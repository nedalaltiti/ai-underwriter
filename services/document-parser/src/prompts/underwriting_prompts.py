# services/document-parser/src/prompts/underwriting_prompts_new.py
"""
Simplified, efficient prompts for underwriting document extraction.
Designed for maximum accuracy with minimal token usage.
"""

from typing import Dict, Any

BASE_RULES = """
Extract only visible data. Use null for missing fields.
Dates: YYYY-MM-DD. Money: no $ symbol. SSNs: with dashes.
"""

def get_engagement_term_prompt() -> str:
    """Terms of Engagement / Company Agreement extraction."""
    return f"""
{BASE_RULES}

Extract from Terms of Engagement section.

CLIENT INITIALS: Look for 2-4 capital letters (e.g., "RL", "JD", "ABC") written by client next to paragraphs/acknowledgments in engagement section. Count all occurrences.

Return JSON:
{{
  "company_name": null,
  "company_address": null, 
  "company_phone": null,
  "settlement_fee_percentage": null,
  "monthly_payment": null,
  "client_name": null,
  "client_address": null,
  "client_signature": null,
  "client_signature_date": null,
  "coclient_signature": null,
  "coclient_signature_date": null,
  "client_initials": null,
  "coclient_initials": null
}}
"""

def get_financial_analysis_prompt() -> str:
    return f"""
{BASE_RULES}

{{
  "applicant_name": null,
  "applicant_email": null,
  "coapplicant_name": null,
  "draft_type": null,
  "fixed_income": null,
  "day_phone": null,
  "evening_phone": null,
  "cell_phone": null,
  "program_start_date": null,
  "lump_sum": null,
  "applicant_monthly_income": null,
  "coapplicant_monthly_income": null,
  "applicant_expenses": null,
  "coapplicant_expenses": null,
  "total_enrolled_debt": null,
  "estimated_program_length": null,
  "monthly_program_deposit": null,
  "estimated_program_settle_amount": null,
  "fee_method": null,
  "client_signature": null,
  "client_signature_date": null,
  "coclient_signature": null,
  "coclient_signature_date": null,
  "client_initials": null
}}
"""

def get_payment_gateway_prompt() -> str:
    """Payment Gateway / Account Agreement extraction."""
    return f"""
{BASE_RULES}

Extract Account Agreement / Payment Gateway information.

Return JSON (include ONLY if section exists in document):
{{
  "payment_gateway_agreement": {{
    "account_id": null,
    "client_first_name": null,
    "client_last_name": null,
    "client_middle_initial": null,
    "client_ssn": null,
    "client_dob": null,
    "client_address": null,
    "client_city": null,
    "client_state": null,
    "client_zipcode": null,
    "client_phone": null,
    "client_email": null,
    "coclient_first_name": null,
    "coclient_last_name": null,
    "coclient_middle_initial": null,
    "coclient_ssn": null,
    "coclient_dob": null,
    "client_initials": null,
    "coclient_initials": null,
    "client_signature": null,
    "client_signature_date": null,
    "coclient_signature": null,
    "coclient_signature_date": null,
    "pages_count": null
  }}
}}

If Account Agreement section not found, return: {{"payment_gateway_agreement": null}}
"""

def get_payment_bank_info_prompt() -> str:
    """Primary Account Information extraction."""
    return f"""
{BASE_RULES}

{{
  "authorizing_person_name": null,
  "bank_name": null,
  "account_number": null,
  "routing_number": null,
  "account_type": null,
  "client_address": null,
  "client_city": null,
  "client_state": null,
  "client_zipcode": null,
  "recurring_debit_authorization": null,
  "first_debit_date": null,
  "client_signature": null,
  "client_signature_date": null,
  "coclient_signature": null,
  "coclient_signature_date": null
}}
"""

def get_power_of_attorney_prompt() -> str:
    """Power of Attorney extraction."""
    return f"""
{BASE_RULES}

{{
  "company_name": null,
  "attorney_name": null,
  "attorney_address": null,
  "client_name": null,
  "client_ssn": null,
  "client_dob": null,
  "client_signature": null,
  "client_signature_date": null,
  "coclient_name": null,
  "coclient_ssn": null,
  "coclient_dob": null,
  "coclient_signature": null,
  "coclient_signature_date": null
}}
"""

def get_legal_plan_prompt() -> str:
    """VLP Terms Agreement extraction."""
    return f"""
{BASE_RULES}

{{
  "legal_plan_provider": null,
  "member_name": null,
  "member_ssn": null,
  "member_dob": null,
  "address": null,
  "city": null,
  "state": null,
  "zipcode": null,
  "phone1": null,
  "email": null,
  "first_payment_amount": null,
  "monthly_payment_amount": null,
  "member_agreement_client_signature": null,
  "member_agreement_signature_date": null,
  "member_acknowledge_client_initials": null,
  "member_acknowledge_client_signature": null,
  "member_acknowledge_signature_date": null,
  "member_info_client_signature": null,
  "member_info_signature_date": null
}}
"""

