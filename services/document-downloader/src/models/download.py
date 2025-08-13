# services/document-downloader/src/models/download.py
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, field_validator, ConfigDict


class DownloadStatus(str, Enum):
    """Download status enumeration."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


class DownloadTask(BaseModel):
    """Model for document download task."""
    
    model_config = ConfigDict(extra='forbid')
    
    contact_id: str = Field(..., description="Contact identifier")
    doc_id: str = Field(..., description="Document identifier")
    doc_name: Optional[str] = Field(None, description="Document name/filename")
    doc_type: Optional[str] = Field(None, description="Document type")
    correlation_id: Optional[str] = Field(None, description="Correlation ID for tracing")
    
    # Additional metadata from webhook
    doc_title: Optional[str] = Field(None, description="Document title")
    file_type: Optional[str] = Field(None, description="File type (Document, Image, etc.)")
    webhook_version: Optional[str] = Field(None, description="Webhook version")
    timestamp: Optional[str] = Field(None, description="Webhook timestamp")
    
    # Retry information
    retry_count: int = Field(default=0, ge=0, description="Number of retry attempts")
    
    # Status tracking
    status: DownloadStatus = Field(default=DownloadStatus.PENDING, description="Current status")
    
    @classmethod
    def from_queue_message(cls, message: 'QueueMessage') -> 'DownloadTask':
        """Create DownloadTask from queue message."""
        data = message.data
        
        return cls(
            contact_id=message.contact_id,
            doc_id=data.get("doc_id", ""),
            doc_name=data.get("doc_name"),
            doc_type=data.get("doc_type"),
            correlation_id=message.correlation_id,
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