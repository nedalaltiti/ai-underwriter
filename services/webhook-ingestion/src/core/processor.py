# services/webhook-ingestion/src/core/processor.py
import time
from typing import Dict, Any, Optional, Mapping
from datetime import datetime, UTC
from loguru import logger

from config import WebhookConfig
from models.requests import WebhookPayload, ErrorCode, ProcessingResult
from core.validators import WebhookValidator
from core.exceptions import ValidationError, ProcessingError, QueueError, RateLimitError, AuthenticationError
from core.security import RateLimiter, WebhookSignatureVerifier, verify_webhook_security_raw
from libs.forth_shared.models.queue import QueueMessage, MessageType
from libs.forth_shared.adapters.queue import QueueAdapter, SQSAdapter
from libs.forth_shared.utils.error_handling import handle_errors
from libs.forth_shared.utils.tracing import generate_webhook_correlation_id


class WebhookProcessor:
    """Core webhook processing logic."""
    
    def __init__(self, config: WebhookConfig):
        self.config = config
        self.validator = WebhookValidator()
        self.queue_adapter: Optional[QueueAdapter] = None
        self._service_start_time = time.time()  # Track service start time
        
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
                queue_name=self.config.uw_uploaded_docs_queue,
                region=self.config.aws_region,
                endpoint_url=self.config.get_aws_endpoint_url()
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
        
    async def process_webhook(
        self, 
        webhook_data: Mapping[str, Any], 
        raw_body: Optional[bytes] = None,
        headers: Optional[Mapping[str, str]] = None,
        client_ip: Optional[str] = None
    ) -> ProcessingResult:
        """Process incoming webhook with security enforcement."""
        start_time = time.perf_counter()  # Use monotonic time for accurate measurement
        correlation_id = webhook_data.get("correlation_id") or generate_webhook_correlation_id()
        
        try:
            # Update metrics
            self.metrics["total_requests"] += 1
            
            # Enforce security checks
            security_result = self._enforce_security(
                raw_body, headers, client_ip, correlation_id, start_time
            )
            if security_result:
                return security_result
            
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
            
            webhook_logger.info("📨 Processing webhook")
            
            # Create queue message for document download
            message = QueueMessage(
                message_type=MessageType.CONTRACT_DOWNLOAD,
                contact_id=payload.contact_id,
                correlation_id=correlation_id,
                data={
                    "doc_id": payload.doc_id,
                    "doc_type": payload.doc_type,
                    "doc_name": payload.doc_name,
                    "doc_title": payload.doc_title,
                    "file_type": payload.file_type,
                    "timestamp": payload.timestamp,
                    "webhook_version": payload.webhook_version,
                    "webhook_source": payload.source.value,
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
                    queue_name=self.config.uw_uploaded_docs_queue
                )
            
            # Calculate processing time and update metrics
            processing_time_ms = int((time.perf_counter() - start_time) * 1000)
            self._update_metrics(True, processing_time_ms)
            
            webhook_logger.bind(
                message_id=message_id,
                processing_time_ms=processing_time_ms
            ).info(f"✅ Webhook processed successfully: {processing_time_ms}ms")
            
            return ProcessingResult(
                success=True,
                message_id=message_id,
                correlation_id=correlation_id,
                processing_time_ms=processing_time_ms
            )
            
        except ValidationError as e:
            self.metrics["validation_errors"] += 1
            processing_time_ms = int((time.perf_counter() - start_time) * 1000)
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
                processing_time_ms=processing_time_ms,
                error_code=ErrorCode.VALIDATION_ERROR
            )
            
        except QueueError as e:
            self.metrics["queue_errors"] += 1
            processing_time_ms = int((time.perf_counter() - start_time) * 1000)
            self._update_metrics(False, processing_time_ms)
            
            logger.bind(
                correlation_id=correlation_id,
                processing_time_ms=processing_time_ms,
                queue_name=self.config.uw_uploaded_docs_queue
            ).error(
                f"🚫 Queue error during webhook processing: {str(e)}"
            )
            
            return ProcessingResult(
                success=False,
                error_message=str(e),
                correlation_id=correlation_id,
                processing_time_ms=processing_time_ms,
                error_code=ErrorCode.QUEUE_ERROR
            )
            
        except Exception as e:
            self.metrics["failed_requests"] += 1
            processing_time_ms = int((time.perf_counter() - start_time) * 1000)
            self._update_metrics(False, processing_time_ms)
            
            logger.bind(
                correlation_id=correlation_id,
                processing_time_ms=processing_time_ms,
                error_type=type(e).__name__
            ).error(
                f"💥 Unexpected webhook processing error: {str(e)}"
            )
            
            return ProcessingResult(
                success=False,
                error_message="Internal processing error",
                correlation_id=correlation_id,
                processing_time_ms=processing_time_ms,
                error_code=ErrorCode.PROCESSING_ERROR
            )
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get service metrics."""
        return {
            "service": self.config.service_name,
            "metrics": self.metrics,
            "timestamp": datetime.now(UTC).isoformat()
        }
    
    def _update_metrics(self, success: bool, processing_time_ms: int) -> None:
        """Update processing metrics."""
        if success:
            self.metrics["successful_requests"] += 1
        else:
            self.metrics["failed_requests"] += 1
            
        # Update average processing time
        total_requests = self.metrics["total_requests"]
        if total_requests > 0:
            current_avg = self.metrics["average_processing_time_ms"]
            self.metrics["average_processing_time_ms"] = (
                (current_avg * (total_requests - 1) + processing_time_ms) / total_requests
            )
        else:
            # First request
            self.metrics["average_processing_time_ms"] = processing_time_ms
    
    def _enforce_security(
        self,
        raw_body: Optional[bytes],
        headers: Optional[Mapping[str, str]],
        client_ip: Optional[str],
        correlation_id: str,
        start_time: float
    ) -> Optional[ProcessingResult]:
        """Enforce security checks and return error result if failed."""
        try:
            verify_webhook_security_raw(
                raw_body=raw_body,
                headers=headers,
                client_ip=client_ip,
                rate_limiter=self.rate_limiter,
                signature_verifier=self.signature_verifier,
                correlation_id=correlation_id
            )
            return None  # Security passed
        except RateLimitError as e:
            self.metrics["rate_limit_errors"] += 1
            processing_time_ms = int((time.perf_counter() - start_time) * 1000)
            self._update_metrics(False, processing_time_ms)
            
            return ProcessingResult(
                success=False,
                error_message=str(e),
                correlation_id=correlation_id,
                processing_time_ms=processing_time_ms,
                error_code=ErrorCode.RATE_LIMIT_ERROR
            )
        except AuthenticationError as e:
            self.metrics["auth_errors"] += 1
            processing_time_ms = int((time.perf_counter() - start_time) * 1000)
            self._update_metrics(False, processing_time_ms)
            
            return ProcessingResult(
                success=False,
                error_message=str(e),
                correlation_id=correlation_id,
                processing_time_ms=processing_time_ms,
                error_code=ErrorCode.AUTHENTICATION_ERROR
            )