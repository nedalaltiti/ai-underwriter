#shared/forth_shared/adapters/queue.py
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import json
import asyncio
from datetime import datetime, UTC
from loguru import logger
from ..models.queue import QueueMessage
import time
import uuid


class QueueAdapter(ABC):
    """Abstract base class for queue operations."""
    
    def __init__(self, queue_name: str):
        self.queue_name = queue_name
        
        # Handle DLQ naming based on your actual queue naming convention
        if queue_name.endswith('.fifo'):
            # For FIFO queues: uw-uploaded-docs-dev-sqs.fifo -> uw-uploaded-docs-dl-dev-sqs.fifo
            base_name = queue_name.replace('.fifo', '')
            if '-dev-sqs' in base_name:
                self.dlq_name = base_name.replace('-dev-sqs', '-dl-dev-sqs') + '.fifo'
            elif '-prod-sqs' in base_name:
                self.dlq_name = base_name.replace('-prod-sqs', '-dl-prod-sqs') + '.fifo'
            else:
                # Fallback to standard naming
                self.dlq_name = f"{queue_name}-dlq"
        else:
            # Standard queues
            self.dlq_name = f"{queue_name}-dlq"
        
    @abstractmethod
    async def send_message(
        self, 
        message: QueueMessage,
        delay_seconds: int = 0
    ) -> str:
        """Send a message to the queue."""
        pass
    
    @abstractmethod
    async def receive_messages(
        self, 
        max_messages: int = 10,
        wait_time_seconds: int = 20
    ) -> List[Dict[str, Any]]:
        """Receive messages from the queue."""
        pass
    
    @abstractmethod
    async def delete_message(self, receipt_handle: str) -> bool:
        """Delete a message from the queue."""
        pass
    
    @abstractmethod
    async def change_message_visibility(
        self,
        receipt_handle: str,
        visibility_timeout: int
    ) -> bool:
        """Change message visibility timeout."""
        pass
    
    async def send_to_dlq(
        self, 
        message: QueueMessage,
        error: str
    ) -> Optional[str]:
        """Send failed message to DLQ."""
        message.original_queue = self.queue_name
        message.failure_reason = error
        message.failed_at = datetime.now(UTC)
        
        try:
            # Override queue name temporarily
            original_queue = self.queue_name
            self.queue_name = self.dlq_name
            message_id = await self.send_message(message)
            self.queue_name = original_queue
            
            logger.info(f"Message sent to DLQ: {message_id}")
            return message_id
        except Exception as e:
            logger.error(f"Failed to send to DLQ: {e}")
            return None


