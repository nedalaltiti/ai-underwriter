# services/document-downloader/src/services/worker.py
import asyncio
import json
from typing import Dict, Any, Optional
from datetime import datetime, UTC
from loguru import logger

from config import DocumentConfig
from core.downloader import DocumentDownloader
from models.download import DownloadTask, DownloadStatus, DownloadResult
from libs.forth_shared.models.queue import QueueMessage, MessageType
from libs.forth_shared.adapters.queue import SQSAdapter
from utils.error_classification import is_permanent_failure, is_successful_completion
from utils.processing_monitor import processing_monitor


class DownloadWorker:
    """Worker for processing download tasks from queue."""
    
    def __init__(self, config: DocumentConfig, downloader: DocumentDownloader):
        self.config = config
        self.downloader = downloader
        self.running = False
        self.shutdown_event = asyncio.Event()
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._semaphore = asyncio.Semaphore(config.worker_concurrency)
        
        # Initialize queue adapters
        endpoint_url = None
        if hasattr(config, 'get_aws_endpoint_url') and callable(getattr(config, 'get_aws_endpoint_url')):
            endpoint_url = config.get_aws_endpoint_url()
            
        self.input_queue = SQSAdapter(
            queue_name=config.input_queue_name,
            region=config.aws_region,
            endpoint_url=endpoint_url
        )
        
        # Only initialize output queue if configured
        self.output_queue = None
        if config.output_queue_name:
            self.output_queue = SQSAdapter(
                queue_name=config.output_queue_name,
                region=config.aws_region,
                endpoint_url=endpoint_url
            )
    
    @property
    def active_downloads(self) -> int:
        """Get number of active downloads."""
        return len([t for t in self._active_tasks.values() if not t.done()])
    
    async def run(self):
        """Main worker loop."""
        self.running = True
        logger.info(f"🔄 Download worker started (concurrency: {self.config.worker_concurrency})")
        
        try:
            while self.running and not self.shutdown_event.is_set():
                await self._process_batch()
                
                # Short sleep between batches
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Worker error: {e}")
            raise
        finally:
            self.running = False
            logger.info("🛑 Download worker stopped")
    
    async def stop(self):
        """Stop the worker gracefully."""
        logger.info("🛑 Stopping download worker...")
        self.running = False
        self.shutdown_event.set()
        
        # Wait for any active downloads to complete (with timeout)
        if hasattr(self, 'active_downloads') and self.active_downloads > 0:
            logger.info(f"Waiting for {self.active_downloads} active downloads to complete...")
            for _ in range(30):  # Wait up to 30 seconds
                if self.active_downloads == 0:
                    break
                await asyncio.sleep(1)
        
        # Clean up any remaining async resources
        await asyncio.sleep(0.1)
    
    async def _process_batch(self):
        """Process a batch of messages."""
        try:
            # Attempt to receive messages (this will lazily initialize the SQS client
            # and resolve the queue URL on the first run). Any connectivity issues
            # will be caught and retried with back-off below.

            messages = await self.input_queue.receive_messages(
                max_messages=self.config.worker_concurrency
            )
            
            if not messages:
                return
            
            logger.info(f"📦 Processing {len(messages)} download tasks")
            
            # Process messages concurrently
            tasks = []
            for message in messages:
                task = asyncio.create_task(
                    self._process_message(message)
                )
                tasks.append(task)
            
            # Wait for all tasks
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Log results
            successes = sum(1 for r in results if r is True)
            failures = len(results) - successes
            
            if failures > 0:
                logger.warning(f"Batch completed: {successes} success, {failures} failed")
            else:
                # Reset error count on successful batch
                self._error_count = 0
            
            # Log periodic processing summary
            processing_monitor.log_periodic_summary()
            
            # Clean up old monitoring entries
            processing_monitor.cleanup_old_entries()
            
        except Exception as e:
            logger.error(f"Batch processing error: {e}")

            # If the queue hasn't been created yet or credentials/region are wrong,
            # the first connection attempt will raise here. We back-off and retry
            # instead of exiting the worker loop.

            await asyncio.sleep(min(30, 2 ** getattr(self, '_error_count', 0)))
            self._error_count = getattr(self, '_error_count', 0) + 1
    
    def _is_test_message(self, task: DownloadTask) -> bool:
        """Check if this is a test message that should be skipped."""
        # Common test patterns
        test_patterns = [
            # Postman/curl test data
            ("12345", "678"),
            ("12345", "67890"), 
            # Generic test data
            ("test_contact", "test_doc"),
            ("dev_contact", "dev_doc"),
            # Numeric test patterns
            ("123", "456"),
            ("1", "1"),
        ]
        
        current_pair = (task.contact_id, task.doc_id)
        
        # Check for exact matches
        if current_pair in test_patterns:
            return True
            
        # Check for test-like correlation IDs
        if task.correlation_id and any(test_word in task.correlation_id.lower() 
                                     for test_word in ["test", "dev", "mock", "sample"]):
            return True
            
        # Check for very short IDs (likely test data)
        if len(task.contact_id) <= 3 and len(task.doc_id) <= 3:
            return True
            
        return False
    
    def _is_confirmed_document_not_found(self, result) -> bool:
        """
        Determine if this is a confirmed 404 (document truly doesn't exist)
        vs a temporary API issue that might have returned a 404-like response.
        """
        error_message = result.error_message or ""
        
        # Indicators of a TRUE 404 (safe to delete)
        confirmed_not_found_indicators = [
            "Document not found: ",  # Our specific error message format
            "404",                   # HTTP status in message
            "not found",            # Clear "not found" language
        ]
        
        # Indicators of possible API issues (should go to DLQ)
        api_issue_indicators = [
            "timeout",
            "connection",
            "network",
            "authentication",
            "unauthorized",
            "forbidden",
            "server error",
            "503",
            "502", 
            "500",
            "gateway",
        ]
        
        error_lower = error_message.lower()
        
        # Check for API issues first (these override "not found")
        for indicator in api_issue_indicators:
            if indicator in error_lower:
                logger.debug(f"🔍 API issue indicator found: {indicator}")
                return False  # Not confirmed - might be API issue
        
        # Check for confirmed not found indicators
        for indicator in confirmed_not_found_indicators:
            if indicator in error_lower:
                logger.debug(f"🔍 Confirmed not found indicator: {indicator}")
                return True  # Confirmed 404
        
        # Default: if uncertain, err on the side of caution (send to DLQ)
        logger.debug(f"🔍 Uncertain error type: {error_message}")
        return False
    
    async def _process_message(self, message: Dict[str, Any]) -> bool:
        """Process a single message."""
        receipt_handle = message.get("ReceiptHandle")
        
        try:
            # Parse message body
            body = json.loads(message["Body"])
            
            # Try to parse as QueueMessage or convert from webhook format
            queue_message = self._parse_queue_message(body)
            
            if not queue_message:
                logger.warning(f"Unable to parse message format: {body}")
                await self.input_queue.delete_message(receipt_handle)
                return False
            
            # Only process download messages
            if queue_message.message_type != MessageType.CONTRACT_DOWNLOAD:
                logger.warning(f"Unexpected message type: {queue_message.message_type}")
                await self.input_queue.delete_message(receipt_handle)
                return False
            
            # Create download task with validation
            try:
                task = DownloadTask.from_queue_message(queue_message)
            except ValueError as e:
                # Invalid message format - send to DLQ immediately
                # Escape curly braces in error message to prevent logging formatter conflicts
                error_msg = str(e).replace('{', '{{').replace('}', '}}')
                logger.bind(
                    correlation_id=queue_message.correlation_id,
                    contact_id=queue_message.contact_id
                ).error(f"❌ Invalid message format - sending to DLQ: {error_msg}")
                
                await self.input_queue.send_to_dlq(
                    message=queue_message,
                    error=f"Invalid message format: {str(e)}"
                )
                await self.input_queue.delete_message(receipt_handle)
                return False
            
            # Check for test messages and handle gracefully
            if self._is_test_message(task):
                logger.bind(
                    contact_id=task.contact_id,
                    doc_id=task.doc_id,
                    correlation_id=task.correlation_id
                ).info(
                    f"🧪 Test message detected - skipping processing: contact_id={task.contact_id}, doc_id={task.doc_id}"
                )
                # Delete test message to prevent retries
                await self.input_queue.delete_message(receipt_handle)
                return True
            
            # Record processing start for monitoring
            processing_monitor.record_processing_start(
                contact_id=task.contact_id,
                doc_id=task.doc_id,
                correlation_id=task.correlation_id
            )
            
            logger.bind(
                contact_id=task.contact_id,
                doc_id=task.doc_id,
                correlation_id=task.correlation_id,
                doc_type=task.doc_type
            ).info(
                f"📥 Downloading document: contact_id={task.contact_id}, doc_id={task.doc_id}"
            )
            
            # Download document
            result = await self.downloader.download_document(task)
            
            if result.success:
                # Record successful processing
                processing_monitor.record_processing_result(
                    contact_id=task.contact_id,
                    doc_id=task.doc_id,
                    success=True
                )
                
                # Queue for parsing
                await self._queue_for_parsing(task, result)
                
                # Delete message
                await self.input_queue.delete_message(receipt_handle)
                
                logger.bind(
                    contact_id=task.contact_id,
                    doc_id=task.doc_id,
                    s3_key=result.s3_key,
                    processing_time_ms=result.processing_time_ms
                ).info(
                    f"✅ Download completed: {task.doc_id} -> {result.s3_key}"
                )
                return True
            else:
                # Use utility function to check if this is a permanent failure
                if is_permanent_failure(result):
                    # Don't retry permanent failures - send directly to DLQ or delete
                    if is_successful_completion(result):
                        # Skipped documents are successful, just delete the message
                        await self.input_queue.delete_message(receipt_handle)
                        logger.bind(
                            contact_id=task.contact_id,
                            doc_id=task.doc_id,
                            error_code=result.error_code
                        ).info(f"✅ Document skipped: {result.error_message}")
                        return True
                    else:
                        # Record permanent failure
                        processing_monitor.record_permanent_failure(
                            contact_id=task.contact_id,
                            doc_id=task.doc_id,
                            error_message=result.error_message or "Unknown permanent failure"
                        )
                        
                        # Handle different types of permanent failures differently
                        if result.error_code == "DOCUMENT_NOT_FOUND":
                            # Check if this is a confirmed 404 (document truly doesn't exist)
                            # vs a temporary API issue (network/auth error that returned 404-like response)
                            if self._is_confirmed_document_not_found(result):
                                # True 404 from Forth API - document doesn't exist, safe to delete
                                await self.input_queue.delete_message(receipt_handle)
                                logger.bind(
                                    contact_id=task.contact_id,
                                    doc_id=task.doc_id,
                                    error_code=result.error_code
                                ).info(f"📄 Document confirmed not found - message deleted: {task.doc_id}")
                                return True  # Treated as successful (message handled)
                            else:
                                # Uncertain 404 (might be API issue) - send to DLQ for manual review
                                await self.input_queue.send_to_dlq(
                                    message=queue_message,
                                    error=f"Uncertain document not found (possible API issue): {result.error_message}"
                                )
                                await self.input_queue.delete_message(receipt_handle)
                                logger.bind(
                                    contact_id=task.contact_id,
                                    doc_id=task.doc_id,
                                    error_code=result.error_code
                                ).warning(f"⚠️ Uncertain document not found - sent to DLQ for review: {result.error_message}")
                                return False
                        else:
                            # Other permanent failures still go to DLQ for investigation
                            await self.input_queue.send_to_dlq(
                                message=queue_message,
                                error=result.error_message
                            )
                            await self.input_queue.delete_message(receipt_handle)
                            logger.bind(
                                contact_id=task.contact_id,
                                doc_id=task.doc_id,
                                error_code=result.error_code
                            ).warning(f"❌ Permanent failure - sent to DLQ: {result.error_message}")
                            return False
                
                # Handle retryable failures
                elif queue_message.retry_count >= self.config.max_retries:
                    # Send to DLQ after max retries
                    await self.input_queue.send_to_dlq(
                        message=queue_message,
                        error=result.error_message
                    )
                    await self.input_queue.delete_message(receipt_handle)
                    logger.bind(
                        contact_id=task.contact_id,
                        doc_id=task.doc_id,
                        retry_count=queue_message.retry_count
                    ).error(f"❌ Download failed after {queue_message.retry_count} retries: {result.error_message}")
                else:
                    # Extend visibility timeout for retry
                    await self.input_queue.change_message_visibility(
                        receipt_handle=receipt_handle,
                        visibility_timeout=self.config.retry_delay
                    )
                    logger.bind(
                        contact_id=task.contact_id,
                        doc_id=task.doc_id,
                        retry_count=queue_message.retry_count,
                        max_retries=self.config.max_retries
                    ).warning(f"⚠️ Download failed, will retry ({queue_message.retry_count + 1}/{self.config.max_retries}): {result.error_message}")
                
                return False
                
        except Exception as e:
            logger.error(f"Message processing error: {e}")
            
            # Try to delete the problematic message to prevent infinite processing
            try:
                await self.input_queue.delete_message(receipt_handle)
                logger.info(f"Deleted problematic message to prevent infinite reprocessing")
            except Exception as delete_error:
                logger.error(f"Failed to delete problematic message: {delete_error}")
            
            return False
    
    def _parse_queue_message(self, body: Dict[str, Any]) -> Optional[QueueMessage]:
        """Parse message body into QueueMessage, handling different formats."""
        try:
            # Method 1: Try to parse as standard QueueMessage
            if "message_type" in body and "contact_id" in body:
                return QueueMessage(**body)
            
            # Method 2: Handle webhook data format (from webhook-ingestion)
            if "doc_id" in body and "contact_id" in body:
                # Convert webhook format to QueueMessage
                correlation_id = body.get("correlation_id") or f"download-{datetime.now(UTC).timestamp()}"
                return QueueMessage(
                    message_type=MessageType.CONTRACT_DOWNLOAD,
                    contact_id=str(body["contact_id"]),
                    correlation_id=correlation_id,
                    data={
                        "doc_id": str(body["doc_id"]),
                        "doc_type": body.get("doc_type", "agreement"),
                        "doc_name": body.get("doc_name"),
                        "webhook_source": body.get("source", "unknown"),
                        "raw_data": body
                    }
                )
            
            # Method 3: Check for nested message (SQS might wrap our message)
            if "Message" in body:
                nested_body = json.loads(body["Message"])
                return self._parse_queue_message(nested_body)
            
            # Method 4: Check for Records array (SQS event format)
            if "Records" in body and isinstance(body["Records"], list):
                for record in body["Records"]:
                    if "body" in record:
                        nested_body = json.loads(record["body"])
                        return self._parse_queue_message(nested_body)
            
            # Log the unrecognized format for debugging
            logger.warning(f"Unrecognized message format. Keys: {list(body.keys())}")
            logger.debug(f"Full message body: {body}")
            return None
            
        except Exception as e:
            logger.error(f"Error parsing queue message: {e}")
            logger.debug(f"Problematic message body: {body}")
            return None
    
    async def _queue_for_parsing(self, task: DownloadTask, result: DownloadResult):
        """Queue document for parsing."""
        # Skip queuing if output queue is not configured
        if not self.output_queue:
            logger.debug("No output queue configured, skipping parsing queue")
            return
            
        try:
            parse_message = QueueMessage(
                message_type=MessageType.DOCUMENT_PARSE,
                contact_id=task.contact_id,
                correlation_id=task.correlation_id,
                data={
                    "doc_id": task.doc_id,
                    "doc_type": task.doc_type,
                    "doc_name": task.doc_name,
                    "s3_key": result.s3_key,
                    "s3_url": result.s3_url,
                    "file_size": result.file_size,
                    "content_type": result.content_type,
                    "download_timestamp": datetime.now(UTC).isoformat()
                }
            )
            
            await self.output_queue.send_message(parse_message)
            logger.debug(f"📤 Queued for parsing: {result.s3_key}")
            
        except Exception as e:
            logger.warning(f"Failed to queue for parsing (queue may not exist): {e}")
            # Don't raise the exception since this is not critical for the download process
            # The document has been successfully downloaded and stored in S3