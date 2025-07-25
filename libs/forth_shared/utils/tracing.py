# libs/forth_shared/utils/tracing.py
"""Tracing utilities for correlation ID generation and tracking."""

from uuid import uuid4
from datetime import datetime, UTC
from typing import Optional


def generate_correlation_id(prefix: str = "webhook") -> str:
    """
    Generate a unique correlation ID for request tracing.
    
    Args:
        prefix: Prefix for the correlation ID (default: "webhook")
        
    Returns:
        Unique correlation ID string
        
    Example:
        >>> generate_correlation_id("webhook")
        'webhook-a1b2c3d4-1640995200'
        >>> generate_correlation_id("batch")
        'batch-e5f6g7h8-1640995201'
    """
    uuid_hex = uuid4().hex[:8]
    timestamp = int(datetime.now(UTC).timestamp())
    return f"{prefix}-{uuid_hex}-{timestamp}"


def generate_webhook_correlation_id() -> str:
    """Generate a correlation ID specifically for webhook requests."""
    return generate_correlation_id("webhook")


def generate_batch_correlation_id() -> str:
    """Generate a correlation ID specifically for batch processing."""
    return generate_correlation_id("batch")


def extract_correlation_id(data: dict, fallback_prefix: str = "webhook") -> Optional[str]:
    """
    Extract correlation ID from data or generate one if not present.
    
    Args:
        data: Data dictionary to extract correlation ID from
        fallback_prefix: Prefix to use if generating new correlation ID
        
    Returns:
        Correlation ID string or None if not found and no fallback
    """
    correlation_id = data.get("correlation_id") or data.get("correlationId")
    
    if not correlation_id:
        return generate_correlation_id(fallback_prefix)
    
    return str(correlation_id) 