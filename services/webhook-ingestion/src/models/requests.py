
# services/webhook-ingestion/src/models/requests.py
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class WebhookSource(str, Enum):
    """Source systems for webhooks."""
    FORTH_CRM = "forth_crm"
    MANUAL = "manual"
    TEST = "test"


class WebhookRequest(BaseModel):
    """Incoming webhook request model."""
    
    contact_id: str = Field(..., description="Contact identifier", min_length=1)
    doc_id: str = Field(..., description="Document identifier", min_length=1)
    doc_type: str = Field(default="agreement", description="Document type")
    doc_name: Optional[str] = Field(None, description="Document name/filename")
    correlation_id: Optional[str] = Field(None, description="Correlation ID for tracing")
    source: WebhookSource = Field(default=WebhookSource.FORTH_CRM, description="Webhook source")
    
    # Additional fields that might come from Forth CRM
    doc_url: Optional[str] = Field(None, description="Direct document URL if available")
    file_type: Optional[str] = Field(None, description="File type (Document, Image, etc.)")
    doc_type_id: Optional[str] = Field(None, description="Document type ID from Forth CRM")
    hardship_description: Optional[str] = Field(None, description="Hardship description if provided")
    
    @field_validator('contact_id')
    @classmethod
    def validate_contact_id(cls, v: str) -> str:
        """Validate contact ID format."""
        v = v.strip()
        if not v.isdigit():
            raise ValueError("Contact ID must be numeric")
        return v
    
    @field_validator('doc_id')
    @classmethod
    def validate_doc_id(cls, v: str) -> str:
        """Validate and extract document ID."""
        v = v.strip()
        
        # Handle comma-separated document IDs (common in Forth CRM)
        if "," in v:
            doc_ids = [id_str.strip() for id_str in v.split(",") if id_str.strip()]
            # Take the last valid numeric ID
            for doc_id in reversed(doc_ids):
                if doc_id.isdigit():
                    return doc_id
            raise ValueError("No valid numeric document ID found in comma-separated list")
        
        if not v.isdigit():
            raise ValueError("Document ID must be numeric")
        return v


class WebhookResponse(BaseModel):
    """Webhook processing response."""
    
    status: str = Field(..., description="Processing status (success/error)")
    message: str = Field(..., description="Human-readable message")
    correlation_id: Optional[str] = Field(None, description="Correlation ID for tracing")
    processing_time_ms: int = Field(default=0, description="Processing time in milliseconds")
    
    # Optional fields for debugging
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")


class WebhookPayload(BaseModel):
    """Internal webhook payload after validation."""
    
    contact_id: str
    doc_id: str
    doc_type: str
    doc_name: Optional[str] = None
    correlation_id: Optional[str] = None
    source: WebhookSource
    raw_data: Optional[Dict[str, Any]] = None
    
    # Enriched fields
    doc_url: Optional[str] = None
    hardship_description: Optional[str] = None