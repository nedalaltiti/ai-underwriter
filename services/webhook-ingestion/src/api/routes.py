# services/webhook-ingestion/src/api/routes.py
import json
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, Request, Depends, HTTPException
from loguru import logger

from api.dependencies import get_webhook_processor
from api.health import router as health_router
from core.processor import WebhookProcessor
from core.exceptions import (
    WebhookError, ValidationError, ProcessingError, 
    QueueError, ContentTypeError, RateLimitError, AuthenticationError
)

from models.requests import WebhookRequest, WebhookResponse, WebhookStatus, ErrorCode


# Main API router with versioning
api_router = APIRouter(prefix="/api/v1", tags=["api"])

# Include health check router
api_router.include_router(health_router)

# Webhook router without prefix for clean external URLs
webhook_router = APIRouter(tags=["webhooks"])


@webhook_router.post("/webhook/forth", response_model=WebhookResponse)
async def receive_webhook(
    request: Request,
    processor: WebhookProcessor = Depends(get_webhook_processor)
) -> WebhookResponse:
    """
    Receive webhook from Forth CRM.
    
    Supports multiple content types:
    - application/json
    - application/x-www-form-urlencoded
    - multipart/form-data
    """
    try:
        # Get raw body for signature verification
        raw_body = await request.body()
        
        # Get headers and client IP
        headers = dict(request.headers)
        client_ip = request.client.host if request.client else "unknown"
        
        # Parse request based on content type
        webhook_data = await _parse_webhook_request(request, raw_body)
        
        # Process webhook with security enforcement
        result = await processor.process_webhook(
            webhook_data=webhook_data,
            raw_body=raw_body,
            headers=headers,
            client_ip=client_ip
        )
        
        return WebhookResponse(
            status=WebhookStatus.SUCCESS if result.success else WebhookStatus.ERROR,
            message="Webhook processed successfully" if result.success else result.error_message,
            correlation_id=result.correlation_id,
            processing_time_ms=result.processing_time_ms
        )
        
    except WebhookError as e:
        logger.bind(error_code=e.error_code).warning(f"Webhook error: {e.message}")
        # Map specific error types to HTTP status codes
        if e.error_code == "RATE_LIMIT_EXCEEDED":
            status_code = 429
        elif e.error_code == "WEBHOOK_AUTH_ERROR":
            status_code = 401
        else:
            status_code = e.status_code
            
        raise HTTPException(
            status_code=status_code,
            detail={
                "error": e.error_code,
                "message": e.message,
                "details": {
                    **e.details,
                    "error_code": ErrorCode.PROCESSING_ERROR.value
                }
            }
        )
    except ValueError as e:
        error_msg = str(e)
        logger.warning(f"Invalid webhook data: {error_msg}")
        
        # Determine which field caused the validation error
        field_name = "unknown"
        if "doc_id" in error_msg:
            field_name = "doc_id"
        elif "contact_id" in error_msg:
            field_name = "contact_id"
        elif "Template variables not allowed" in error_msg:
            field_name = "template_variable"
        
        raise HTTPException(
            status_code=400, 
            detail={
                "error": "VALIDATION_ERROR",
                "message": error_msg,
                "details": {
                    "error_code": ErrorCode.VALIDATION_ERROR.value,
                    "field": field_name,
                    "suggestion": "Please configure Forth CRM to send actual field values instead of template placeholders."
                }
            }
        )
    except Exception as e:
        logger.error(f"Unexpected webhook processing error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail={
                "error": "INTERNAL_ERROR",
                "message": "Internal server error",
                "details": {
                    "error_code": ErrorCode.PROCESSING_ERROR.value
                }
            }
        )


@webhook_router.get("/webhook/forth")
async def webhook_verification():
    """
    GET endpoint for webhook verification.
    
    Some webhook providers send a GET request to verify the endpoint.
    """
    return {
        "status": "active",
        "service": "webhook-ingestion",
        "timestamp": datetime.now().isoformat(),
        "message": "Webhook endpoint is ready to receive POST requests"
    }


async def _parse_webhook_request(request: Request, raw_body: bytes) -> Dict[str, Any]:
    """Parse webhook request based on content type."""
    content_type = request.headers.get("content-type", "")
    
    try:
        # Handle JSON content
        if "application/json" in content_type or not content_type:
            return json.loads(raw_body) if raw_body else {}
        
        # Handle form data (both urlencoded and multipart)
        if "form" in content_type:
            form_data = await request.form()
            return dict(form_data)
            
        # Unknown content type - try JSON as fallback
        return json.loads(raw_body) if raw_body else {}
        
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON: {e}")
        raise ContentTypeError(content_type or "application/json")
    except Exception as e:
        logger.warning(f"Failed to parse request with content type {content_type}: {e}")
        raise ContentTypeError(content_type)


# Export both routers
__all__ = ["api_router", "webhook_router"]