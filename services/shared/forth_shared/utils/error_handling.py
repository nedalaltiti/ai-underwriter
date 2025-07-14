# shared/forth_shared/utils/error_handling.py
from typing import Optional, Dict, Any, Type
from functools import wraps
import asyncio
from loguru import logger
import traceback


class ServiceError(Exception):
    """Base exception for service errors."""
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 500
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "INTERNAL_ERROR"
        self.details = details or {}
        self.status_code = status_code
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "details": self.details
            }
        }


class ValidationError(ServiceError):
    """Validation error."""
    
    def __init__(self, message: str, field: Optional[str] = None, **kwargs):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=400,
            **kwargs
        )
        if field:
            self.details["field"] = field


class NotFoundError(ServiceError):
    """Resource not found error."""
    
    def __init__(self, resource: str, identifier: str, **kwargs):
        super().__init__(
            message=f"{resource} not found: {identifier}",
            error_code="NOT_FOUND",
            status_code=404,
            **kwargs
        )
        self.details.update({
            "resource": resource,
            "identifier": identifier
        })


class ExternalServiceError(ServiceError):
    """External service error."""
    
    def __init__(self, service: str, message: str, **kwargs):
        super().__init__(
            message=f"{service} error: {message}",
            error_code="EXTERNAL_SERVICE_ERROR",
            status_code=502,
            **kwargs
        )
        self.details["service"] = service


def handle_errors(
    default_message: str = "An error occurred",
    log_errors: bool = True
):
    """Decorator for consistent error handling."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except ServiceError:
                # Re-raise service errors as-is
                raise
            except asyncio.CancelledError:
                # Don't catch cancellation
                raise
            except Exception as e:
                if log_errors:
                    logger.error(
                        f"Unhandled error in {func.__name__}: {e}",
                        exc_info=True
                    )
                
                # Wrap in ServiceError
                raise ServiceError(
                    message=default_message,
                    details={
                        "original_error": str(e),
                        "traceback": traceback.format_exc()
                    }
                )
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except ServiceError:
                raise
            except Exception as e:
                if log_errors:
                    logger.error(
                        f"Unhandled error in {func.__name__}: {e}",
                        exc_info=True
                    )
                
                raise ServiceError(
                    message=default_message,
                    details={
                        "original_error": str(e),
                        "traceback": traceback.format_exc()
                    }
                )
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator
