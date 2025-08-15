
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


class WebhookType(str, Enum):
    """Types of webhook events."""
    DOCUMENT_UPLOADED = "document_uploaded"
    CLIENT_SUBMITTED = "client_submitted"


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
                    "correlation_id": "webhook-c3d4e5f6-1752860755",
                    "source": "forth_crm",
                    "webhook_type": "document_uploaded"
                },
                {
                    "contact_id": "123456",
                    "doc_id": "789012,789013,789014",
                    "correlation_id": "webhook-d7e8f9g0-1752860756",
                    "source": "forth_crm",
                    "webhook_type": "client_submitted"
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
        pattern=r'^(\d+(,\d+)*|\{[A-Z_0-9_]+\})$', 
        alias="docId" 
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
    webhook_type: Optional[WebhookType] = Field(
        default=WebhookType.DOCUMENT_UPLOADED,
        description="Type of webhook event",
        alias="webhookType"
    )
    doc_types: Optional[Dict[str, str]] = Field(
        None,
        description="Mapping of document IDs to their types (e.g., {'475837940': 'contract', '475837941': 'addendum'})",
        alias="docTypes"
    )
        
    @field_validator('contact_id')
    @classmethod
    def validate_contact_id(cls, v: str) -> str:
        """Validate contact ID format using regex."""
        v = v.strip()
        
        # Skip validation for Forth template variables
        if v.startswith('{') and v.endswith('}'):
            logger.bind(
                event="forth_template_contact_id",
                template_value=v
            ).debug("Forth template variable received for contact_id")
            return v
            
        if not DIGIT_PATTERN.match(v):
            raise ValueError("Contact ID must be numeric")
        return v
    
    @field_validator('doc_id')
    @classmethod
    def validate_doc_id_format(cls, v: str) -> str:
        """Validate document ID format but preserve original value for webhook type processing."""
        v = v.strip()
        
        # Skip validation for Forth template variables
        if v.startswith('{') and v.endswith('}'):
            logger.bind(
                event="forth_template_doc_id",
                template_value=v
            ).debug("Forth template variable received for doc_id")
            return v
        
        if "," in v:
            doc_ids = [id_str.strip() for id_str in v.split(",") if id_str.strip()]
            # Validate all IDs are numeric (pattern validation handles this too)
            for doc_id in doc_ids:
                if not DIGIT_PATTERN.match(doc_id):
                    raise ValueError(f"All document IDs must be numeric, got: {doc_id}")
            
            logger.debug(f"Multiple doc_ids received: {len(doc_ids)} documents")
        
        return v  # Return original value
    
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
            if 'webhook_type' in values:
                values['webhookType'] = values.pop('webhook_type')
            if 'doc_types' in values:
                values['docTypes'] = values.pop('doc_types')
            
            # Handle alternative doc_id field names (map to alias: docId)
            if 'docId' not in values:
                doc_id = (
                    values.get('upload_doc') or      # Forth CRM uses this field
                    values.get('uploaded_docs') or   # Alternative field
                    values.get('document_id') or 
                    values.get('id') or 
                    values.get('docId', '')
                )
                if doc_id:
                    values['docId'] = doc_id
                    # Remove alternative field names to avoid conflicts
                    for key in ['upload_doc', 'uploaded_docs', 'document_id', 'id']:
                        values.pop(key, None)
            
        return values
    
    @model_validator(mode='after')
    def handle_webhook_type_logic(self) -> 'WebhookRequest':
        """Handle webhook type specific logic for document IDs."""
        # Store original doc_id for reference
        original_doc_id = self.doc_id
        
        # Extract doc_id based on webhook_type
        if "," in original_doc_id:
            doc_ids = [id_str.strip() for id_str in original_doc_id.split(",") if id_str.strip()]
            
            if self.webhook_type == WebhookType.CLIENT_SUBMITTED:
                # For CLIENT_SUBMITTED: keep all doc_ids (comma-separated)
                # The processor will handle splitting them
                logger.debug(f"Client submitted: {len(doc_ids)} documents")
                   
            else:
                # For DOCUMENT_UPLOADED: take only the last doc_id 
                selected_id = doc_ids[-1]
                
                logger.debug(f"Document uploaded: using last ID {selected_id} from {len(doc_ids)} docs")
                
                # Update doc_id to only the selected one
                object.__setattr__(self, 'doc_id', selected_id)
        
        return self


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
                    "correlation_id": "webhook-d4e5f6g7-1752860760",
                    "source": "forth_crm",
                    "raw_data": {"original_payload": "data"}
                }
            ]
        }
    )
    
    contact_id: str
    doc_id: str

    doc_title: Optional[str] = None
    file_type: Optional[str] = None
    timestamp: Optional[str] = None
    webhook_version: Optional[str] = None
    correlation_id: Optional[str] = None
    source: WebhookSource
    webhook_type: WebhookType = WebhookType.DOCUMENT_UPLOADED
    doc_types: Optional[Dict[str, str]] = None
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
            doc_title=request.doc_title,
            file_type=request.file_type,
            timestamp=request.timestamp,
            webhook_version=request.webhook_version,
            correlation_id=correlation_id or request.correlation_id,
            source=request.source,
            webhook_type=request.webhook_type or WebhookType.DOCUMENT_UPLOADED,
            doc_types=request.doc_types,
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