def get_debt_schedule_prompt() -> str:
    """Debt Schedule extraction."""
    return f"""
{BASE_RULES}

{{
  "debt_schedule": [
    {{
      "creditor_name": null,
      "name_on_account": null, 
      "account_number": null,
      "current_balance": null,
      "debt_type": null
    }}
  ]
}}
"""

def get_disclosure_prompt() -> str:
    """Disclosure sections extraction."""
    return f"""
{BASE_RULES}

{{
  "client_signature": null,
  "client_signature_date": null,
  "coclient_signature": null,
  "coclient_signature_date": null,
  "additional_disclosure_client_signature": null,
  "additional_disclosure_client_signature_date": null,
  "additional_disclosure_coclient_signature": null,
  "additional_disclosure_coclient_signature_date": null,
  "client_initials": null,
  "coclient_initials": null
}}
"""

def get_program_disclosure_prompt() -> str:
    """Program Disclosure extraction."""
    return f"""
{BASE_RULES}

{{
  "company_name": null,
  "settlement_fee_percent": null,
  "client_initials": null,
  "coclient_initials": null,
  "client_initials_count": null,
  "is_all_initials_present": null
}}
"""

def get_fcra_prompt() -> str:
    """FCRA Authorization extraction."""
    return f"""
{BASE_RULES}

{{
  "company_name": null,
  "client_name": null,
  "client_signature": null,
  "client_signature_date": null
}}
"""

def get_payment_service_fees_prompt() -> str:
    """Payment Service Fees table extraction."""
    return f"""
{BASE_RULES}

{{
  "payment_service_fees": [
    {{
      "service_type": null,
      "service_name": null,
      "service_amount": null
    }}
  ]
}}
"""

def get_payment_deposit_schedule_prompt() -> str:
    """Payment Deposit Schedule table extraction."""
    return f"""
{BASE_RULES}

Extract complete deposit schedule table.

{{
  "payment_deposit_schedule": [
    {{
      "payment_no": null,
      "process_date": null,
      "amount": null
    }}
  ]
}}
"""

def get_attorney_privileged_client_info_prompt() -> str:
    """Attorney Client Privileged Information extraction."""
    return f"""
{BASE_RULES}

{{
  "client_name": null,
  "client_ssn": null,
  "client_dob": null,
  "client_employer": null,
  "client_title": null,
  "client_classification": null,
  "client_email": null,
  "client_street": null,
  "client_city": null,
  "client_state": null,
  "client_zipcode": null,
  "client_home_phone": null,
  "client_cell_phone": null,
  "coclient_name": null,
  "coclient_ssn": null,
  "coclient_dob": null,
  "coclient_employer": null,
  "coclient_title": null,
  "coclient_classification": null,
  "coclient_email": null,
  "is_married_to_coclient": null,
  "has_security_clearance": null,
  "is_in_bankruptcy": null,
  "is_enrolled_in_credit_counseling": null,
  "client_signature": null,
  "client_signature_date": null,
  "coclient_signature": null,
  "coclient_signature_date": null
}}
"""

def get_clixsign_sender_prompt() -> str:
    """Clixsign Sender Information extraction."""
    return f"""
{BASE_RULES}

{{
  "package_id": null,
  "package_title": null,
  "final_status": null,
  "final_status_date": null,
  "sending_entity": null,
  "sender_name": null,
  "sender_email_address": null,
  "sender_ip_address": null,
  "signers_count": null
}}
"""

def get_clixsign_signers_prompt() -> str:
    """Clixsign Signers Information extraction."""
    return f"""
{BASE_RULES}

{{
  "clixsign_signers": [
    {{
      "package_id": null,
      "signer_name": null,
      "signer_email_address": null,
      "signer_ip_address": null,
      "signer_user_agent": null,
      "package_opened_at": null,
      "signature_adopted_at": null,
      "package_signed_at": null
    }}
  ]
}}
"""

def get_cancellation_notice_prompt() -> str:
    """Cancellation Notice / Right of Rescission extraction."""
    return f"""
{BASE_RULES}

{{
  "cancellation_deadline": null,
  "cancellation_date": null,
  "client_signature": null,
  "client_signature_date": null,
  "coclient_signature": null,
  "coclient_signature_date": null
}}
"""

