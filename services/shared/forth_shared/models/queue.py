# shared/forth_shared/models/queue.py
from enum import Enum
from datetime import datetime
from typing import Any, Optional, Dict
from pydantic import BaseModel, Field, field_validator
from .base import BaseTimestampModel


class MessageType(str, Enum):
    """Standardized message types for queue routing."""
    
    CONTRACT_DOWNLOAD = "contract_download"
    DOCUMENT_PARSE = "document_parse"
    VALIDATION_COMPLETE = "validation_complete"
    EXTRACTION_COMPLETE = "extraction_complete"
    ERROR_NOTIFICATION = "error_notification"


class MessagePriority(int, Enum):
    """Message priority levels."""
    
    CRITICAL = 1
    HIGH = 3
    NORMAL = 5
    LOW = 7
    BACKGROUND = 10


class QueueMessage(BaseTimestampModel):
    """Standardized queue message format."""
    
    message_type: MessageType
    contact_id: str = Field(..., min_length=1)
    correlation_id: Optional[str] = Field(default=None)
    trace_id: Optional[str] = Field(default=None)
    
    # Payload
    data: Dict[str, Any] = Field(default_factory=dict)
    
    # Message handling
    priority: MessagePriority = Field(default=MessagePriority.NORMAL)
    retry_count: int = Field(default=0, ge=0)
    max_retries: int = Field(default=3, ge=0)
    
    # Dead letter queue support
    original_queue: Optional[str] = None
    failure_reason: Optional[str] = None
    failed_at: Optional[datetime] = None
    
    @field_validator('contact_id')
    @classmethod
    def validate_contact_id(cls, v: str) -> str:
        """Ensure contact_id is numeric."""
        if not v.strip().isdigit():
            raise ValueError("Contact ID must be numeric")
        return v.strip()
    
    def to_sqs_format(self) -> Dict[str, Any]:
        """Convert to SQS-compatible format."""
        return {
            "message_type": self.message_type.value,
            "contact_id": self.contact_id,
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
            "data": self.data,
            "priority": self.priority.value,
            "retry_count": self.retry_count,
            "timestamp": self.created_at.isoformat(),
        }