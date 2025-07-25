# services/webhook-ingestion/src/core/exceptions.py
"""Webhook-specific exception handling."""

from typing import Optional, Dict, Any
from libs.forth_shared.utils.error_handling import ServiceError, ValidationError as BaseValidationError


class WebhookError(ServiceError):
    """Base exception for webhook-related errors."""
    
    def __init__(self, message: str, **kwargs):
        error_code = kwargs.pop('error_code', 'WEBHOOK_ERROR')
        super().__init__(
            message=message,
            error_code=error_code,
            **kwargs
        )


class ValidationError(BaseValidationError):
    """Webhook validation error extending shared validation error."""
    
    def __init__(self, message: str, field: Optional[str] = None, error_code: Optional[str] = None, **kwargs):
        super().__init__(message=message, field=field, **kwargs)
        self.error_code = error_code or "WEBHOOK_VALIDATION_ERROR"


class ProcessingError(WebhookError):
    """Webhook processing error."""
    
    def __init__(self, message: str, stage: Optional[str] = None, **kwargs):
        super().__init__(
            message=message,
            error_code="WEBHOOK_PROCESSING_ERROR",
            status_code=500,
            **kwargs
        )
        if stage:
            self.details["processing_stage"] = stage


class QueueError(WebhookError):
    """Queue-related error."""
    
    def __init__(self, message: str, queue_name: Optional[str] = None, **kwargs):
        super().__init__(
            message=message,
            error_code="QUEUE_ERROR",
            status_code=502,
            **kwargs
        )
        if queue_name:
            self.details["queue_name"] = queue_name


class AuthenticationError(WebhookError):
    """Webhook authentication/signature verification error."""
    
    def __init__(self, message: str = "Invalid webhook signature", **kwargs):
        super().__init__(
            message=message,
            error_code="WEBHOOK_AUTH_ERROR",
            status_code=401,
            **kwargs
        )


class RateLimitError(WebhookError):
    """Rate limit exceeded error."""
    
    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None, **kwargs):
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            **kwargs
        )
        if retry_after:
            self.details["retry_after"] = retry_after


class ContentTypeError(WebhookError):
    """Unsupported content type error."""
    
    def __init__(self, content_type: str, **kwargs):
        super().__init__(
            message=f"Unsupported content type: {content_type}",
            error_code="UNSUPPORTED_CONTENT_TYPE",
            status_code=415,
            **kwargs
        )
        self.details["content_type"] = content_type 