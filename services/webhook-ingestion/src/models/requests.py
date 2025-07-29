
# services/webhook-ingestion/src/models/requests.py
import re
from typing import Optional, Dict, Any, List, Mapping
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict, NonNegativeInt, AnyHttpUrl
from enum import Enum
from loguru import logger
from dataclasses import dataclass

# Compiled regex patterns (avoid recompiling on every validation)
DIGIT_PATTERN = re.compile(r'^\d+$')
COMMA_SEPARATED_DIGITS = re.compile(r'^\d+(,\d+)*$')


class WebhookSource(str, Enum):
    """Source systems for webhooks."""
    FORTH_CRM = "forth_crm"
    MANUAL = "manual"
    TEST = "test"


class WebhookStatus(str, Enum):
    """Webhook processing status."""
    SUCCESS = "success"
    ERROR = "error"


class ErrorCode(str, Enum):
    """Error codes for programmatic error handling."""
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PROCESSING_ERROR = "PROCESSING_ERROR"
    QUEUE_ERROR = "QUEUE_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    CONTENT_TYPE_ERROR = "CONTENT_TYPE_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"


class BaseSchema(BaseModel):
    """Base schema with common configuration for all models."""
    
    model_config = ConfigDict(
        extra='forbid',
        frozen=True
    )


