# services/webhook-ingestion/src/api/routes.py
import json
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, Request, Depends, HTTPException
from loguru import logger

from api.dependencies import get_webhook_processor
from core.processor import WebhookProcessor
from core.exceptions import (
    WebhookError, ValidationError, ProcessingError, 
    QueueError, ContentTypeError, RateLimitError, AuthenticationError
)
from core.security import verify_webhook_security
from models.requests import WebhookRequest, WebhookResponse


# Main API router with versioning
api_router = APIRouter(prefix="/api/v1", tags=["api"])

# Webhook router without prefix for clean external URLs
webhook_router = APIRouter(tags=["webhooks"])


@api_router.get("/health")
async def health_check(processor: WebhookProcessor = Depends(get_webhook_processor)):
    """Health check endpoint."""
    health_status = await processor.health_check()
    
    if health_status["status"] != "healthy":
        raise HTTPException(status_code=503, detail=health_status)
    
    return health_status


@api_router.get("/metrics")
async def get_metrics(processor: WebhookProcessor = Depends(get_webhook_processor)):
    """Get service metrics."""
    return await processor.get_metrics()


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
        # Security verification (rate limiting + signature verification)
        await verify_webhook_security(
            request=request,
            rate_limiter=processor.get_rate_limiter(),
            signature_verifier=processor.get_signature_verifier(),
            require_signature=False  # Set to True if signature is mandatory
        )
        
        # Parse request based on content type
        webhook_data = await _parse_webhook_request(request)
        
        # Process webhook
        result = await processor.process_webhook(webhook_data)
        
        return WebhookResponse(
            status="success" if result.success else "error",
            message="Webhook processed successfully" if result.success else result.error_message,
            correlation_id=result.correlation_id,
            processing_time_ms=result.processing_time_ms
        )
        
    except WebhookError as e:
        logger.warning(f"Webhook error: {e.message}")
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "error": e.error_code,
                "message": e.message,
                "details": e.details
            }
        )
    except ValueError as e:
        logger.warning(f"Invalid webhook data: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected webhook processing error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail={
                "error": "INTERNAL_ERROR",
                "message": "Internal server error"
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


async def _parse_webhook_request(request: Request) -> Dict[str, Any]:
    """Parse webhook request based on content type."""
    content_type = request.headers.get("content-type", "")
    
    try:
        if "application/json" in content_type:
            return await request.json()
        elif "application/x-www-form-urlencoded" in content_type:
            form_data = await request.form()
            return dict(form_data)
        elif "multipart/form-data" in content_type:
            form_data = await request.form()
            return dict(form_data)
        else:
            # Try to parse as JSON by default
            body = await request.body()
            if body:
                return json.loads(body)
            return {}
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON: {e}")
        raise ContentTypeError(content_type)
    except Exception as e:
        logger.warning(f"Failed to parse request with content type {content_type}: {e}")
        raise ContentTypeError(content_type)


# Export both routers
__all__ = ["api_router", "webhook_router"]