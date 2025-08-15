# services/webhook-ingestion/src/core/validators.py
from typing import Mapping, Any, Optional
from loguru import logger
from pydantic import ValidationError as PydanticValidationError

from models.requests import WebhookRequest, WebhookPayload, ErrorCode
from core.exceptions import ValidationError
from libs.forth_shared.utils.tracing import extract_correlation_id


class WebhookValidator:
    """Validates incoming webhook data using Pydantic models."""
    
    def validate_webhook(self, data: Mapping[str, Any]) -> WebhookPayload:
        """
        Validate webhook data using Pydantic and return structured payload.
        
        Args:
            data: Raw webhook data (immutable mapping)
            
        Returns:
            Validated WebhookPayload
            
        Raises:
            ValidationError: If validation fails (includes ErrorCode.VALIDATION_ERROR)
        """
        try:
            # Let Pydantic handle all validation
            webhook_request = WebhookRequest(**data)
            
            # Generate correlation ID if not provided
            correlation_id = webhook_request.correlation_id or extract_correlation_id(dict(data), "webhook")
            
            # Convert to internal payload format
            payload = WebhookPayload.from_webhook_request(
                webhook_request,
                correlation_id=correlation_id,
                raw_data=dict(data)  # Convert mapping to dict for storage
            )
            
            logger.debug("Webhook validation successful")
            
            return payload
            
        except PydanticValidationError as e:
            # Convert Pydantic validation errors to our ValidationError with error code
            error_details = []
            for error in e.errors():
                field = ".".join(str(loc) for loc in error["loc"])
                message = error["msg"]
                error_details.append(f"{field}: {message}")
            
            error_message = f"Validation failed: {'; '.join(error_details)}"
            
            logger.bind(
                validation_errors=error_details,
                raw_data_keys=list(data.keys()) if hasattr(data, 'keys') else None
            ).warning(f"🔍 WEBHOOK VALIDATION FAILED: {error_message}")
            
            raise ValidationError(
                error_message,
                error_code=ErrorCode.VALIDATION_ERROR,
                details={"validation_errors": error_details}
            )
            
        except Exception as e:
            logger.bind(
                error_type=type(e).__name__,
                error_message=str(e),
                raw_data_keys=list(data.keys()) if hasattr(data, 'keys') else None
            ).error(f"🔍 UNEXPECTED VALIDATION ERROR: {e}", exc_info=True)
            
            raise ValidationError(
                f"Validation failed: {str(e)}",
                error_code=ErrorCode.VALIDATION_ERROR,
                details={"error_type": type(e).__name__, "original_error": str(e)}
            )
