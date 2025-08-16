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
from core.validator import UnderwritingValidator
from integrations.gemini import GeminiClient
from models.extraction import ProcessingTask, ProcessingStatus
from utils.logging import get_logger, setup_logging
from utils.metrics import metrics_tracker

logger = get_logger(__name__)


class DocumentWorker:
    """Background worker for processing documents from SQS."""
    
    def __init__(self):
        """Initialize the worker."""
        self.running = False
        self.sqs_client = None
        self.s3_client = None
        self.processor = None
        self.validator = None
        self.sqs_adapter = None  # Add SQS adapter for DLQ support
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
            logger.error("AWS credentials not found")
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
            
            # Initialize processor and validator
            self.processor = DocumentProcessor(gemini_client)
            self.validator = UnderwritingValidator()
            
            logger.info("Document processor and validator initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize processors: {e}")
            raise
    
    async def start(self):
        """Start the worker."""
        logger.info("🔄 Starting document processing worker")
        logger.info(f"Input queue: {config.input_queue_name}")
        logger.info(f"Worker concurrency: {config.worker_concurrency}")
        
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
            logger.info("🛑 Document processing worker stopped")
    
    async def _process_messages_loop(self, worker_id: str):
        """Main message processing loop for a worker."""
        logger.info(f"Worker {worker_id} started")
        
        while self.running:
            try:
                # Get queue URL
                queue_url = await self._get_queue_url()
                if not queue_url:
                    await asyncio.sleep(30)  # Wait before retrying
                    continue
                
                # Receive messages
                messages = await self._receive_messages(queue_url)
                
                if not messages:
                    await asyncio.sleep(1)  # Short sleep when no messages
                    continue
                
                # Process each message
                for message in messages:
                    try:
                        await self._process_message(message, queue_url, worker_id)
                    except Exception as e:
                        logger.error(f"Worker {worker_id} failed to process message: {e}")
                        
            except Exception as e:
                logger.error(f"Worker {worker_id} loop error: {e}")
                await asyncio.sleep(5)  # Wait before retrying
        
        logger.info(f"Worker {worker_id} stopped")
    
    async def _get_queue_url(self) -> Optional[str]:
        """Get SQS queue URL."""
        try:
            response = self.sqs_client.get_queue_url(QueueName=config.input_queue_name)
            return response['QueueUrl']
        except ClientError as e:
            if e.response['Error']['Code'] == 'AWS.SimpleQueueService.NonExistentQueue':
                logger.error(f"Queue does not exist: {config.input_queue_name}")
            else:
                logger.error(f"Failed to get queue URL: {e}")
            return None
    
    async def _receive_messages(self, queue_url: str) -> list:
        """Receive messages from SQS queue."""
        try:
            response = self.sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=config.sqs_max_messages,
                WaitTimeSeconds=config.sqs_wait_time,
                VisibilityTimeout=config.processing_timeout,
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
                logger.info(f"Worker {worker_id} processing document-downloader message: {doc_id}")
                
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
                logger.info(f"Worker {worker_id} processing direct message: {doc_id}")
            
            # Process document
            result = await self.processor.process_document(task)
            
            # Validate if successful
            if result.extracted_document:
                validation_results = self.validator.validate_document(result.extracted_document)
                logger.info(f"Document {task.doc_id} validated with {len(validation_results)} checks")
            
            # Store results in database
            await self._store_processing_result(task, result, worker_id)
            
            # Delete message from queue
            await self._delete_message(queue_url, receipt_handle)
            
            logger.info(f"✅ Worker {worker_id} completed processing: {task.doc_id}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in message: {e}")
            await self._delete_message(queue_url, receipt_handle)  # Remove invalid message
            
        except Exception as e:
            logger.error(f"Worker {worker_id} processing error: {e}")
            
            # Get message attributes for retry count
            attributes = message.get('Attributes', {})
            receive_count = int(attributes.get('ApproximateReceiveCount', '1'))
            max_retries = 3  # Configure max retries
            
            # Check if we should retry or send to DLQ
            if receive_count >= max_retries:
                # Send to DLQ
                logger.warning(f"Worker {worker_id}: Processing failed after {receive_count} attempts for {doc_id or 'unknown'}, sending to DLQ")
                
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
            else:
                # Let message return to queue for retry (visibility timeout will expire)
                logger.info(f"Worker {worker_id}: Processing failed for {doc_id or 'unknown'}, attempt {receive_count}/{max_retries}, will retry")
                # Don't delete message - let it be retried when visibility timeout expires
    
    async def _store_processing_result(self, task: ProcessingTask, result, worker_id: str):
        """Store processing result to database."""
        try:
            from integrations.database import UnderwritingDatabaseAdapter
            
            # Initialize database adapter with config
            db_adapter = UnderwritingDatabaseAdapter(config)
            await db_adapter.initialize()
            
            try:
                # Check if processing was successful and we have extracted data
                if result.status.value == "completed" and hasattr(result, 'extracted_document') and result.extracted_document:
                    # If we have an ExtractedDocumentPackage, store it directly
                    if hasattr(result.extracted_document, 'file_id'):
                        success = await db_adapter.store_document_package(result.extracted_document)
                        
                        if success:
                            logger.info(f"Worker {worker_id}: Successfully stored document package for {task.doc_id}")
                        else:
                            logger.error(f"Worker {worker_id}: Failed to store document package for {task.doc_id}")
                    else:
                        logger.warning(f"Worker {worker_id}: Extracted document for {task.doc_id} is not a valid package")
                else:
                    logger.warning(f"Worker {worker_id}: Processing failed or no data extracted for {task.doc_id}, status: {result.status.value}")
                    
            finally:
                await db_adapter.close()
                
        except Exception as e:
            logger.error(f"Worker {worker_id}: Database storage error for {task.doc_id}: {e}")
            # Don't raise - we don't want to fail message processing due to storage issues
    
    async def _delete_message(self, queue_url: str, receipt_handle: str):
        """Delete processed message from queue."""
        try:
            self.sqs_client.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle
            )
        except Exception as e:
            logger.error(f"Failed to delete message: {e}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    def stop(self):
        """Stop the worker."""
        logger.info("Stopping worker...")
        self.running = False


async def main():
    """Main worker entry point."""
    setup_logging()
    
    logger.info("🚀 Starting document-parser worker")
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
        worker.stop()


if __name__ == "__main__":
    asyncio.run(main())