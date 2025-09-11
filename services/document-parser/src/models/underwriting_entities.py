# services/document-parser/src/models/underwriting_entities.py
"""
Comprehensive Pydantic v2 models for underwriting database entities.
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
    company_name: Optional[str] = None
    company_address: Optional[str] = None
    company_phone: Optional[str] = None
    company_type: Optional[str] = None
    settlement_fee: Optional[Decimal] = None
    settlement_fee_percentage: Optional[Decimal] = None
    monthly_payment: Optional[Decimal] = None
    client_name: Optional[str] = None
    client_address: Optional[str] = None
    client_signature: Optional[str] = None
    client_signature_date: Optional[date] = None
    coclient_name: Optional[str] = None
    coclient_signature: Optional[str] = None
    coclient_signature_date: Optional[date] = None
    client_initials: Optional[str] = None
    client_initials_count: Optional[int] = None
    coclient_initials: Optional[str] = None
    coclient_initials_count: Optional[int] = None
    page_count: Optional[int] = None
    identified_debts_ack_client_signature: Optional[str] = None
    identified_debts_ack_coclient_signature: Optional[str] = None
    privacy_policy_client_initials: Optional[str] = None
    privacy_policy_coclient_initials: Optional[str] = None



class FCRAConsumerReportConsent(BaseUnderwritingModel):
    """FCRA Consumer Report Consent document model."""
    
    file_id: int = Field(..., description="File identifier")
    company_name: Optional[str] = None
    client_name: Optional[str] = None
    client_signature: Optional[str] = None
    client_signature_date: Optional[datetime] = None


class DebtSchedule(BaseUnderwritingModel):
    """Debt Schedule - can have multiple entries per file."""
    
    file_id: int = Field(..., description="File identifier")
    creditor_name: Optional[str] = None
    name_on_account: Optional[str] = None
    account_number: Optional[str] = None
    current_balance: Optional[Decimal] = None
    debt_type: Optional[str] = None
    client_name: Optional[str] = None
    client_signature: Optional[str] = None
    client_signature_date: Optional[date] = None
    coclient_name: Optional[str] = None
    coclient_signature: Optional[str] = None
    coclient_signature_date: Optional[date] = None


class FinancialAnalysis(BaseUnderwritingModel):
    """Financial Analysis document model."""
    
    file_id: int = Field(..., description="File identifier")
    applicant_name: Optional[str] = None
    applicant_email: Optional[EmailStr] = None
    coapplicant_name: Optional[str] = None
    coapplicant_email: Optional[EmailStr] = None
    draft_type: Optional[str] = None
    fixed_income: Optional[Decimal] = None
    day_phone: Optional[str] = None
    evening_phone: Optional[str] = None
    cell_phone: Optional[str] = None
    program_start_date: Optional[date] = None
    estimated_program_start_date: Optional[date] = None
    lump_sum: Optional[Decimal] = None
    applicant_monthly_income: Optional[Decimal] = None
    coapplicant_monthly_income: Optional[Decimal] = None
    applicant_expenses: Optional[Decimal] = None
    coapplicant_expenses: Optional[Decimal] = None
    applicant_total_net_income: Optional[Decimal] = None
    coapplicant_total_net_income: Optional[Decimal] = None
    total_enrolled_debt: Optional[Decimal] = None
    estimated_program_length: Optional[int] = None
    monthly_program_deposit: Optional[Decimal] = None
    estimated_program_settle_amount: Optional[Decimal] = None
    fee_method: Optional[str] = None
    total_program_fees: Optional[Decimal] = None
    estimated_program_savings: Optional[Decimal] = None
    estimated_total_cost: Optional[Decimal] = None
    hardship_details: Optional[str] = None
    client_signature: Optional[str] = None
    client_signature_date: Optional[date] = None
    coclient_signature: Optional[str] = None
    coclient_signature_date: Optional[date] = None
    client_initials: Optional[str] = None
    coclient_initials: Optional[str] = None


class Disclosure(BaseUnderwritingModel):
    """Disclosure document model."""
    
    file_id: int = Field(..., description="File identifier")
    client_signature: Optional[str] = None
    client_signature_date: Optional[date] = None
    coclient_signature: Optional[str] = None
    coclient_signature_date: Optional[date] = None
    additional_disclosure_client_signature: Optional[str] = None
    additional_disclosure_client_signature_date: Optional[date] = None
    additional_disclosure_coclient_signature: Optional[str] = None
    additional_disclosure_coclient_signature_date: Optional[date] = None



class HighInterestCreditorDisclosure(BaseUnderwritingModel):
    """High Interest Creditor Disclosure document model."""
    
    file_id: int = Field(..., description="File identifier")
    company_name: Optional[str] = None
    client_name: Optional[str] = None
    client_signature: Optional[str] = None
    client_signature_date: Optional[date] = None
    coclient_name: Optional[str] = None
    coclient_signature: Optional[str] = None
    coclient_signature_date: Optional[date] = None


class ProgramDisclosure(BaseUnderwritingModel):
    """Program Disclosure document model."""
    
    file_id: int = Field(..., description="File identifier")
    company_name: Optional[str] = None
    settlement_fee_percent: Optional[Decimal] = None
    client_initials: Optional[str] = None
    coclient_initials: Optional[str] = None
    client_initials_count: Optional[int] = None
    coclient_initials_count: Optional[int] = None
    is_all_initials_present: Optional[bool] = None


class PowerOfAttorney(BaseUnderwritingModel):
    """Power of Attorney document model."""
    
    file_id: int = Field(..., description="File identifier")
    company_name: Optional[str] = None
    attorney_name: Optional[str] = None
    attorney_address: Optional[str] = None
    attorney_phone: Optional[str] = None
    client_name: Optional[str] = None
    client_ssn: Optional[str] = None
    client_dob: Optional[date] = None
    client_signature: Optional[str] = None
    client_signature_date: Optional[datetime] = None
    coclient_name: Optional[str] = None
    coclient_ssn: Optional[str] = None
    coclient_dob: Optional[date] = None
    coclient_signature: Optional[str] = None
    coclient_signature_date: Optional[datetime] = None


class CancellationNotice(BaseUnderwritingModel):
    """Cancellation Notice document model."""
    
    file_id: int = Field(..., description="File identifier")
    cancellation_deadline: Optional[date] = None
    cancellation_date: Optional[date] = None
    client_signature: Optional[str] = None
    client_signature_date: Optional[datetime] = None
    coclient_signature: Optional[str] = None
    coclient_signature_date: Optional[datetime] = None


class PaymentGatewayAgreement(BaseUnderwritingModel):
    """Payment Gateway Agreement document model."""
    
    file_id: int = Field(..., description="File identifier")
    account_id: Optional[str] = None
    client_first_name: Optional[str] = None
    client_last_name: Optional[str] = None
    client_middle_initial: Optional[str] = None
    client_ssn: Optional[str] = None
    client_dob: Optional[date] = None
    client_address: Optional[str] = None
    client_city: Optional[str] = None
    client_state: Optional[str] = None
    client_zipcode: Optional[str] = None
    client_phone: Optional[str] = None
    client_email: Optional[EmailStr] = None
    coclient_first_name: Optional[str] = None
    coclient_last_name: Optional[str] = None
    coclient_middle_initial: Optional[str] = None
    coclient_ssn: Optional[str] = None
    coclient_dob: Optional[date] = None
    client_initials: Optional[str] = None
    coclient_initials: Optional[str] = None
    client_signature: Optional[str] = None
    client_signature_date: Optional[datetime] = None
    coclient_signature: Optional[str] = None
    coclient_signature_date: Optional[datetime] = None
    pages_count: Optional[int] = None



class PaymentGatewayServiceFees(BaseUnderwritingModel):
    """Payment Gateway Service Fees (optional) - multiple entries per file."""
    
    file_id: int = Field(..., description="File identifier")
    service_type: Optional[str] = None
    service_name: Optional[str] = None
    service_amount: Optional[Decimal] = None


class PaymentGatewayBankInfo(BaseUnderwritingModel):
    """Payment Gateway Bank Information document model."""
    
    file_id: int = Field(..., description="File identifier")
    authorizing_person_name: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    routing_number: Optional[str] = None
    account_type: Optional[Literal["checking", "savings"]] = None
    client_address: Optional[str] = None
    client_city: Optional[str] = None
    client_state: Optional[str] = None
    client_zipcode: Optional[str] = None
    recurring_debit_authorization: Optional[Decimal] = None
    first_debit_date: Optional[date] = None
    client_signature: Optional[str] = None
    client_signature_date: Optional[date] = None
    coclient_signature: Optional[str] = None
    coclient_signature_date: Optional[date] = None


class PaymentGatewayDepositSchedule(BaseUnderwritingModel):
    """Payment Gateway Deposit Schedule document model - multiple entries per file."""
    
    file_id: int = Field(..., description="File identifier")
    payment_no: Optional[str] = None
    process_date: Optional[date] = None
    amount: Optional[Decimal] = None


class LegalPlanAgreement(BaseUnderwritingModel):
    """Legal Plan Agreement document model - multiple entries per file."""
    
    file_id: int = Field(..., description="File identifier")
    legal_plan_provider: Optional[str] = None
    member_name: Optional[str] = None
    member_ssn: Optional[str] = None
    member_dob: Optional[date] = None
    coapplicant_name: Optional[str] = None
    coapplicant_ssn: Optional[str] = None
    coapplicant_dob: Optional[date] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
    phone1: Optional[str] = None
    phone2: Optional[str] = None
    email: Optional[EmailStr] = None
    referring_company: Optional[str] = None
    first_payment_date: Optional[date] = None
    first_payment_amount: Optional[Decimal] = None
    monthly_recurring_date: Optional[date] = None
    monthly_payment_amount: Optional[Decimal] = None
    debt_relief_program_duration: Optional[int] = None
    members_accumulation_amount: Optional[Decimal] = None
    payment_processor_name: Optional[str] = None
    credit_card_number: Optional[str] = None
    bank_account_number: Optional[str] = None
    credit_card_expiration_date: Optional[date] = None
    bank_routing_number: Optional[str] = None
    credit_card_name: Optional[str] = None
    bank_institution_name: Optional[str] = None
    credit_card_billing_address: Optional[str] = None
    account_holder_name: Optional[str] = None
    initials_count: Optional[int] = None
    is_all_initials_present: Optional[bool] = None
    client_signature: Optional[str] = None
    signature_date: Optional[datetime] = None
    pages_count: Optional[int] = None
    member_agreement_client_signature: Optional[str] = None
    member_agreement_signature_date: Optional[date] = None
    member_acknowledge_client_initials: Optional[str] = None
    member_acknowledge_client_initials_count: Optional[int] = None
    member_acknowledge_client_signature: Optional[str] = None
    member_acknowledge_signature_date: Optional[date] = None
    member_info_client_signature: Optional[str] = None
    member_info_signature_date: Optional[date] = None


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
    sender_ip_address: Optional[str] = None
    signers_count: Optional[int] = None
    

class ClixsignCertificateSigner(BaseUnderwritingModel):
    """Clixsign Certificate Signer information - multiple entries per file."""
    
    file_id: int = Field(..., description="File identifier")
    package_id: Optional[Union[int, str]] = None  # Can be integer or UUID string
    signer_name: Optional[str] = None
    signer_email_address: Optional[EmailStr] = None
    signer_ip_address: Optional[str] = None
    signer_user_agent: Optional[str] = None
    package_opened_at: Optional[datetime] = None
    signature_adopted_at: Optional[datetime] = None
    package_signed_at: Optional[datetime] = None
    package_declined_at: Optional[datetime] = None
    

class AttorneyPrivilegedClientInfo(BaseUnderwritingModel):
    """Attorney Privileged Client Information document model."""
    
    file_id: int = Field(..., description="File identifier")
    client_name: Optional[str] = None
    client_ssn: Optional[str] = None
    client_dob: Optional[date] = None
    client_employer: Optional[str] = None
    client_title: Optional[str] = None
    client_classification: Optional[str] = None
    client_email: Optional[EmailStr] = None
    client_street: Optional[str] = None
    client_city: Optional[str] = None
    client_state: Optional[str] = None
    client_zipcode: Optional[str] = None
    client_home_phone: Optional[str] = None
    client_cell_phone: Optional[str] = None
    coclient_name: Optional[str] = None
    coclient_ssn: Optional[str] = None
    coclient_dob: Optional[date] = None
    coclient_employer: Optional[str] = None
    coclient_title: Optional[str] = None
    coclient_classification: Optional[str] = None
    coclient_email: Optional[EmailStr] = None
    is_married_to_coclient: Optional[bool] = None
    has_security_clearance: Optional[bool] = None
    is_in_bankruptcy: Optional[bool] = None
    is_enrolled_in_credit_counseling: Optional[bool] = None
    client_signature: Optional[str] = None
    client_signature_date: Optional[date] = None
    coclient_signature: Optional[str] = None
    coclient_signature_date: Optional[date] = None


class ExtractedDocumentPackage(BaseUnderwritingModel):
    """
    Main container for all extracted entities from a document package.
    Handles partial extraction gracefully - missing entities are simply None.
    """
    
    file_id: int = Field(..., description="File identifier")
    document_type: Optional[str] = Field(None, description="Detected document type")
    confidence_score: Optional[float] = None
    
    # Core entities 
    engagement_term: Optional[EngagementTerm] = None
    power_of_attorney: Optional[PowerOfAttorney] = None
    payment_gateway_agreement: Optional[PaymentGatewayAgreement] = None
    financial_analysis: Optional[FinancialAnalysis] = None
    
    # Supporting entities 
    fcra_consent: Optional[FCRAConsumerReportConsent] = None
    debt_schedule: Optional[List[DebtSchedule]] = None
    disclosure: Optional[Disclosure] = None
    high_interest_disclosure: Optional[HighInterestCreditorDisclosure] = None
    program_disclosure: Optional[ProgramDisclosure] = None
    cancellation_notice: Optional[CancellationNotice] = None
    
    # Payment related 
    payment_service_fees: Optional[List[PaymentGatewayServiceFees]] = None
    payment_bank_info: Optional[PaymentGatewayBankInfo] = None
    payment_deposit_schedule: Optional[List[PaymentGatewayDepositSchedule]] = None
    
    # Legal plan 
    legal_plan_agreement: Optional[LegalPlanAgreement] = None
    
    # Attorney privileged info 
    attorney_privileged_client_info: Optional[AttorneyPrivilegedClientInfo] = None
    
    # Digital signature info 
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
            self.payment_bank_info, self.legal_plan_agreement, self.attorney_privileged_client_info,
            self.clixsign_sender
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
    'AttorneyPrivilegedClientInfo',
    'ClixsignCertificateSender',
    'ClixsignCertificateSigner',
    'ExtractedDocumentPackage'
]
