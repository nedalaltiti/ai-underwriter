# services/document-parser/src/models/underwriting_entities.py
"""
Comprehensive Pydantic v2 models for underwriting database entities.
Designed for robust extraction, validation, and storage with zero tolerance for hallucination.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any, Literal, Union
from pydantic import BaseModel, Field, field_validator, model_validator
import re

EmailStr = str

class BaseUnderwritingModel(BaseModel):
    """Base model with common validation and configuration."""
    
    model_config = {
        "str_strip_whitespace": True,
        "validate_assignment": True,
        "extra": "ignore",  # Ignore extra fields to prevent errors
        "frozen": False
    }

    @field_validator('*', mode='before')
    @classmethod
    def empty_string_to_none(cls, v):
        """Convert empty strings to None for optional fields."""
        if isinstance(v, str) and v.strip() == '':
            return None
        return v


class EngagementTerm(BaseUnderwritingModel):
    """Company Agreement / Engagement Term document model."""
    
    file_id: int = Field(..., description="File identifier")
    company_name: Optional[str] = Field(None, max_length=255)
    company_address: Optional[str] = Field(None, max_length=500)
    company_phone: Optional[str] = Field(None, max_length=20)
    company_type: Optional[str] = Field(None, max_length=100)
    settlement_fee: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    settlement_fee_percentage: Optional[Decimal] = Field(None, ge=0, le=100, decimal_places=2)
    monthly_payment: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    client_name: Optional[str] = Field(None, max_length=255)
    client_signature: Optional[str] = Field(None, max_length=255)
    client_signature_date: Optional[date] = None
    coclient_name: Optional[str] = Field(None, max_length=255)
    coclient_signature: Optional[str] = Field(None, max_length=255)
    coclient_signature_date: Optional[date] = None
    initials: Optional[str] = Field(None, max_length=10)
    initials_count: Optional[int] = Field(None, ge=0)
    is_all_initials_present: Optional[bool] = None
    page_count: Optional[int] = Field(None, ge=1)

    @field_validator('company_phone')
    @classmethod
    def validate_phone(cls, v):
        if v and not re.match(r'^[\d\s\-\(\)\+\.]+$', v):
            return None  # Invalid phone, set to None rather than error
        return v


class FCRAConsumerReportConsent(BaseUnderwritingModel):
    """FCRA Consumer Report Consent document model."""
    
    file_id: int = Field(..., description="File identifier")
    company_name: Optional[str] = Field(None, max_length=255)
    client_name: Optional[str] = Field(None, max_length=255)
    client_signature: Optional[str] = Field(None, max_length=255)
    client_signature_date: Optional[datetime] = None


class DebtSchedule(BaseUnderwritingModel):
    """Debt Schedule (Exhibit A) - can have multiple entries per file."""
    
    file_id: int = Field(..., description="File identifier")
    creditor_name: Optional[str] = Field(None, max_length=255)
    name_on_account: Optional[str] = Field(None, max_length=255)
    account_number: Optional[str] = Field(None, max_length=64)
    current_balance: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    debt_type: Optional[str] = Field(None, max_length=100)


class FinancialAnalysis(BaseUnderwritingModel):
    """Financial Analysis (Exhibit B) document model."""
    
    file_id: int = Field(..., description="File identifier")
    applicant_name: Optional[str] = Field(None, max_length=255)
    applicant_email: Optional[EmailStr] = None
    coapplicant_name: Optional[str] = Field(None, max_length=255)
    coapplicant_email: Optional[EmailStr] = None
    draft_type: Optional[str] = Field(None, max_length=100)
    fixed_income: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    day_phone: Optional[str] = Field(None, max_length=20)
    evening_phone: Optional[str] = Field(None, max_length=20)
    cell_phone: Optional[str] = Field(None, max_length=20)
    program_start_date: Optional[date] = None
    estimated_program_start_date: Optional[date] = None
    lump_sum: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    applicant_monthly_income: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    coapplicant_monthly_income: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    applicant_expenses: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    coapplicant_expenses: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    applicant_total_net_income: Optional[Decimal] = Field(None, decimal_places=2)
    coapplicant_total_net_income: Optional[Decimal] = Field(None, decimal_places=2)
    total_enrolled_debt: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    estimated_program_length: Optional[int] = Field(None, ge=1)
    monthly_program_deposit: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    estimated_program_settle_amount: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    fee_method: Optional[str] = Field(None, max_length=100)
    total_program_fees: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    estimated_program_savings: Optional[Decimal] = Field(None, decimal_places=2)
    estimated_total_cost: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    hardship_details: Optional[str] = Field(None, max_length=2000)
    client_signature: Optional[str] = Field(None, max_length=255)
    client_signature_date: Optional[date] = None


class Disclosure(BaseUnderwritingModel):
    """Disclosure (Exhibit C) document model."""
    
    file_id: int = Field(..., description="File identifier")
    client_signature: Optional[str] = Field(None, max_length=255)
    client_signature_date: Optional[date] = None
    coclient_signature: Optional[str] = Field(None, max_length=255)
    coclient_signature_date: Optional[date] = None


class HighInterestCreditorDisclosure(BaseUnderwritingModel):
    """High Interest Creditor Disclosure document model."""
    
    file_id: int = Field(..., description="File identifier")
    company_name: Optional[str] = Field(None, max_length=255)
    client_name: Optional[str] = Field(None, max_length=255)
    client_signature: Optional[str] = Field(None, max_length=255)
    client_signature_date: Optional[date] = None
    coclient_name: Optional[str] = Field(None, max_length=255)
    coclient_signature: Optional[str] = Field(None, max_length=255)
    coclient_signature_date: Optional[date] = None


class ProgramDisclosure(BaseUnderwritingModel):
    """Program Disclosure document model."""
    
    file_id: int = Field(..., description="File identifier")
    company_name: Optional[str] = Field(None, max_length=255)
    settlement_fee_percent: Optional[Decimal] = Field(None, ge=0, le=100, decimal_places=2)
    client_initial: Optional[str] = Field(None, max_length=10)
    is_all_initials_present: Optional[bool] = None


class PowerOfAttorney(BaseUnderwritingModel):
    """Power of Attorney document model."""
    
    file_id: int = Field(..., description="File identifier")
    company_name: Optional[str] = Field(None, max_length=255)
    attorney_name: Optional[str] = Field(None, max_length=255)
    attorney_address: Optional[str] = Field(None, max_length=500)
    attorney_phone: Optional[str] = Field(None, max_length=20)
    client_name: Optional[str] = Field(None, max_length=255)
    client_ssn: Optional[str] = Field(None, max_length=11)
    client_dob: Optional[date] = None
    client_signature: Optional[str] = Field(None, max_length=255)
    client_signature_date: Optional[datetime] = None
    coclient_name: Optional[str] = Field(None, max_length=255)
    coclient_ssn: Optional[str] = Field(None, max_length=11)
    coclient_dob: Optional[date] = None
    coclient_signature: Optional[str] = Field(None, max_length=255)

    @field_validator('client_ssn', 'coclient_ssn')
    @classmethod
    def validate_ssn(cls, v):
        if v and not re.match(r'^\d{3}-?\d{2}-?\d{4}$', v):
            return None  # Invalid SSN format
        return v


class CancellationNotice(BaseUnderwritingModel):
    """Cancellation Notice document model."""
    
    file_id: int = Field(..., description="File identifier")
    cancellation_deadline: Optional[date] = None
    cancellation_date: Optional[date] = None
    buyer_signature: Optional[str] = Field(None, max_length=255)


class PaymentGatewayAgreement(BaseUnderwritingModel):
    """Payment Gateway Agreement document model."""
    
    file_id: int = Field(..., description="File identifier")
    account_id: Optional[str] = Field(None, max_length=100)
    client_first_name: Optional[str] = Field(None, max_length=255)
    client_last_name: Optional[str] = Field(None, max_length=255)
    client_middle_initial: Optional[str] = Field(None, max_length=255)
    client_ssn: Optional[str] = Field(None, max_length=11)
    client_dob: Optional[date] = None
    client_address: Optional[str] = Field(None, max_length=500)
    client_city: Optional[str] = Field(None, max_length=100)
    client_state: Optional[str] = Field(None, max_length=2)
    client_zipcode: Optional[str] = Field(None, max_length=10)
    client_phone: Optional[str] = Field(None, max_length=20)
    client_email: Optional[EmailStr] = None
    coclient_first_name: Optional[str] = Field(None, max_length=255)
    coclient_last_name: Optional[str] = Field(None, max_length=255)
    coclient_middle_initial: Optional[str] = Field(None, max_length=255)
    coclient_ssn: Optional[str] = Field(None, max_length=11)
    coclient_dob: Optional[date] = None
    client_initials: Optional[str] = Field(None, max_length=10)
    client_signature: Optional[str] = Field(None, max_length=255)
    client_signature_date: Optional[datetime] = None
    coclient_signature: Optional[str] = Field(None, max_length=255)
    coclient_signature_date: Optional[datetime] = None
    pages_count: Optional[int] = Field(None, ge=1)

    @field_validator('client_state')
    @classmethod
    def validate_state(cls, v):
        if v and len(v) != 2:
            return None  # Invalid state code
        return v.upper() if v else None


class PaymentGatewayServiceFees(BaseUnderwritingModel):
    """Payment Gateway Service Fees (optional) - multiple entries per file."""
    
    file_id: int = Field(..., description="File identifier")
    service_type: Optional[str] = Field(None, max_length=100)
    service_name: Optional[str] = Field(None, max_length=255)
    service_amount: Optional[Decimal] = Field(None, ge=0, decimal_places=2)


class PaymentGatewayBankInfo(BaseUnderwritingModel):
    """Payment Gateway Bank Information document model."""
    
    file_id: int = Field(..., description="File identifier")
    authorizing_person_name: Optional[str] = Field(None, max_length=255)
    bank_name: Optional[str] = Field(None, max_length=255)
    account_number: Optional[str] = Field(None, max_length=50)
    routing_number: Optional[str] = Field(None, max_length=9)
    account_type: Optional[Literal["checking", "savings"]] = None
    address: Optional[str] = Field(None, max_length=500)
    recurring_debit_authorization: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    first_debit_date: Optional[date] = None
    client_signature: Optional[str] = Field(None, max_length=128)
    client_signature_date: Optional[date] = None
    coclient_signature: Optional[str] = Field(None, max_length=128)
    coclient_signature_date: Optional[date] = None

    @field_validator('routing_number')
    @classmethod
    def validate_routing_number(cls, v):
        if v and not re.match(r'^\d{9}$', v):
            return None  # Invalid routing number
        return v


class PaymentGatewayDepositSchedule(BaseUnderwritingModel):
    """Payment Gateway Deposit Schedule - multiple entries per file."""
    
    file_id: int = Field(..., description="File identifier")
    payment_no: Optional[str] = Field(None, max_length=50)
    process_date: Optional[date] = None
    amount: Optional[Decimal] = Field(None, ge=0, decimal_places=2)


class LegalPlanAgreement(BaseUnderwritingModel):
    """Legal Plan Agreement document model."""
    
    file_id: int = Field(..., description="File identifier")
    legal_plan_provider: Optional[str] = Field(None, max_length=255)
    member_name: Optional[str] = Field(None, max_length=255)
    member_ssn: Optional[str] = Field(None, max_length=11)
    member_dob: Optional[date] = None
    coapplicant_name: Optional[str] = Field(None, max_length=255)
    coapplicant_ssn: Optional[str] = Field(None, max_length=11)
    coapplicant_dob: Optional[date] = None
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=2)
    zipcode: Optional[str] = Field(None, max_length=10)
    phone1: Optional[str] = Field(None, max_length=20)
    phone2: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    referring_company: Optional[str] = Field(None, max_length=255)
    first_payment_date: Optional[date] = None
    first_payment_amount: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    monthly_recurring_date: Optional[date] = None
    monthly_payment_amount: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    debt_relief_program_duration: Optional[int] = Field(None, ge=1)
    members_accumulation_amount: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    payment_processor_name: Optional[str] = Field(None, max_length=255)
    credit_card_number: Optional[str] = Field(None, max_length=20)
    bank_account_number: Optional[str] = Field(None, max_length=50)
    credit_card_expiration_date: Optional[date] = None
    bank_routing_number: Optional[str] = Field(None, max_length=9)
    credit_card_name: Optional[str] = Field(None, max_length=255)
    bank_institution_name: Optional[str] = Field(None, max_length=255)
    credit_card_billing_address: Optional[str] = Field(None, max_length=500)
    account_holder_name: Optional[str] = Field(None, max_length=255)
    initials_count: Optional[int] = Field(None, ge=0)
    is_all_initials_present: Optional[bool] = None
    client_signature: Optional[str] = Field(None, max_length=255)
    signature_date: Optional[datetime] = None
    pages_count: Optional[int] = Field(None, ge=1)


class ClixsignCertificateSender(BaseUnderwritingModel):
    """Clixsign Certificate Sender information."""
    
    file_id: int = Field(..., description="File identifier")
    package_id: Optional[Union[int, str]] = None  # Can be integer or UUID string
    package_title: Optional[str] = None
    final_status: Optional[str] = None
    final_status_date: Optional[datetime] = None
    sending_entity: Optional[str] = None
    sender_name: Optional[str] = None
    sender_email_address: Optional[EmailStr] = None
    sender_ip_address: Optional[str] = Field(None, max_length=32)
    signers_count: Optional[int] = Field(None, ge=0)
    
    @field_validator('package_id', mode='before')
    @classmethod
    def validate_package_id(cls, v):
        """Convert package_id to string for consistent storage."""
        if v is None:
            return None
        return str(v)


class ClixsignCertificateSigner(BaseUnderwritingModel):
    """Clixsign Certificate Signer information - multiple entries per file."""
    
    file_id: int = Field(..., description="File identifier")
    package_id: Optional[Union[int, str]] = None  # Can be integer or UUID string
    signer_name: Optional[str] = None
    signer_email_address: Optional[EmailStr] = None
    signer_ip_address: Optional[str] = Field(None, max_length=32)
    signer_user_agent: Optional[str] = None
    package_opened_at: Optional[datetime] = None
    signature_adopted_at: Optional[datetime] = None
    package_signed_at: Optional[datetime] = None
    package_declined_at: Optional[datetime] = None
    
    @field_validator('package_id', mode='before')
    @classmethod
    def validate_package_id(cls, v):
        """Convert package_id to string for consistent storage."""
        if v is None:
            return None
        return str(v)


class ExtractedDocumentPackage(BaseUnderwritingModel):
    """
    Main container for all extracted entities from a document package.
    Handles partial extraction gracefully - missing entities are simply None.
    """
    
    file_id: int = Field(..., description="File identifier")
    document_type: Optional[str] = Field(None, description="Detected document type")
    confidence_score: Optional[float] = Field(None, ge=0, le=1, description="Extraction confidence")
    
    # Core entities (most common)
    engagement_term: Optional[EngagementTerm] = None
    power_of_attorney: Optional[PowerOfAttorney] = None
    payment_gateway_agreement: Optional[PaymentGatewayAgreement] = None
    financial_analysis: Optional[FinancialAnalysis] = None
    
    # Supporting entities (optional)
    fcra_consent: Optional[FCRAConsumerReportConsent] = None
    debt_schedule: Optional[List[DebtSchedule]] = None
    disclosure: Optional[Disclosure] = None
    high_interest_disclosure: Optional[HighInterestCreditorDisclosure] = None
    program_disclosure: Optional[ProgramDisclosure] = None
    cancellation_notice: Optional[CancellationNotice] = None
    
    # Payment related (optional)
    payment_service_fees: Optional[List[PaymentGatewayServiceFees]] = None
    payment_bank_info: Optional[PaymentGatewayBankInfo] = None
    payment_deposit_schedule: Optional[List[PaymentGatewayDepositSchedule]] = None
    
    # Legal plan (optional)
    legal_plan_agreement: Optional[LegalPlanAgreement] = None
    
    # Digital signature info (optional)
    clixsign_sender: Optional[ClixsignCertificateSender] = None
    clixsign_signers: Optional[List[ClixsignCertificateSigner]] = None
    
    # Metadata
    extraction_metadata: Dict[str, Any] = Field(default_factory=dict)
    validation_results: List[str] = Field(default_factory=list)
    
    @model_validator(mode='after')
    def validate_package(self):
        """Ensure at least one entity was extracted."""
        entities = [
            self.engagement_term, self.power_of_attorney, self.payment_gateway_agreement,
            self.financial_analysis, self.fcra_consent, self.disclosure,
            self.high_interest_disclosure, self.program_disclosure, self.cancellation_notice,
            self.payment_bank_info, self.legal_plan_agreement, self.clixsign_sender
        ]
        
        # Check for list entities
        list_entities = [
            self.debt_schedule, self.payment_service_fees, 
            self.payment_deposit_schedule, self.clixsign_signers
        ]
        
        has_entities = any(entity is not None for entity in entities)
        has_list_entities = any(lst and len(lst) > 0 for lst in list_entities if lst is not None)
        
        if not has_entities and not has_list_entities:
            self.validation_results.append("No valid entities extracted from document")
        
        return self


# Export all models for easy import
__all__ = [
    'BaseUnderwritingModel',
    'EngagementTerm',
    'FCRAConsumerReportConsent', 
    'DebtSchedule',
    'FinancialAnalysis',
    'Disclosure',
    'HighInterestCreditorDisclosure',
    'ProgramDisclosure',
    'PowerOfAttorney',
    'CancellationNotice',
    'PaymentGatewayAgreement',
    'PaymentGatewayServiceFees',
    'PaymentGatewayBankInfo',
    'PaymentGatewayDepositSchedule',
    'LegalPlanAgreement',
    'ClixsignCertificateSender',
    'ClixsignCertificateSigner',
    'ExtractedDocumentPackage'
]
