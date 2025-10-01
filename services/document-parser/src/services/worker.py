# services/document-parser/src/services/worker.py
"""Background worker for processing documents from SQS queue."""

import asyncio
import json
import signal
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from config import config
from core.processor import DocumentProcessor
from integrations.gemini import GeminiClient
from models.extraction import ProcessingTask
from utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


class DocumentWorker:
    """Background worker for processing documents from SQS."""
    
    def __init__(self):
        """Initialize the worker."""
        self.running = False
        self.sqs_client = None
        self.s3_client = None
        self.processor = None
        self.sqs_adapter = None  # Add SQS adapter for DLQ support
        self.db_adapter = None  # Shared database adapter (singleton per worker)
        self._setup_aws_clients()
        self._setup_processors()
        
    def _setup_aws_clients(self):
        """Setup AWS clients for SQS and S3."""
        try:
            session = boto3.Session(region_name=config.aws_region)
            
            # SQS client
            if config.aws_endpoint_url:
                self.sqs_client = session.client('sqs', endpoint_url=config.aws_endpoint_url)
            else:
                self.sqs_client = session.client('sqs')
                
            # S3 client  
            if config.aws_endpoint_url:
                self.s3_client = session.client('s3', endpoint_url=config.aws_endpoint_url)
            else:
                self.s3_client = session.client('s3')
            
            # Setup SQS adapter for DLQ support
            from libs.forth_shared.adapters.queue import SQSAdapter
            self.sqs_adapter = SQSAdapter(
                queue_name=config.input_queue_name,
                region=config.aws_region,
                endpoint_url=config.aws_endpoint_url if config.aws_endpoint_url else None
            )
                
            logger.info("AWS clients initialized successfully")
            
        except NoCredentialsError:
            logger.error("AWS credentials not found - check AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables")
            raise
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'InvalidClientTokenId':
                logger.error("AWS credentials are invalid or expired - check AWS credentials configuration")
            else:
                logger.error(f"AWS client error ({error_code}): {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize AWS clients: {e}")
            raise
    
    def _setup_processors(self):
        """Setup document processor and validator."""
        try:
            # Initialize Gemini client
            service_account_info = config.get_gemini_service_account_dict()
            gemini_client = GeminiClient(service_account_info)
            
            # Initialize processor
            self.processor = DocumentProcessor(gemini_client)
            
            logger.info("Document processor and validator initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize processor: {e}")
            raise
    
    async def _setup_database(self):
        """Setup shared database adapter (singleton per worker process)."""
        try:
            from integrations.database.adapter import UnderwritingDatabaseAdapter
            
            self.db_adapter = UnderwritingDatabaseAdapter()
            await self.db_adapter.initialize()
            
            # Inject the shared adapter into the processor
            self.processor.db_adapter = self.db_adapter
            
            logger.info("db.worker_adapter_initialized")
            
        except Exception as e:
            logger.bind(error=type(e).__name__, detail=str(e)[:200]).error("db.worker_adapter_failed")
            raise
    
    async def start(self):
        """Start the worker."""
        logger.bind(service="document-parser").info("worker.startup")
        logger.bind(
            service="document-parser",
            queue=config.input_queue_name,
            concurrency=config.worker_concurrency
        ).info("worker.config")
        
        # Initialize shared database adapter (once per worker process)
        await self._setup_database()
        
        self.running = True
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Start processing tasks
        tasks = []
        for i in range(config.worker_concurrency):
            task = asyncio.create_task(self._process_messages_loop(f"worker-{i}"))
            tasks.append(task)
            
        logger.info(f"Started {len(tasks)} worker tasks")
        
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Worker tasks cancelled")
        finally:
            logger.bind(service="document-parser").info("worker.stopped")
    
    async def _process_messages_loop(self, worker_id: str):
        """Main message processing loop for a worker."""
        logger.bind(
            service="document-parser", 
            worker_id=worker_id,
            queue=config.input_queue_name
        ).info("worker.ready")
        
        while self.running:
            try:
                # CRITICAL: Yield control to event loop (allows health checks to run)
                await asyncio.sleep(0)
                
                # Get queue URL
                queue_url = await self._get_queue_url()
                if not queue_url:
                    await asyncio.sleep(30)  # Wait before retrying
                    continue
                
                # Receive messages
                messages = await self._receive_messages(queue_url)
                
                if not messages:
                    await asyncio.sleep(5)  # Use longer sleep when no messages (was 1)
                    continue
                
                # Process each message
                for message in messages:
                    try:
                        # CRITICAL: Yield control between messages
                        await asyncio.sleep(0)
                        
                        # Add timeout to prevent hanging
                        await asyncio.wait_for(
                            self._process_message(message, queue_url, worker_id),
                            timeout=900  # 15 minutes max per documen
                        )
                    except asyncio.TimeoutError:
                        # Extract contact/doc info for better logging
                        contact_id = "unknown"
                        doc_id = "unknown"
                        try:
                            body = json.loads(message.get("Body", "{}"))
                            contact_id = body.get("contact_id", "unknown")
                            doc_data = body.get("data", {})
                            doc_id = doc_data.get("doc_id", "unknown")
                        except:
                            pass
                        
                        logger.bind(
                            service="document-parser",
                            worker_id=worker_id,
                            contact_id=contact_id,
                            doc_id=doc_id,
                            timeout_minutes=15
                        ).error("worker.processing_timeout")
                        
                        # Delete the timed-out message to prevent infinite reprocessing
                        try:
                            receipt_handle = message.get("ReceiptHandle")
                            if receipt_handle:
                                await self._delete_message(queue_url, receipt_handle)
                                logger.bind(contact_id=contact_id, doc_id=doc_id).info("worker.timeout_deleted")
                        except Exception as delete_error:
                            logger.error(f"Failed to delete timed-out message: {delete_error}")
                    except Exception as e:
                        logger.bind(
                            service="document-parser",
                            worker_id=worker_id,
                            error=type(e).__name__
                        ).error("worker.message_failed")
                        
            except Exception as e:
                logger.error(f"Worker {worker_id} loop error: {e}")
                await asyncio.sleep(5)  # Wait before retrying
        
        logger.info(f"Worker {worker_id} stopped")
    
    async def _get_queue_url(self) -> Optional[str]:
        """Get SQS queue URL."""
        try:
            # Use asyncio.to_thread to prevent blocking event loop
            response = await asyncio.to_thread(
                self.sqs_client.get_queue_url,
                QueueName=config.input_queue_name
            )
            return response['QueueUrl']
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'AWS.SimpleQueueService.NonExistentQueue':
                logger.error(f"Queue does not exist: {config.input_queue_name}")
            elif error_code == 'InvalidClientTokenId':
                logger.error(f"AWS credentials invalid/expired when accessing queue: {config.input_queue_name}")
            elif error_code == 'AccessDenied':
                logger.error(f"AWS permissions denied for queue: {config.input_queue_name}")
            else:
                logger.error(f"Failed to get queue URL ({error_code}): {e}")
            return None
    
    async def _receive_messages(self, queue_url: str) -> list:
        """Receive messages from SQS queue."""
        try:
            # Use asyncio.to_thread to prevent blocking event loop
            response = await asyncio.to_thread(
                self.sqs_client.receive_message,
                QueueUrl=queue_url,
                MaxNumberOfMessages=config.sqs_max_messages,
                WaitTimeSeconds=config.sqs_wait_time,
                VisibilityTimeout=config.sqs_visibility_timeout,
                AttributeNames=['All']  # Include message attributes for retry count
            )
            return response.get('Messages', [])
        except Exception as e:
            logger.error(f"Failed to receive messages: {e}")
            return []
    
    async def _process_message(self, message: Dict[str, Any], queue_url: str, worker_id: str):
        """Process a single SQS message."""
        receipt_handle = message['ReceiptHandle']
        
        try:
            # Parse message body
            body = json.loads(message['Body'])
            
            # Handle different message formats
            # Format 1: Direct from document-downloader (structured message)
            if 'message_type' in body and 'data' in body:
                data = body['data']
                contact_id = body.get('contact_id') or ''
                doc_id = data.get('doc_id') or 'unknown'
                
                task = ProcessingTask(
                    task_id=uuid4(),
                    document_url=(data.get('s3_url') or ''),  # Use s3_url from document-downloader
                    s3_key=(data.get('s3_key') or ''),
                    contact_id=contact_id or '',
                    doc_id=doc_id or 'unknown',
                    received_at=datetime.now(),
                    metadata={
                        'file_size': data.get('file_size'),
                        'content_type': data.get('content_type'),
                        'download_timestamp': data.get('download_timestamp'),
                        'message_type': body.get('message_type'),
                        **data
                    }
                )
                logger.info(f"parse.start worker={worker_id} contact={contact_id} doc={doc_id}")
                
            # Format 2: Direct API call or legacy format (flat structure)
            else:
                doc_id = body.get('doc_id') or 'unknown'
                task = ProcessingTask(
                    task_id=uuid4(),
                    document_url=(body.get('document_url') or ''),
                    s3_key=(body.get('s3_key') or ''),
                    contact_id=(body.get('contact_id') or ''),
                    doc_id=doc_id or 'unknown',
                    received_at=datetime.now(),
                    metadata=body.get('metadata', {})
                )
                logger.info(f"parse.start worker={worker_id} contact={body.get('contact_id', 'unknown')} doc={doc_id}")
            
            # Extend message visibility for long processing (prevent redelivery)
            try:
                await self._extend_message_visibility(queue_url, receipt_handle, 900)  # 15 minutes
                logger.bind(contact_id=task.contact_id, doc_id=task.doc_id).debug("parse.visibility_extended")
            except Exception as e:
                logger.warning(f"Failed to extend message visibility: {e}")
            
            # Process document
            result = await self.processor.process_document(task)
            
            await self._log_processing_result(task, result, worker_id)
            
            # Delete message from queue
            await self._delete_message(queue_url, receipt_handle)
            logger.bind(
                contact_id=task.contact_id,
                doc_id=task.doc_id,
                worker_id=worker_id
            ).debug("parse.message_deleted")
            
            logger.bind(
                service="document-parser",
                worker_id=worker_id,
                contact_id=task.contact_id,
                doc_id=task.doc_id,
                status=result.status.value,
            ).info("parse.completed")
            
        except json.JSONDecodeError as e:
            logger.error(f"parse.invalid_json worker={worker_id} error={str(e)}")
            await self._delete_message(queue_url, receipt_handle)  # Remove invalid message
            
        except Exception as e:
            logger.error(f"parse.error worker={worker_id} doc={doc_id or 'unknown'} error={type(e).__name__}")
            
            # Get message attributes for retry count
            attributes = message.get('Attributes', {})
            receive_count = int(attributes.get('ApproximateReceiveCount', '1'))
            max_retries = 3  # Configure max retries
            
            # Check for permanent failures that shouldn't be retried
            from core.exceptions import NonRetryableError
            is_permanent = isinstance(e, NonRetryableError) or isinstance(e.__cause__, NonRetryableError)
            
            # Send to DLQ if max retries reached OR permanent error
            if receive_count >= max_retries or is_permanent:
                # Send to DLQ
                reason = "permanent_error" if is_permanent else "max_retries"
                logger.info(f"parse.dlq worker={worker_id} doc={doc_id or 'unknown'} attempts={receive_count} reason={reason}")
                
                # Create QueueMessage for DLQ
                from libs.forth_shared.models.queue import QueueMessage, MessageType
                
                # Try to extract identifiers from the message context
                failed_contact_id = 'unknown'
                failed_data = {}
                failed_correlation_id = None
                
                try:
                    if 'body' in locals():
                        failed_data = body
                        failed_contact_id = body.get('contact_id', 'unknown')
                        failed_correlation_id = body.get('correlation_id')
                except:
                    pass
                
                # Use an existing enum value for failure notifications
                failed_message = QueueMessage(
                    message_type=MessageType.ERROR_NOTIFICATION,
                    contact_id=failed_contact_id or '0',
                    data={
                        **(failed_data or {}),
                        "error": str(e),
                        "worker_id": worker_id,
                    },
                    correlation_id=failed_correlation_id,
                    retry_count=receive_count
                )
                
                # Send to DLQ with error details
                await self.sqs_adapter.send_to_dlq(
                    message=failed_message,
                    error=f"Processing failed after {receive_count} attempts: {str(e)}"
                )
                
                # Delete from main queue to prevent blocking
                await self._delete_message(queue_url, receipt_handle)
                logger.info(f"parse.message_deleted worker={worker_id} doc={doc_id or 'unknown'} reason={reason}")
            else:
                # Let message return to queue for retry (visibility timeout will expire)
                logger.info(f"parse.retry worker={worker_id} doc={doc_id or 'unknown'} attempt={receive_count}/{max_retries}")
                # Don't delete message - let it be retried when visibility timeout expires
    
    async def _log_processing_result(self, task: ProcessingTask, result, worker_id: str):
        """Log processing result (storage already handled by processor)."""
        try:
            # Check if processing was successful and we have extracted data
            if result.status.value == "completed" and hasattr(result, 'extracted_document') and result.extracted_document:
                # If we have an ExtractedDocumentPackage, log success
                if hasattr(result.extracted_document, 'file_id'):
                    logger.bind(
                        service="document-parser",
                        worker_id=worker_id,
                        contact_id=task.contact_id,
                        doc_id=task.doc_id,
                    ).info("worker.processing_success")
                else:
                    logger.warning(f"parse.invalid_package worker={worker_id} contact={task.contact_id} doc={task.doc_id}")
            else:
                logger.warning(f"parse.no_data worker={worker_id} contact={task.contact_id} doc={task.doc_id} status={result.status.value}")
                
        except Exception as e:
            logger.error(f"worker.log_error worker={worker_id} contact={task.contact_id} doc={task.doc_id} error={type(e).__name__}")
    
    async def _extend_message_visibility(self, queue_url: str, receipt_handle: str, visibility_timeout: int):
        """Extend message visibility timeout to prevent redelivery during long processing."""
        try:
            await asyncio.to_thread(
                self.sqs_client.change_message_visibility,
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle,
                VisibilityTimeout=visibility_timeout
            )
        except Exception as e:
            logger.error(f"Failed to extend message visibility: {e}")

    async def _delete_message(self, queue_url: str, receipt_handle: str):
        """Delete processed message from queue."""
        try:
            # Use asyncio.to_thread to prevent blocking event loop
            await asyncio.to_thread(
                self.sqs_client.delete_message,
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle
            )
        except Exception as e:
            logger.error(f"Failed to delete message: {e}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.bind(
            service="document-parser",
            signal=signum,
            graceful=True
        ).info("worker.shutdown_signal")
        self.running = False
        
        # Schedule async cleanup
        if self.db_adapter:
            asyncio.create_task(self._cleanup_database())
    
    async def _cleanup_database(self):
        """Cleanup database resources."""
        if self.db_adapter:
            try:
                await self.db_adapter.close()
                logger.info("db.worker_adapter_closed")
            except Exception as e:
                logger.bind(error=str(e)).warning("db.worker_adapter_close_failed")
    
    async def stop(self):
        """Stop the worker and cleanup resources."""
        logger.bind(service="document-parser").info("worker.stopping")
        self.running = False
        
        # Close shared database adapter
        await self._cleanup_database()


async def main():
    """Main worker entry point."""
    setup_logging(
        service_name=config.service_name,
        log_level=config.log_level,
        log_format="text" if config.is_development() else "json"
    )
    
    logger.info("Starting document-parser worker")
    logger.info(f"Environment: {config.environment}")
    logger.info(f"Service version: {config.service_version}")
    
    worker = DocumentWorker()
    
    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.error(f"Worker failed: {e}")
        sys.exit(1)
    finally:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())