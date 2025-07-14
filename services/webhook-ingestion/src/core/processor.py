# services/webhook-ingestion/src/core/processor.py
import time
from typing import Dict, Any, Optional, Union
from datetime import datetime, UTC
from loguru import logger

from config import WebhookConfig
from models.requests import WebhookPayload
from core.validators import WebhookValidator
from core.exceptions import ValidationError, ProcessingError, QueueError
from core.security import RateLimiter, WebhookSignatureVerifier
from forth_shared.models.queue import QueueMessage, MessageType
from forth_shared.adapters.queue import QueueAdapter, SQSAdapter
from forth_shared.utils.error_handling import handle_errors


class ProcessingResult:
    """Result of webhook processing."""
    
    def __init__(
        self,
        success: bool,
        message_id: Optional[str] = None,
        error_message: Optional[str] = None,
        correlation_id: Optional[str] = None,
        processing_time_ms: int = 0
    ):
        self.success = success
        self.message_id = message_id
        self.error_message = error_message
        self.correlation_id = correlation_id
        self.processing_time_ms = processing_time_ms


class WebhookProcessor:
    """Core webhook processing logic."""
    
    def __init__(self, config: WebhookConfig):
        self.config = config
        self.validator = WebhookValidator()
        self.queue_adapter: Optional[QueueAdapter] = None
        
        # Security components
        self.rate_limiter: Optional[RateLimiter] = None
        self.signature_verifier: Optional[WebhookSignatureVerifier] = None
        
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "validation_errors": 0,
            "queue_errors": 0,
            "rate_limit_errors": 0,
            "auth_errors": 0,
            "average_processing_time_ms": 0.0,
        }
        
    @handle_errors("Failed to initialize webhook processor")
    async def initialize(self):
        """Initialize processor resources."""
        logger.info("🚀 Initializing webhook processor")
        
        try:
            # Initialize queue adapter
            self.queue_adapter = SQSAdapter(
                queue_name=self.config.output_queue_name,
                region=self.config.aws_region,
                endpoint_url=self.config.get_aws_endpoint_url() if hasattr(self.config, 'get_aws_endpoint_url') else None
            )
            
            # Initialize security components
            if self.config.rate_limit_enabled:
                self.rate_limiter = RateLimiter(
                    max_requests=self.config.rate_limit_requests,
                    window_seconds=self.config.rate_limit_period
                )
                logger.info(
                    f"🛡️  Rate limiting: {self.config.rate_limit_requests} requests/{self.config.rate_limit_period}s"
                )
            
            if self.config.webhook_secret:
                self.signature_verifier = WebhookSignatureVerifier(
                    secret=self.config.webhook_secret
                )
                logger.info("🔐 Webhook signature verification enabled")
            
            # Verify queue connectivity
            await self.health_check()
            
            logger.info("✅ Webhook processor ready!")
        except Exception as e:
            logger.error(f"Failed to initialize processor: {e}")
            raise ProcessingError(
                f"Processor initialization failed: {str(e)}",
                stage="initialization"
            )
        
    async def shutdown(self) -> None:
        """Cleanup resources."""
        logger.info("Shutting down webhook processor")
        
        # Cleanup queue connections
        if self.queue_adapter and hasattr(self.queue_adapter, 'close'):
            try:
                await self.queue_adapter.close()
            except Exception as e:
                logger.error(f"Error closing queue adapter: {e}")
        
        logger.info("Webhook processor shutdown completed")
        
    async def process_webhook(self, webhook_data: Dict[str, Any]) -> ProcessingResult:
        """Process incoming webhook."""
        start_time = time.time()
        correlation_id = webhook_data.get("correlation_id") or self._generate_correlation_id()
        
        try:
            # Update metrics
            self.metrics["total_requests"] += 1
            
            # Validate and parse webhook data
            payload = self.validator.validate_webhook(webhook_data)
            
            # Bind context for this webhook processing
            webhook_logger = logger.bind(
                contact_id=payload.contact_id,
                doc_id=payload.doc_id,
                doc_type=payload.doc_type,
                correlation_id=correlation_id,
                source=payload.source.value
            )
            
            webhook_logger.info(
                f"📨 Processing webhook: contact_id={payload.contact_id}, doc_id={payload.doc_id}, type={payload.doc_type}"
            )
            
            # Create queue message for document download
            message = QueueMessage(
                message_type=MessageType.CONTRACT_DOWNLOAD,
                contact_id=payload.contact_id,
                correlation_id=correlation_id,
                data={
                    "doc_id": payload.doc_id,
                    "doc_type": payload.doc_type,
                    "doc_name": payload.doc_name,
                    "doc_url": payload.doc_url,
                    "hardship_description": payload.hardship_description,
                    "webhook_source": payload.source,
                    "raw_data": payload.raw_data,
                }
            )
            
            # Send to queue
            try:
                message_id = await self.queue_adapter.send_message(message)
            except Exception as e:
                logger.error(f"Failed to send message to queue: {e}")
                raise QueueError(
                    f"Failed to send message to queue: {str(e)}",
                    queue_name=self.config.output_queue_name
                )
            
            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)
            self._update_metrics(True, processing_time_ms)
            
            webhook_logger.bind(
                message_id=message_id,
                processing_time_ms=processing_time_ms
            ).info(
                f"✅ Webhook processed successfully: {processing_time_ms}ms | contact_id={payload.contact_id}, doc_id={payload.doc_id}"
            )
            
            return ProcessingResult(
                success=True,
                message_id=message_id,
                correlation_id=correlation_id,
                processing_time_ms=processing_time_ms
            )
            
        except ValidationError as e:
            self.metrics["validation_errors"] += 1
            processing_time_ms = int((time.time() - start_time) * 1000)
            self._update_metrics(False, processing_time_ms)
            
            logger.bind(
                correlation_id=correlation_id,
                processing_time_ms=processing_time_ms
            ).warning(
                f"❌ Webhook validation failed: {str(e)}"
            )
            
            return ProcessingResult(
                success=False,
                error_message=str(e),
                correlation_id=correlation_id,
                processing_time_ms=processing_time_ms
            )
            
        except QueueError as e:
            self.metrics["queue_errors"] += 1
            processing_time_ms = int((time.time() - start_time) * 1000)
            self._update_metrics(False, processing_time_ms)
            
            logger.bind(
                correlation_id=correlation_id,
                processing_time_ms=processing_time_ms,
                queue_name=self.config.output_queue_name
            ).error(
                f"🚫 Queue error during webhook processing: {str(e)}"
            )
            
            return ProcessingResult(
                success=False,
                error_message=str(e),
                correlation_id=correlation_id,
                processing_time_ms=processing_time_ms
            )
            
        except Exception as e:
            self.metrics["failed_requests"] += 1
            processing_time_ms = int((time.time() - start_time) * 1000)
            self._update_metrics(False, processing_time_ms)
            
            logger.bind(
                correlation_id=correlation_id,
                processing_time_ms=processing_time_ms
            ).error(
                f"💥 Unexpected webhook processing error: {str(e)}"
            )
            
            # Wrap unexpected errors
            error = ProcessingError(
                "Internal processing error occurred",
                stage="processing",
                details={"original_error": str(e)}
            )
            
            return ProcessingResult(
                success=False,
                error_message="Internal processing error",
                correlation_id=correlation_id,
                processing_time_ms=processing_time_ms
            )
    
    async def health_check(self) -> Dict[str, Any]:
        """Check service health."""
        health_status = {
            "service": self.config.service_name,
            "version": self.config.service_version,
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "healthy",
            "checks": {}
        }
        
        try:
            # Check queue connectivity
            if self.queue_adapter:
                try:
                    # Try to get queue attributes as a connectivity test
                    await self.queue_adapter._ensure_client()
                    health_status["checks"]["queue"] = {
                        "status": "healthy",
                        "queue_name": self.config.output_queue_name,
                        "queue_url": getattr(self.queue_adapter, '_queue_url', None)
                    }
                except Exception as e:
                    health_status["checks"]["queue"] = {
                        "status": "unhealthy",
                        "error": str(e),
                        "queue_name": self.config.output_queue_name
                    }
                    health_status["status"] = "unhealthy"
            else:
                health_status["checks"]["queue"] = {
                    "status": "unhealthy",
                    "error": "Queue adapter not initialized"
                }
                health_status["status"] = "unhealthy"
            
            # Check security components
            health_status["checks"]["security"] = {
                "rate_limiting": self.rate_limiter is not None,
                "signature_verification": self.signature_verifier is not None
            }
            
            # Add metrics summary
            health_status["metrics"] = {
                "total_requests": self.metrics["total_requests"],
                "success_rate": (
                    self.metrics["successful_requests"] / max(self.metrics["total_requests"], 1) * 100
                ),
                "average_processing_time_ms": self.metrics["average_processing_time_ms"]
            }
            
            return health_status
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "service": self.config.service_name,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat()
            }
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get service metrics."""
        return {
            "service": self.config.service_name,
            "metrics": self.metrics,
            "timestamp": datetime.now(UTC).isoformat()
        }
    
    def _generate_correlation_id(self) -> str:
        """Generate correlation ID for request tracing."""
        from uuid import uuid4
        return f"webhook-{uuid4().hex[:8]}-{int(time.time())}"
    
    def _update_metrics(self, success: bool, processing_time_ms: int) -> None:
        """Update processing metrics."""
        if success:
            self.metrics["successful_requests"] += 1
        else:
            self.metrics["failed_requests"] += 1
            
        # Update average processing time
        total_requests = self.metrics["total_requests"]
        current_avg = self.metrics["average_processing_time_ms"]
        
        self.metrics["average_processing_time_ms"] = (
            (current_avg * (total_requests - 1) + processing_time_ms) / total_requests
        )
    
    @property
    def security_enabled(self) -> bool:
        """Check if any security features are enabled."""
        return bool(self.rate_limiter or self.signature_verifier)
    
    def get_rate_limiter(self) -> Optional[RateLimiter]:
        """Get rate limiter instance."""
        return self.rate_limiter
    
    def get_signature_verifier(self) -> Optional[WebhookSignatureVerifier]:
        """Get signature verifier instance."""
        return self.signature_verifier