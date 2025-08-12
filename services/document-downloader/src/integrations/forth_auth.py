# services/document-downloader/src/integrations/forth_auth.py
"""Forth API authentication and token management."""

import asyncio
import httpx
from datetime import datetime, UTC, timedelta
from typing import Optional, Dict, Any
from loguru import logger
from pydantic import BaseModel, Field

from config import DocumentConfig


class TokenInfo(BaseModel):
    """token information model."""
    api_key: str
    expires_at: datetime
    created_at: datetime
    
    @classmethod
    def from_forth_response(cls, response_data: Dict[str, Any]) -> "TokenInfo":
        """Create TokenInfo from Forth API response using expires_in."""
        api_key = response_data.get("api_key")
        expires_in_seconds = response_data.get("expires_in", 864000)  # Default 10 days
        
        if not api_key:
            raise ValueError("No api_key in response")
        
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=expires_in_seconds)
        
        return cls(
            api_key=api_key,
            expires_at=expires_at,
            created_at=now
        )
    
    def is_expired(self) -> bool:
        """Check if token is expired."""
        return datetime.now(UTC) >= self.expires_at
    
    def needs_refresh(self, refresh_before_seconds: int) -> bool:
        """Check if token needs refresh."""
        refresh_time = self.expires_at - timedelta(seconds=refresh_before_seconds)
        return datetime.now(UTC) >= refresh_time
    
    def seconds_until_expiry(self) -> int:
        """Get seconds until expiration."""
        remaining = self.expires_at - datetime.now(UTC)
        return max(0, int(remaining.total_seconds()))


class ForthAuthManager:
    """Forth API authentication manager."""
    
    def __init__(self, config: DocumentConfig):
        self.config = config
        self.client_id = config.forth_client_id.get_secret_value() if config.forth_client_id else None
        self.client_secret = config.forth_client_secret.get_secret_value() if config.forth_client_secret else None
        self.base_url = config.forth_api_base_url
        
        self._current_token: Optional[TokenInfo] = None
        self._refresh_task: Optional[asyncio.Task] = None
        self._refresh_lock = asyncio.Lock()
        self._http_client: Optional[httpx.AsyncClient] = None
        
        # Use expires_in from API response to calculate refresh timing
        # Refresh 2 days before expiration (172800 seconds = 2 days)
        self.refresh_before_seconds = config.forth_token_refresh_days * 24 * 3600
        self.check_interval_seconds = 3600  # Check every hour
        
    def has_credentials(self) -> bool:
        """Check if we have the necessary credentials for token refresh."""
        return bool(self.client_id and self.client_secret)
        
    async def initialize(self):
        """Initialize the auth manager."""
        if not self.has_credentials():
            logger.warning("No client credentials - token refresh disabled")
            return
        
        self._http_client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(30),
            headers={"Accept": "application/json"}
        )
        
        # Get initial token
        await self._refresh_token()
        
        # Start background refresh task
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        
        logger.info("Forth Auth Manager initialized")
    
    async def close(self):
        """Close the auth manager."""
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        
        if self._http_client:
            await self._http_client.aclose()
        
        logger.info("Forth Auth Manager closed")
    
    async def get_current_api_key(self) -> Optional[str]:
        """Get the current valid API key."""
        async with self._refresh_lock:
            if not self._current_token or self._current_token.is_expired():
                await self._refresh_token()
            
            return self._current_token.api_key if self._current_token else None
    
    async def _refresh_token(self) -> bool:
        """Refresh the API token using Forth API format."""
        if not self.client_id or not self.client_secret:
            logger.error("Missing client credentials")
            return False
        
        try:
            logger.info(f"Refreshing Forth API token at {self.base_url}/auth/token")
            logger.debug(f"Using client_id: {self.client_id}")
            
            # Use httpx's files parameter with string values to force multipart/form-data
            # This mimics curl's -F behavior exactly
            form_data = {
                "client_secret": (None, self.client_secret),
                "client_id": (None, self.client_id)
            }
            
            response = await self._http_client.post(
                "/auth/token",
                files=form_data,  # This forces multipart/form-data like curl -F
                headers={
                    "Accept": "application/json"
                }
            )
            
            logger.debug(f"Token refresh response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.debug(f"Token refresh response structure: status={data.get('status', {}).get('code')}, has_response={bool(data.get('response'))}")
                
                # Parse Forth API response: {"status": {...}, "response": {"api_key": "...", "expires_in": 864000}}
                if data.get("status", {}).get("code") == 200 and "response" in data:
                    self._current_token = TokenInfo.from_forth_response(data["response"])
                    
                    expires_in_hours = self._current_token.seconds_until_expiry() // 3600
                    logger.info(f"✅ Token refreshed successfully - expires in {expires_in_hours} hours")
                    return True
                else:
                    # Don't log the full response as it may contain sensitive data
                    status_info = data.get("status", {})
                    logger.error(f"Token refresh failed: {status_info.get('message', 'Unknown error')} (code: {status_info.get('code')})")
                    return False
            else:
                # Log status code but not response body for security
                logger.error(f"Token refresh HTTP error: {response.status_code}")
                try:
                    error_data = response.json()
                    if "status" in error_data and "message" in error_data["status"]:
                        logger.error(f"Error message: {error_data['status']['message']}")
                except:
                    pass
                return False
                
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return False
    
    async def _refresh_loop(self):
        """Background refresh loop using expires_in timing."""
        while True:
            try:
                await asyncio.sleep(self.check_interval_seconds)
                
                if self._current_token and self._current_token.needs_refresh(self.refresh_before_seconds):
                    async with self._refresh_lock:
                        logger.info("Token needs refresh - refreshing proactively")
                        await self._refresh_token()
                        
            except asyncio.CancelledError:
                logger.info("Refresh loop cancelled")
                break
            except Exception as e:
                logger.error(f"Refresh loop error: {e}")
                await asyncio.sleep(60)
    
    def get_token_status(self) -> Dict[str, Any]:
        """Get simple token status."""
        if not self._current_token:
            return {
                "has_token": False,
                "has_credentials": self.has_credentials(),
                "status": "no_token"
            }
        
        seconds_remaining = self._current_token.seconds_until_expiry()
        hours_remaining = seconds_remaining // 3600
        
        return {
            "has_token": True,
            "has_credentials": self.has_credentials(),
            "expires_at": self._current_token.expires_at.isoformat(),
            "expires_in_hours": hours_remaining,
            "expires_in_seconds": seconds_remaining,
            "is_expired": self._current_token.is_expired(),
            "needs_refresh": self._current_token.needs_refresh(self.refresh_before_seconds),
            "status": "expired" if self._current_token.is_expired() 
                     else "needs_refresh" if self._current_token.needs_refresh(self.refresh_before_seconds)
                     else "valid"
        }