class SQSAdapter(QueueAdapter):
    """AWS SQS implementation of QueueAdapter."""
    
    def __init__(
        self,
        queue_name: str,
        region: str = "us-west-1",
        endpoint_url: Optional[str] = None,
        session = None
    ):
        super().__init__(queue_name)
        self.region = region
        self.endpoint_url = endpoint_url
        self._session = session
        self._queue_url = None
        self._client = None
        self._client_context = None
        
    async def _ensure_client(self):
        """Lazily initialize SQS client."""
        if not self._client:
            import aioboto3
            
            if not self._session:
                self._session = aioboto3.Session(region_name=self.region)
            
            # Create client context manager
            client_kwargs = {}
            if self.endpoint_url:
                client_kwargs["endpoint_url"] = self.endpoint_url
            self._client_context = self._session.client('sqs', **client_kwargs)
            self._client = await self._client_context.__aenter__()
            
            # Get queue URL
            try:
                response = await self._client.get_queue_url(QueueName=self.queue_name)
                self._queue_url = response['QueueUrl']
                logger.debug(f"🔗 SQS connected: {self.queue_name}")
            except Exception as e:
                logger.error(f"Failed to connect to SQS queue {self.queue_name}: {e}")
                raise
    
    async def close(self):
        """Close SQS client connection."""
        if self._client_context:
            try:
                await self._client_context.__aexit__(None, None, None)
                logger.info("SQS client connection closed")
            except Exception as e:
                logger.error(f"Error closing SQS client: {e}")
            finally:
                self._client = None
                self._client_context = None
                self._queue_url = None
            
    async def send_message(
        self, 
        message: QueueMessage,
        delay_seconds: int = 0
    ) -> str:
        """Send message to SQS."""
        await self._ensure_client()
        
        params = {
            'QueueUrl': self._queue_url,
            'MessageBody': json.dumps(message.to_sqs_format()),
            'MessageAttributes': {
                'message_type': {
                    'StringValue': message.message_type.value,
                    'DataType': 'String'
                },
                'priority': {
                    'StringValue': str(message.priority.value),
                    'DataType': 'Number'
                }
            }
        }
        
        if delay_seconds > 0:
            params['DelaySeconds'] = delay_seconds
        
        # Add FIFO queue parameters if the queue name ends with .fifo
        if self.queue_name.endswith('.fifo'):
            # Serialize all documents from the same webhook submission/contact
            # Use correlation_id (webhook batch) if present; otherwise fallback to contact_id
            correlation_id = getattr(message, 'correlation_id', None)
            message_group_id = str(correlation_id or message.contact_id)

            params['MessageGroupId'] = message_group_id

            # Deduplication: must be unique per document to avoid dropping docs in the same batch
            # Use correlation_id + doc_id (or generate UUID fallback)
            doc_id = None
            try:
                doc_id = str(message.data.get('doc_id')) if isinstance(message.data, dict) else None
            except Exception:
                doc_id = None
            
            if doc_id:
                dedup_id = f"{message_group_id}-{doc_id}"
            else:
                # Fallback to unique UUID to ensure no collision
                import uuid
                dedup_id = f"{message_group_id}-{uuid.uuid4()}"
            
            params['MessageDeduplicationId'] = dedup_id[:128]  # AWS limit is 128 chars

            # Enrich attributes for observability
            params['MessageAttributes'].update({
                'message_group_id': {'StringValue': message_group_id, 'DataType': 'String'},
                'message_dedup_id': {'StringValue': params['MessageDeduplicationId'], 'DataType': 'String'},
            })

            logger.debug(f"📤 SQS FIFO group={message_group_id} dedup={doc_id or 'uuid'} → {self.queue_name}")
            
        response = await self._client.send_message(**params)
        return response['MessageId']
    
    async def receive_messages(
        self, 
        max_messages: int = 10,
        wait_time_seconds: int = 20,
        visibility_timeout_seconds: int = None
    ) -> List[Dict[str, Any]]:
        """Receive messages from SQS."""
        await self._ensure_client()
        
        params = {
            'QueueUrl': self._queue_url,
            'MaxNumberOfMessages': min(max_messages, 10),
            'WaitTimeSeconds': wait_time_seconds,
            'MessageAttributeNames': ['All'],
            'AttributeNames': ['All']
        }
        
        # Add visibility timeout if specified
        if visibility_timeout_seconds is not None:
            params['VisibilityTimeout'] = visibility_timeout_seconds
            
        response = await self._client.receive_message(**params)
        
        return response.get('Messages', [])
    
    async def delete_message(self, receipt_handle: str) -> bool:
        """Delete message from SQS."""
        await self._ensure_client()
        
        try:
            await self._client.delete_message(
                QueueUrl=self._queue_url,
                ReceiptHandle=receipt_handle
            )
            return True
        except Exception as e:
            logger.error(f"Failed to delete message: {e}")
            return False
    
    async def change_message_visibility(
        self,
        receipt_handle: str,
        visibility_timeout: int
    ) -> bool:
        """Change message visibility timeout."""
        await self._ensure_client()
        
        try:
            await self._client.change_message_visibility(
                QueueUrl=self._queue_url,
                ReceiptHandle=receipt_handle,
                VisibilityTimeout=visibility_timeout
            )
            return True
        except Exception as e:
            logger.error(f"Failed to change visibility: {e}")
            return False