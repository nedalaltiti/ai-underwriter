# services/document-parser/src/models/extraction.py
"""Models for document extraction and processing."""

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Union, Optional, TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ValidationInfo

from .base import BankDetails, ClientInformation, Creditor, FinancialAnalysis

if TYPE_CHECKING:
    from models.underwriting_entities import ExtractedDocumentPackage
from .validation import ValidationResult


class ProcessingStatus(str, Enum):
    """Status of document processing."""
    PENDING = "pending"
    PROCESSING = "processing" 
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class DocumentSection(BaseModel):
    """Model for a document section."""
    section_name: str
    data: Dict[str, Any]
    signatures_valid: Optional[bool] = True
    dates_valid: Optional[bool] = True


class ExtractedDocument(BaseModel):
    """Main model for the entire extracted document - simplified for Gemini extraction."""
    
    # Basic client information (maps to multiple tables)
    name: Optional[str] = None
    ssn: Optional[str] = None
    dob: Optional[str] = None  # Will be parsed to date later
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[Dict[str, Any]] = None
    
    # Optional fields that may be extracted
    client_info: Optional[ClientInformation] = None
    financial_analysis: Optional[FinancialAnalysis] = None
    creditors: Optional[List[Creditor]] = []
    bank_details: Optional[BankDetails] = None
    document_sections: Optional[List[DocumentSection]] = []
    vlp_enrolled: bool = False
    contract_date: Optional[date] = None
    first_payment_date: Optional[date] = None
    sender_ip: Optional[str] = None
    signer_ip: Optional[str] = None
    validation_results: List[ValidationResult] = []
    extraction_metadata: Dict[str, Any] = {}
    
    @field_validator('first_payment_date')
    def validate_first_payment(cls, v, info: ValidationInfo):
        """Validate first payment date is within acceptable range."""
        if v is None:
            return v
        contract_date = info.data.get('contract_date')
        if contract_date:
            days = (v - contract_date).days
            if days < 2 or days > 45:
                raise ValueError(
                    f"First payment must be 2–45 days after contract date, got {days} days"
                )
        return v
    
    @field_validator('signer_ip')
    def validate_different_ips(cls, v, info: ValidationInfo):
        """Validate sender and signer IPs are different."""
        sender_ip = info.data.get('sender_ip')
        if sender_ip and v == sender_ip:
            raise ValueError("Sender and signer IPs must be different")
        return v


class ProcessingTask(BaseModel):
    """Model for a document processing task."""
    task_id: UUID
    document_url: str  
    s3_key: str        
    contact_id: str
    doc_id: str
    received_at: datetime
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None
    status: ProcessingStatus = ProcessingStatus.PENDING
    retry_count: int = 0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = {}
    
    @field_validator('document_url')
    def validate_document_url(cls, v):
        """Validate document URL format."""
        # Allow empty string (when using only s3_key). Validate only when provided.
        if v:
            if not (v.startswith('http://') or v.startswith('https://') or v.startswith('s3://')):
                raise ValueError("Document URL must be HTTP, HTTPS, or S3 URL")
        return v


class ProcessingResult(BaseModel):
    """Model for processing results."""
    task_id: UUID
    status: ProcessingStatus
    extracted_document: Optional[Union[ExtractedDocument, "ExtractedDocumentPackage"]] = None
    processing_time_ms: int
    token_usage: Dict[str, Any] = {}
    validation_summary: Dict[str, Any] = {}
    error_details: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.now)
    
    def get_validation_summary(self) -> Dict[str, Any]:
        """Get summary of validation results."""
        if not self.extracted_document or not self.extracted_document.validation_results:
            return {"total": 0, "passed": 0, "failed": 0, "pass_rate": 0.0}
        
        results = self.extracted_document.validation_results
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": passed / total if total > 0 else 0.0,
            "critical_failures": [
                r.field for r in results 
                if not r.passed and r.field in [
                    "budget_surplus", "minimum_payment", "unsecured_debt_percentage"
                ]
            ]
        }


# Rebuild models after all imports are complete to resolve forward references
def _rebuild_models():
    """Rebuild models to resolve forward references after all imports."""
    try:
        from models.underwriting_entities import ExtractedDocumentPackage
        ProcessingResult.model_rebuild()
    except ImportError:
        # If ExtractedDocumentPackage isn't available, that's fine
        pass

_rebuild_models()