# Main prompt routing function
def get_prompt_for_document_type(document_type: str) -> str:
    """Get focused prompt for specific document type."""
    
    prompts = {
        'engagement_term': get_engagement_term_prompt(),
        'financial_analysis': get_financial_analysis_prompt(),
        'payment_gateway_agreement': get_payment_gateway_prompt(),
        'payment_bank_info': get_payment_bank_info_prompt(),
        'power_of_attorney': get_power_of_attorney_prompt(),
        'legal_plan_agreement': get_legal_plan_prompt(),
        'debt_schedule': get_debt_schedule_prompt(),
        'disclosure': get_disclosure_prompt(),
        'program_disclosure': get_program_disclosure_prompt(),
        'fcra_consent': get_fcra_prompt(),
        'payment_service_fees': get_payment_service_fees_prompt(),
        'payment_deposit_schedule': get_payment_deposit_schedule_prompt(),
        'attorney_privileged_client_info': get_attorney_privileged_client_info_prompt(),
        'clixsign_sender': get_clixsign_sender_prompt(),
        'clixsign_signers': get_clixsign_signers_prompt(),
        'cancellation_notice': get_cancellation_notice_prompt(),
    }
    
    return prompts.get(document_type, get_comprehensive_prompt())

def get_comprehensive_prompt() -> str:
    """Compact comprehensive extraction for underwriting documents."""
    return f"""
{BASE_RULES}

Extract complete tables. All rows, actual data only.

Return complete JSON with ALL entities found (use null for missing sections):
{{
  "engagement_term": {{
    "company_name": null,
    "company_address": null,
    "company_phone": null,
    "company_type": null,
    "settlement_fee": null,
    "settlement_fee_percentage": null,
    "monthly_payment": null,
    "client_name": null,
    "client_address": null,
    "client_signature": null,
    "client_signature_date": null,
    "coclient_name": null,
    "coclient_signature": null,
    "coclient_signature_date": null,
    "client_initials": null,
    "client_initials_count": null,
    "coclient_initials": null,
    "coclient_initials_count": null,
    "page_count": null,
    "identified_debts_ack_client_signature": null,
    "identified_debts_ack_coclient_signature": null,
    "privacy_policy_client_initials": null,
    "privacy_policy_coclient_initials": null
  }},
  "financial_analysis": {{
    "applicant_name": null,
    "applicant_email": null,
    "coapplicant_name": null,
    "draft_type": null,
    "fixed_income": null,
    "day_phone": null,
    "evening_phone": null,
    "cell_phone": null,
    "program_start_date": null,
    "lump_sum": null,
    "applicant_monthly_income": null,
    "coapplicant_monthly_income": null,
    "applicant_expenses": null,
    "coapplicant_expenses": null,
    "applicant_total_net_income": null,
    "coapplicant_total_net_income": null,
    "total_enrolled_debt": null,
    "estimated_program_length": null,
    "monthly_program_deposit": null,
    "estimated_program_settle_amount": null,
    "fee_method": null,
    "total_program_fees": null,
    "estimated_program_savings": null,
    "estimated_total_cost": null,
    "hardship_details": null,
    "client_signature": null,
    "client_signature_date": null,
    "coclient_signature": null,
    "coclient_signature_date": null,
    "client_initials": null
  }},
  "payment_gateway_agreement": {{
    "account_id": null,
    "client_first_name": null,
    "client_last_name": null,
    "client_middle_initial": null,
    "client_ssn": null,
    "client_dob": null,
    "client_address": null,
    "client_city": null,
    "client_state": null,
    "client_zipcode": null,
    "client_phone": null,
    "client_email": null,
    "coclient_first_name": null,
    "coclient_last_name": null,
    "coclient_middle_initial": null,
    "coclient_ssn": null,
    "coclient_dob": null,
    "client_initials": null,
    "coclient_initials": null,
    "client_signature": null,
    "client_signature_date": null,
    "coclient_signature": null,
    "coclient_signature_date": null,
    "pages_count": null
  }},
  "payment_bank_info": {{
    "authorizing_person_name": null,
    "bank_name": null,
    "account_number": null,
    "routing_number": null,
    "account_type": null,
    "client_address": null,
    "client_city": null,
    "client_state": null,
    "client_zipcode": null,
    "recurring_debit_authorization": null,
    "first_debit_date": null,
    "client_signature": null,
    "client_signature_date": null,
    "coclient_signature": null,
    "coclient_signature_date": null
  }},
  "power_of_attorney": {{
    "company_name": null,
    "attorney_name": null,
    "attorney_address": null,
    "client_name": null,
    "client_ssn": null,
    "client_dob": null,
    "client_signature": null,
    "client_signature_date": null,
    "coclient_name": null,
    "coclient_ssn": null,
    "coclient_dob": null,
    "coclient_signature": null,
    "coclient_signature_date": null
  }},
  "legal_plan_agreement": {{
    "legal_plan_provider": null,
    "member_name": null,
    "member_ssn": null,
    "member_dob": null,
    "coapplicant_name": null,
    "coapplicant_ssn": null,
    "coapplicant_dob": null,
    "address": null,
    "city": null,
    "state": null,
    "zipcode": null,
    "phone1": null,
    "phone2": null,
    "email": null,
    "referring_company": null,
    "first_payment_date": null,
    "first_payment_amount": null,
    "monthly_recurring_date": null,
    "monthly_payment_amount": null,
    "debt_relief_program_duration": null,
    "members_accumulation_amount": null,
    "payment_processor_name": null,
    "credit_card_number": null,
    "bank_account_number": null,
    "credit_card_expiration_date": null,
    "bank_routing_number": null,
    "credit_card_name": null,
    "bank_institution_name": null,
    "credit_card_billing_address": null,
    "account_holder_name": null,
    "initials_count": null,
    "is_all_initials_present": null,
    "client_signature": null,
    "signature_date": null,
    "pages_count": null,
    "member_agreement_client_signature": null,
    "member_agreement_signature_date": null,
    "member_acknowledge_client_initials": null,
    "member_acknowledge_client_initials_count": null,
    "member_acknowledge_client_signature": null,
    "member_acknowledge_signature_date": null,
    "member_info_client_signature": null,
    "member_info_signature_date": null
  }},
  "debt_schedule": [
    {{
      "creditor_name": null,
      "name_on_account": null, 
      "account_number": null,
      "current_balance": null,
      "debt_type": null,
      "client_name": null,
      "client_signature": null,
      "client_signature_date": null,
      "coclient_name": null,
      "coclient_signature": null,
      "coclient_signature_date": null
    }}
  ],
  "disclosure": {{
    "client_signature": null,
    "client_signature_date": null,
    "coclient_signature": null,
    "coclient_signature_date": null,
    "additional_disclosure_client_signature": null,
    "additional_disclosure_client_signature_date": null,
    "additional_disclosure_coclient_signature": null,
    "additional_disclosure_coclient_signature_date": null,
    "client_initials": null,
    "coclient_initials": null
  }},
  "program_disclosure": {{
    "company_name": null,
    "settlement_fee_percent": null,
    "client_initials": null,
    "coclient_initials": null,
    "client_initials_count": null,
    "is_all_initials_present": null
  }},
  "fcra_consent": {{
    "company_name": null,
    "client_name": null,
    "client_signature": null,
    "client_signature_date": null
  }},
  "payment_service_fees": [
    {{
      "service_type": "Administrative or Disbursement",
      "service_name": "actual_fee_name_from_document",
      "service_amount": "actual_amount_from_document"
    }}
  ],
  "payment_deposit_schedule": [
    {{
      "payment_no": null,
      "process_date": null, 
      "amount": null
    }}
  ],
  "attorney_privileged_client_info": {{
    "client_name": null,
    "client_ssn": null,
    "client_dob": null,
    "client_employer": null,
    "client_title": null,
    "client_classification": null,
    "client_email": null,
    "client_street": null,
    "client_city": null,
    "client_state": null,
    "client_zipcode": null,
    "client_home_phone": null,
    "client_cell_phone": null,
    "coclient_name": null,
    "coclient_ssn": null,
    "coclient_dob": null,
    "coclient_employer": null,
    "coclient_title": null,
    "coclient_classification": null,
    "coclient_email": null,
    "is_married_to_coclient": null,
    "has_security_clearance": null,
    "is_in_bankruptcy": null,
    "is_enrolled_in_credit_counseling": null,
    "client_signature": null,
    "client_signature_date": null,
    "coclient_signature": null,
    "coclient_signature_date": null
  }},
  "clixsign_sender": {{
    "package_id": null,
    "package_title": null,
    "final_status": null,
    "final_status_date": null,
    "sending_entity": null,
    "sender_name": null,
    "sender_email_address": null,
    "sender_ip_address": null,
    "signers_count": null
  }},
  "clixsign_signers": [
    {{
      "package_id": null,
      "signer_name": null,
      "signer_email_address": null,
      "signer_ip_address": null,
      "signer_user_agent": null,
      "package_opened_at": null,
      "signature_adopted_at": null,
      "package_signed_at": null
    }}
  ],
  "cancellation_notice": {{
    "cancellation_deadline": null,
    "cancellation_date": null,
        "client_signature": null,
        "client_signature_date": null,
        "coclient_signature": null,
    "coclient_signature_date": null
      }}
    }}

Extract only sections that are present. Use null for missing fields within each section.
    """

# Validation prompt
def get_validation_prompt(extracted_data: Dict[str, Any]) -> str:
    """Simple validation prompt."""
    return f"""
{extracted_data}

{{
  "validation_passed": true,
  "confidence_score": 0.95,
  "flagged_fields": [],
  "corrected_data": {{}}
}}
    """