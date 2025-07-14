# services/document-downloader/src/models/download.py
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class DownloadTask(BaseModel):
    """Model for document download task."""
    
    contact_id: str = Field(..., description="Contact identifier")
    doc_id: str = Field(..., description="Document identifier")
    doc_type: str = Field(default="agreement", description="Document type")
    doc_name: Optional[str] = Field(None, description="Document filename")
    doc_url: Optional[str] = Field(None, description="Direct document URL if available")
    correlation_id: Optional[str] = Field(None, description="Correlation ID for tracing")
    
    # Additional metadata
    hardship_description: Optional[str] = Field(None, description="Hardship description from webhook")
    file_type: Optional[str] = Field(None, description="File type (Document, Image, etc.)")
    doc_type_id: Optional[str] = Field(None, description="Document type ID from Forth CRM")
    
    # Retry information
    retry_count: int = Field(default=0, ge=0, description="Number of retry attempts")
    
    @classmethod
    def from_queue_message(cls, message: 'QueueMessage') -> 'DownloadTask':
        """Create DownloadTask from queue message."""
        data = message.data
        
        return cls(
            contact_id=message.contact_id,
            doc_id=data.get("doc_id", ""),
            doc_type=data.get("doc_type", "agreement"),
            doc_name=data.get("doc_name"),
            doc_url=data.get("doc_url"),
            correlation_id=message.correlation_id,
            hardship_description=data.get("hardship_description"),
            file_type=data.get("file_type"),
            doc_type_id=data.get("doc_type_id"),
            retry_count=message.retry_count
        )


class DownloadResult(BaseModel):
    """Result of document download operation."""
    
    success: bool = Field(..., description="Whether download succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    
    # Success fields
    s3_key: Optional[str] = Field(None, description="S3 key of uploaded document")
    s3_url: Optional[str] = Field(None, description="S3 URL of uploaded document")
    file_size: Optional[int] = Field(None, ge=0, description="File size in bytes")
    content_type: Optional[str] = Field(None, description="MIME type of document")
    
    # Timing
    processing_time_ms: int = Field(default=0, ge=0, description="Processing time in milliseconds")
    
    # Metadata
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")