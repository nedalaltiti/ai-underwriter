# services/webhook-ingestion/src/core/processor.py
import time
from typing import Dict, Any, Optional, Mapping, List
from datetime import datetime, UTC
from loguru import logger

from config import WebhookConfig
from models.requests import WebhookPayload, ErrorCode, ProcessingResult
from core.validators import WebhookValidator
from core.exceptions import ValidationError, ProcessingError, QueueError, RateLimitError, AuthenticationError
from core.security import RateLimiter, WebhookSignatureVerifier, verify_webhook_security_raw
from libs.forth_shared.models.queue import QueueMessage, MessageType
from models.requests import WebhookType
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
            
            # Webhook secret is now mandatory
            if not self.config.webhook_secret or not self.config.webhook_secret.get_secret_value():
                raise ProcessingError(
                    "Webhook secret is required for authentication",
                    stage="initialization"
                )
            
            self.signature_verifier = WebhookSignatureVerifier(
                secret=self.config.webhook_secret.get_secret_value()
            )
            logger.info("🔐 Webhook signature verification enabled (mandatory)")
            
            logger.info("✅ Webhook processor ready!")
        except Exception as e:
            logger.error("Failed to initialize processor: %s", e)
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
                logger.error("Error closing queue adapter: %s", e)
        
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
            # Sanitize correlation_id to avoid Loguru formatting issues
            safe_correlation_id = correlation_id.replace("{", "(").replace("}", ")")
            webhook_logger = logger.bind(
                contact_id=payload.contact_id,
                doc_id=payload.doc_id,
                correlation_id=safe_correlation_id,
                source=payload.source.value
            )
            
            webhook_logger.info(f"webhook.process type={payload.webhook_type.value} contact={payload.contact_id}")
            
            # Create and send queue messages based on webhook type
            try:
                message_ids = await self._create_and_send_messages(payload, correlation_id, webhook_logger)
                message_id = message_ids[0] if message_ids else None  # For compatibility
            except Exception as e:
                logger.error("Failed to send message to queue: %s", e)
                raise QueueError(
                    f"Failed to send message to queue: {str(e)}",
                    queue_name=self.config.uw_uploaded_docs_queue
                )
            
            # Calculate processing time and update metrics
            processing_time_ms = int((time.perf_counter() - start_time) * 1000)
            self._update_metrics(True, processing_time_ms)
            
            webhook_logger.info(f"webhook.success contact={payload.contact_id} docs={len(message_ids)} duration_ms={processing_time_ms}")
            
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
                "webhook.validation_failed error=%s", str(e)
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
                "webhook.queue_error error=%s", str(e)
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
                "webhook.error type=%s error=%s", type(e).__name__, str(e)
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
    
    async def _create_and_send_messages(self, payload: WebhookPayload, correlation_id: str, webhook_logger) -> List[str]:
        """Create and send queue messages based on webhook type."""
        message_ids = []
        
        if payload.webhook_type == WebhookType.CLIENT_SUBMITTED:
            # For CLIENT_SUBMITTED: process all documents
            doc_ids = self._extract_all_doc_ids(payload.doc_id)
            
            webhook_logger.debug(f"queue.batch_create docs={len(doc_ids)}")
            
            for i, doc_id in enumerate(doc_ids):
                message = QueueMessage(
                    message_type=MessageType.CONTRACT_DOWNLOAD,
                    contact_id=payload.contact_id,
                    correlation_id=f"{correlation_id}-doc{i+1}",
                    data={
                        "doc_id": doc_id,
                        "doc_title": payload.doc_title,
                        "file_type": payload.file_type,
                        "timestamp": payload.timestamp,
                        "webhook_version": payload.webhook_version,
                        "webhook_source": payload.source.value,
                        "webhook_type": payload.webhook_type.value,
                        "raw_data": payload.raw_data,
                    }
                )
                
                message_id = await self.queue_adapter.send_message(message)
                message_ids.append(message_id)
                        
        else:
            # For DOCUMENT_UPLOADED: process single document (existing behavior)
            message = QueueMessage(
                message_type=MessageType.CONTRACT_DOWNLOAD,
                contact_id=payload.contact_id,
                correlation_id=correlation_id,
                data={
                    "doc_id": payload.doc_id,
                    "doc_title": payload.doc_title,
                    "file_type": payload.file_type,
                    "timestamp": payload.timestamp,
                    "webhook_version": payload.webhook_version,
                    "webhook_source": payload.source.value,
                    "webhook_type": payload.webhook_type.value,
                    "raw_data": payload.raw_data,
                }
            )
            
            message_id = await self.queue_adapter.send_message(message)
            message_ids.append(message_id)
            
            webhook_logger.bind(
                webhook_type=payload.webhook_type.value,
                message_id=message_id
            ).debug("📤 Queued single document")
        
        return message_ids
    
    def _extract_all_doc_ids(self, doc_id_string: str) -> List[str]:
        """Extract all document IDs from comma-separated string."""
        if "," in doc_id_string:
            return [doc_id.strip() for doc_id in doc_id_string.split(",") if doc_id.strip()]
        return [doc_id_string]