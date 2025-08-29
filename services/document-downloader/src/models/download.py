# services/document-downloader/src/models/download.py
from typing import Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, field_validator, ConfigDict

if TYPE_CHECKING:
    from libs.forth_shared.models.queue import QueueMessage


class DownloadStatus(str, Enum):
    """Download status enumeration."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"
    NOT_FOUND = "not_found"


class DownloadTask(BaseModel):
    """Model for document download task."""
    
    model_config = ConfigDict(extra='forbid')
    
    contact_id: str = Field(..., description="Contact identifier")
    doc_id: str = Field(..., description="Document identifier")
    doc_name: Optional[str] = Field(None, description="Document name/filename")
    doc_type: Optional[str] = Field(None, description="Document type")
    correlation_id: Optional[str] = Field(None, description="Correlation ID for tracing")
    webhook_source: Optional[str] = Field(None, description="Webhook source (CDR, ASPIRE, RESYNC, etc.)")
    
    # Additional metadata from webhook
    doc_title: Optional[str] = Field(None, description="Document title")
    file_type: Optional[str] = Field(None, description="File type (Document, Image, etc.)")
    webhook_version: Optional[str] = Field(None, description="Webhook version")
    timestamp: Optional[str] = Field(None, description="Webhook timestamp")
    
    # Retry information
    retry_count: int = Field(default=0, ge=0, description="Number of retry attempts")
    
    # Status tracking
    status: DownloadStatus = Field(default=DownloadStatus.PENDING, description="Current status")
    
    @field_validator('doc_id')
    @classmethod
    def validate_doc_id(cls, v):
        """Ensure doc_id is provided and valid."""
        if not v or not str(v).strip():
            raise ValueError("doc_id is required")
        
        # Check for placeholder values that should be rejected
        doc_id_str = str(v).strip()
        invalid_patterns = [
            '{UPLOADED_DOCS}',      # Variant we saw in logs
            '{UPLOAD_DOC_IDS}',     # Correct Forth CRM placeholder
            '{DOC_ID}',
            '{',
            '}',
            'UPLOADED_DOCS',
            'UPLOAD_DOC_IDS',       # Also check without braces
            'DOC_ID'
        ]
        
        for pattern in invalid_patterns:
            if pattern in doc_id_str:
                raise ValueError(f"Invalid doc_id contains placeholder: {doc_id_str}")
        
        # Ensure doc_id is numeric or valid format (allow alphanumeric)
        if not doc_id_str.replace('_', '').replace('-', '').isalnum():
            raise ValueError(f"doc_id must be alphanumeric: {doc_id_str}")
            
        return doc_id_str
    
    @field_validator('contact_id')
    @classmethod
    def validate_contact_id(cls, v):
        """Ensure contact_id is provided and valid."""
        if not v or not str(v).strip():
            raise ValueError("contact_id is required")
        
        contact_id_str = str(v).strip()
        
        # Check for placeholder values
        invalid_patterns = ['{CONTACT_ID}', '{', '}', 'CONTACT_ID']
        for pattern in invalid_patterns:
            if pattern in contact_id_str:
                raise ValueError(f"Invalid contact_id contains placeholder: {contact_id_str}")
                
        return contact_id_str
    
    @classmethod
    def from_queue_message(cls, message: 'QueueMessage') -> 'DownloadTask':
        """Create DownloadTask from queue message."""
        data = message.data
        
        return cls(
            contact_id=message.contact_id,
            doc_id=data.get("doc_id", ""),
            doc_name=None,  
            doc_type=None, 
            correlation_id=message.correlation_id,
            webhook_source=data.get("webhook_source"),
            doc_title=data.get("doc_title"),
            file_type=data.get("file_type"),
            webhook_version=data.get("webhook_version"),
            timestamp=data.get("timestamp"),
            retry_count=getattr(message, 'retry_count', 0)
        )


class DownloadResult(BaseModel):
    """Result of document download operation."""
    
    model_config = ConfigDict(extra='forbid')
    
    success: bool = Field(..., description="Whether download succeeded")
    status: DownloadStatus = Field(..., description="Final download status")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    error_code: Optional[str] = Field(None, description="Error code for programmatic handling")
    
    # Success fields
    s3_key: Optional[str] = Field(None, description="S3 key of uploaded document")
    s3_url: Optional[str] = Field(None, description="S3 URL of uploaded document")
    file_size: Optional[int] = Field(None, ge=0, description="File size in bytes")
    content_type: Optional[str] = Field(None, description="MIME type of document")
    
    # Timing
    processing_time_ms: int = Field(default=0, ge=0, description="Processing time in milliseconds")
    download_time_ms: Optional[int] = Field(None, ge=0, description="Time spent downloading")
    upload_time_ms: Optional[int] = Field(None, ge=0, description="Time spent uploading to S3")
    
    # Metadata
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    correlation_id: Optional[str] = Field(None, description="Correlation ID for tracing")
    # Upstream HTTP status for error interpretation (e.g., 404)
    api_status_code: Optional[int] = Field(None, description="Upstream API HTTP status code if applicable")