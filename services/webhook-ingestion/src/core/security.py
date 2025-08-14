# services/webhook-ingestion/src/core/security.py
"""Security utilities for webhook ingestion."""

import hmac
import hashlib
import time
from typing import Dict, Optional, Tuple
from collections import defaultdict, deque
from fastapi import Request
from loguru import logger

from core.exceptions import RateLimitError, AuthenticationError


class RateLimiter:
    """Simple in-memory rate limiter."""
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, deque] = defaultdict(deque)
    
    def is_allowed(self, client_id: str) -> Tuple[bool, Optional[int]]:
        """
        Check if request is allowed for client.
        
        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        now = time.time()
        client_requests = self.requests[client_id]
        
        # Remove old requests outside the window
        while client_requests and client_requests[0] <= now - self.window_seconds:
            client_requests.popleft()
        
        # Check if limit exceeded
        if len(client_requests) >= self.max_requests:
            # Calculate when the oldest request will expire
            retry_after = int(client_requests[0] + self.window_seconds - now) + 1
            return False, retry_after
        
        # Add current request
        client_requests.append(now)
        return True, None
    
    def get_client_id(self, request: Request) -> str:
        """Extract client identifier from request."""
        # Try to get real IP from headers (for load balancer scenarios)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct client IP
        return request.client.host if request.client else "unknown"


class WebhookSignatureVerifier:
    """Webhook signature verification utility."""
    
    def __init__(self, secret: str):
        self.secret = secret.encode() if isinstance(secret, str) else secret
    
    def verify_signature(
        self, 
        payload: bytes, 
        signature: str,
        algorithm: str = "sha256"
    ) -> bool:
        """
        Verify webhook signature.
        
        Args:
            payload: Raw request body
            signature: Signature from webhook header
            algorithm: Hash algorithm (sha1, sha256)
        
        Returns:
            True if signature is valid
        
        Raises:
            AuthenticationError: If signature is missing or invalid
        """
        if not self.secret:
            logger.error("🔐 Webhook secret not configured - authentication required")
            raise AuthenticationError("Webhook secret not configured")
        
        if not signature:
            logger.warning("🔐 Missing webhook signature header")
            raise AuthenticationError("Missing webhook signature")
        
        try:
            # Parse signature format: "sha256=..." or just hex value
            if "=" in signature:
                sig_algorithm, sig_value = signature.split("=", 1)
            else:
                # Forth CRM HMAC sends just the hex value without prefix
                sig_algorithm = algorithm
                sig_value = signature
            
            # Auto-detect algorithm based on signature length if not specified
            if sig_algorithm == algorithm and "=" not in signature:
                if len(sig_value) == 40:
                    sig_algorithm = "sha1"
                elif len(sig_value) == 64:
                    sig_algorithm = "sha256"
            
            logger.debug(f"🔐 Verifying signature - algorithm: {sig_algorithm}")
            logger.debug(f"🔐 Payload length: {len(payload)}")
            
            # Calculate expected signature
            if sig_algorithm == "sha1":
                expected = hmac.new(self.secret, payload, hashlib.sha1).hexdigest()
            elif sig_algorithm == "sha256":
                expected = hmac.new(self.secret, payload, hashlib.sha256).hexdigest()
            else:
                logger.warning(f"🔐 Unsupported signature algorithm: {sig_algorithm}")
                raise AuthenticationError(f"Unsupported signature algorithm: {sig_algorithm}")
            
            # Compare signatures securely
            is_valid = hmac.compare_digest(expected, sig_value)
            if not is_valid:
                logger.warning("🔐 Webhook signature verification failed")
                raise AuthenticationError("Invalid webhook signature")
            
            return True
            
        except AuthenticationError:
            # Re-raise authentication errors
            raise
        except Exception as e:
            logger.error(f"🔐 Signature verification error: {e}")
            raise AuthenticationError("Signature verification failed")
    



def get_signature_from_headers(headers: Dict[str, str]) -> Optional[str]:
    """Extract signature from headers dictionary."""
    # Try common signature header names
    return (
        headers.get("x-hub-signature-256") or
        headers.get("X-Hub-Signature-256") or
        headers.get("x-hub-signature") or
        headers.get("X-Hub-Signature") or
        headers.get("x-forth-signature") or
        headers.get("X-Forth-Signature") or
        headers.get("x-signature") or
        headers.get("X-Signature") or
        headers.get("authorization") or
        headers.get("Authorization")
    )


def get_request_signature(request: Request) -> Optional[str]:
    """Extract signature from FastAPI request headers."""
    return get_signature_from_headers(dict(request.headers))



def verify_webhook_security_raw(
    raw_body: Optional[bytes],
    headers: Optional[Dict[str, str]],
    client_ip: Optional[str],
    rate_limiter: Optional[RateLimiter] = None,
    signature_verifier: Optional[WebhookSignatureVerifier] = None,
    correlation_id: Optional[str] = None
) -> None:
    """
    Comprehensive webhook security verification for raw data.
    
    Args:
        raw_body: Raw request body bytes
        headers: Request headers dictionary
        client_ip: Client IP address
        rate_limiter: Rate limiter instance
        signature_verifier: Signature verifier instance
        correlation_id: Correlation ID for logging
    
    Raises:
        RateLimitError: If rate limit exceeded
        AuthenticationError: If signature verification fails
    """
    # 1. ENFORCE RATE LIMITING
    if rate_limiter and client_ip:
        is_allowed, retry_after = rate_limiter.is_allowed(client_ip)
        if not is_allowed:
            logger.bind(
                correlation_id=correlation_id,
                client_ip=client_ip,
                retry_after=retry_after
            ).warning(f"🚫 Rate limit exceeded for {client_ip}")
            
            raise RateLimitError(
                f"Rate limit exceeded. Try again in {retry_after} seconds",
                retry_after=retry_after
            )
    
    # 2. ENFORCE MANDATORY SIGNATURE VERIFICATION
    if not signature_verifier:
        logger.error("🔐 Webhook signature verifier not configured - authentication required")
        raise AuthenticationError("Webhook authentication not configured")
    
    if raw_body is None:
        logger.warning("🔐 Empty request body - signature verification failed")
        raise AuthenticationError("Empty request body")
        
    if not headers:
        logger.warning("🔐 Missing request headers - signature verification failed")
        raise AuthenticationError("Missing request headers")
    
    signature = get_signature_from_headers(headers)
    if not signature:
        logger.bind(
            correlation_id=correlation_id,
            client_ip=client_ip
        ).warning("🔐 Missing webhook signature header")
        raise AuthenticationError("Missing webhook signature header")
    
    # Verify signature (will raise AuthenticationError if invalid)
    signature_verifier.verify_signature(raw_body, signature)
    logger.bind(
        correlation_id=correlation_id
    ).debug("🔐 Webhook signature verified successfully") 