class WebhookRequest(BaseSchema):
    """Incoming webhook request model."""
    
    model_config = ConfigDict(
        extra='allow',  # Allow extra fields from Forth CRM
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "contact_id": "123456",
                    "doc_id": "789012",
                    "doc_name": "contract.pdf",
                    "doc_type": "agreement",
                    "correlation_id": "webhook-c3d4e5f6-1752860755",
                    "source": "forth_crm"
                }
            ]
        }
    )
    
    contact_id: str = Field(
        ..., 
        description="Contact identifier", 
        min_length=1,
        alias="contactId" 
    )
    doc_id: str = Field(
        ..., 
        description="Document identifier", 
        min_length=1,
        pattern=r'^\d+(,\d+)*$',  # Allow comma-separated IDs
        alias="docId" 
    )
    doc_name: Optional[str] = Field(
        None, 
        description="Document name/filename",
        alias="docName" 
    )
    doc_type: Optional[str] = Field(
        None,
        description="Document type (e.g., contract, addendum)",
        alias="docType"
    )
    doc_title: Optional[str] = Field(
        None,
        description="Document title",
        alias="docTitle"
    )
    file_type: Optional[str] = Field(
        None,
        description="File type/extension",
        alias="fileType"
    )
    timestamp: Optional[str] = Field(
        None,
        description="Webhook timestamp"
    )
    webhook_version: Optional[str] = Field(
        None,
        description="Webhook version",
        alias="webhookVersion"
    )
    correlation_id: Optional[str] = Field(
        None, 
        description="Correlation ID for tracing",
        alias="correlationId" 
    )
    source: WebhookSource = Field(
        default=WebhookSource.FORTH_CRM, 
        description="Webhook source"
    )
        
    @field_validator('contact_id')
    @classmethod
    def validate_contact_id(cls, v: str) -> str:
        """Validate contact ID format using regex."""
        v = v.strip()
        if not DIGIT_PATTERN.match(v):
            raise ValueError("Contact ID must be numeric")
        return v
    
    @field_validator('doc_id')
    @classmethod
    def extract_doc_id(cls, v: str) -> str:
        """Extract document ID from comma-separated list (takes the last one)."""
        v = v.strip()
        
        # Handle comma-separated document IDs (common in Forth CRM)
        if "," in v:
            doc_ids = [id_str.strip() for id_str in v.split(",") if id_str.strip()]
            # Take the last valid ID (all are guaranteed to be numeric by field pattern)
            selected_id = doc_ids[-1]
            
            # Use structured logging with debug level
            logger.bind(
                event="multi_doc_id",
                selected_doc_id=selected_id,
                all_doc_ids=v,
                total_count=len(doc_ids)
            ).debug("Multiple doc_ids received, using last one")
            
            return selected_id
        
        return v
    
    @model_validator(mode='before')
    @classmethod
    def handle_alternative_field_names(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Handle alternative field names for better compatibility."""
        if isinstance(values, dict):
            values = dict(values)  # Make a copy to avoid modifying the original
            
            # Handle snake_case to camelCase conversion for main fields FIRST
            if 'contact_id' in values:
                values['contactId'] = values.pop('contact_id')
            if 'doc_id' in values:
                values['docId'] = values.pop('doc_id')
            if 'doc_name' in values:
                values['docName'] = values.pop('doc_name')
            if 'doc_type' in values:
                values['docType'] = values.pop('doc_type')
            if 'correlation_id' in values:
                values['correlationId'] = values.pop('correlation_id')
            
            # Handle alternative doc_id field names (map to alias: docId)
            if 'docId' not in values:
                doc_id = (
                    values.get('document_id') or 
                    values.get('id') or 
                    values.get('docId', '')
                )
                if doc_id:
                    values['docId'] = doc_id
                    # Remove alternative field names to avoid conflicts
                    for key in ['document_id', 'id']:
                        values.pop(key, None)
            
            # Handle alternative doc_name field names (map to alias: docName)
            if 'docName' not in values:
                doc_name = (
                    values.get('document_name') or
                    values.get('filename') or
                    values.get('file_name') or
                    values.get('docName')
                )
                if doc_name:
                    values['docName'] = doc_name
                    # Remove alternative field names to avoid conflicts
                    for key in ['document_name', 'filename', 'file_name']:
                        values.pop(key, None)
        
        return values


class WebhookResponse(BaseSchema):
    """Webhook processing response."""
    
    model_config = ConfigDict(
        **BaseSchema.model_config,
        json_schema_extra={
            "examples": [
                {
                    "status": "success",
                    "message": "Webhook processed successfully",
                    "correlation_id": "webhook-a1b2c3d4-1752860745",
                    "processing_time_ms": 125
                },
                {
                    "status": "error",
                    "message": "Invalid document ID format",
                    "correlation_id": "webhook-b2c3d4e5-1752860750",
                    "processing_time_ms": 42,
                    "details": {"error_code": "VALIDATION_ERROR"}
                }
            ]
        }
    )
    
    status: WebhookStatus = Field(..., description="Processing status")
    message: str = Field(..., description="Human-readable message")
    correlation_id: Optional[str] = Field(None, description="Correlation ID for tracing")
    processing_time_ms: NonNegativeInt = Field(default=0, description="Processing time in milliseconds")
    
    # Optional fields for debugging
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")


class WebhookPayload(BaseSchema):
    """Internal webhook payload after validation."""
    
    model_config = ConfigDict(
        **BaseSchema.model_config,
        json_schema_extra={
            "examples": [
                {
                    "contact_id": "123456",
                    "doc_id": "789012",
                    "doc_name": "contract.pdf",
                    "doc_type": "contract",
                    "correlation_id": "webhook-d4e5f6g7-1752860760",
                    "source": "forth_crm",
                    "raw_data": {"original_payload": "data"}
                }
            ]
        }
    )
    
    contact_id: str
    doc_id: str
    doc_name: Optional[str] = None
    doc_type: Optional[str] = None
    doc_title: Optional[str] = None
    file_type: Optional[str] = None
    timestamp: Optional[str] = None
    webhook_version: Optional[str] = None
    correlation_id: Optional[str] = None
    source: WebhookSource
    raw_data: Optional[Mapping[str, Any]] = None
    
    @classmethod
    def from_webhook_request(
        cls, 
        request: WebhookRequest, 
        correlation_id: Optional[str] = None,
        raw_data: Optional[Mapping[str, Any]] = None
    ) -> "WebhookPayload":
        """Create WebhookPayload from WebhookRequest."""
        return cls(
            contact_id=request.contact_id,
            doc_id=request.doc_id,
            doc_name=request.doc_name,
            doc_type=request.doc_type,
            doc_title=request.doc_title,
            file_type=request.file_type,
            timestamp=request.timestamp,
            webhook_version=request.webhook_version,
            correlation_id=correlation_id or request.correlation_id,
            source=request.source,
            raw_data=raw_data
        )


class WebhookBatch(BaseSchema):
    """Batch of webhook requests (common pattern for multiple documents)."""
    
    model_config = ConfigDict(
        **BaseSchema.model_config,
        json_schema_extra={
            "examples": [
                {
                    "batch_id": "batch-a1b2c3d4-1752860745",
                    "requests": [
                        {
                            "contact_id": "123456",
                            "doc_id": "789012",
                            "doc_name": "contract.pdf",
                            "source": "forth_crm"
                        },
                        {
                            "contact_id": "123456",
                            "doc_id": "789013",
                            "doc_name": "addendum.pdf",
                            "source": "forth_crm"
                        }
                    ]
                }
            ]
        }
    )
    
    batch_id: Optional[str] = Field(
        None, 
        description="Batch correlation ID for tracing all requests in this batch"
    )
    
    requests: List[WebhookRequest] = Field(
        ..., 
        description="List of webhook requests",
        min_length=1,
        max_length=100  # Reasonable batch size limit
    )


@dataclass(frozen=True)
class ProcessingResult:
    """Result of webhook processing."""
    success: bool
    message_id: Optional[str] = None
    error_message: Optional[str] = None
    correlation_id: Optional[str] = None
    processing_time_ms: int = 0
    error_code: Optional[ErrorCode] = None