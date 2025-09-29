# services/document-parser/src/prompts/underwriting_prompts_new.py
"""
Simplified, efficient prompts for underwriting document extraction.
Designed for maximum accuracy with minimal token usage.
"""

from typing import Dict, Any

# Core extraction rules - simple and direct
BASE_RULES = """
RULES:
1. Extract only what is clearly visible
2. Use null for missing fields - never guess
3. Dates: YYYY-MM-DD format
4. Money: decimal without $ (e.g. "1250.00")
5. SSNs: with dashes (e.g. "123-45-6789")
6. Signatures: actual names, not labels
"""

def get_engagement_term_prompt() -> str:
    """Terms of Engagement / Company Agreement extraction."""
    return f"""
{BASE_RULES}

Extract from Terms of Engagement section. Based on contracts, client initials appear on pages 2-6, signatures on page 6 or 11.

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

Look for: Clarity/Concordia/Aspire companies, settlement fee %, client initials throughout engagement pages, signatures at end.
"""

def get_financial_analysis_prompt() -> str:
    """Financial Analysis / Budget extraction.""" 
    return f"""
{BASE_RULES}

Extract from Financial Analysis/Budget section. Look for income/expense tables and signature at end.

Return JSON:
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

Look for: Income/expense tables, program details, phone numbers, signatures.
"""

def get_payment_gateway_prompt() -> str:
    """Payment Gateway / Account Agreement extraction."""
    return f"""
{BASE_RULES}

Extract from Account Agreement section. Based on contracts, initials on page 28 or 34, signatures on page 36 or 41.

Return JSON:
{{
  "account_id": null,
  "client_first_name": null,
  "client_last_name": null,
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
  "coclient_ssn": null,
  "client_initials": null,
  "client_signature": null,
  "client_signature_date": null,
  "coclient_signature": null,
  "coclient_signature_date": null
}}

Look for: FORTH processor, client information grid, initials, signatures.
"""

def get_payment_bank_info_prompt() -> str:
    """Primary Account Information extraction."""
    return f"""
{BASE_RULES}

Extract from Primary Account Information section. Based on contracts, signatures on page 29 or 35.

Return JSON:
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

Look for: Bank name, account/routing numbers, address components (street, city, state, zip), recurring debit amount, signature.
"""

def get_power_of_attorney_prompt() -> str:
    """Power of Attorney extraction."""
    return f"""
{BASE_RULES}

Extract from Power of Attorney section. Based on contracts, signatures on page 17 or 31.

Return JSON:
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

Look for: Law firm name, client personal info, signatures. SSNs should be FULL 9-digit format.
"""

def get_legal_plan_prompt() -> str:
    """VLP Terms Agreement extraction."""
    return f"""
{BASE_RULES}

Extract from VLP Terms Agreement section. Based on contracts:
- Page 30/23: VLP Terms (signature)  
- Page 31/24: Member Acknowledgement (initials & signature)
- Page 32/25: Member Information (signature)

Return JSON:
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

Look for: VLP provider, member info, payment amounts, multiple signatures across pages.
"""

def get_debt_schedule_prompt() -> str:
    """Debt Schedule extraction."""
    return f"""
{BASE_RULES}

Extract from debt/creditor listing tables.

Return JSON:
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

Look for: Tables with creditor names, account numbers, balances.
"""

def get_disclosure_prompt() -> str:
    """Disclosure sections extraction."""
    return f"""
{BASE_RULES}

Extract from disclosure sections. Look for multiple disclosure sections like 11 USC § 527(a) and 11 USC § 527(b). Based on contracts, signatures on pages 18, 20, etc.

Return JSON:
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

Look for: Federal disclosures (11 USC § 527), multiple disclosure sections, signature blocks, client initials.
"""

def get_program_disclosure_prompt() -> str:
    """Program Disclosure extraction."""
    return f"""
{BASE_RULES}

Extract from Program Disclosure section. Based on contracts, initials on pages 23-24 or 18-22.

Return JSON:
{{
  "company_name": null,
  "settlement_fee_percent": null,
  "client_initials": null,
  "coclient_initials": null,
  "client_initials_count": null,
  "is_all_initials_present": null
}}

Look for: Debt resolution company, settlement fee %, client initials throughout disclosure pages.
"""

def get_fcra_prompt() -> str:
    """FCRA Authorization extraction."""
    return f"""
{BASE_RULES}

Extract from FCRA Authorization section. Based on contracts, signatures on page 7 or 12.

Return JSON:
{{
  "company_name": null,
  "client_name": null,
  "client_signature": null,
  "client_signature_date": null
}}

Look for: FCRA authorization language, client signature.
"""

def get_payment_service_fees_prompt() -> str:
    """Payment Service Fees table extraction."""
    return f"""
{BASE_RULES}

Extract from Service Fees table. Look for "Administrative"/"Administrativa" and "Disbursement"/"Desembolso" columns with fee amounts.

Return JSON:
{{
  "payment_service_fees": [
    {{
      "service_type": "Administrative or Disbursement",
      "service_name": "Fee name in English or Spanish",
      "service_amount": "Amount without $ symbol (e.g., 10.95)"
    }}
  ]
}}

SPANISH/ENGLISH FEE MAPPING:
- Tarifa de instalación / Setup Fee
- Tarifa de servicio mensual / Monthly Service Fee  
- Tarifa por suspensión de pago / Stop Payment Fee
- Tarifa de depósito del Cliente / Client Deposit Fee
- Tarifa de depósito de terceros / Third Party Deposit Fee
- Tarifa por rechazo del depósito / Reject Deposit Fee
- Tarifa por elemento devuelto / Returned Item Fee
- Débito ACH/Cheque por teléfono / ACH Debit/Check by Phone
- Transferencia bancaria / Bank Wire
- Cheque / Check
- Cheque al segundo día / Check 2nd Day
- Cheque durante la noche / Check Overnight
- Pago Directo / Direct Pay

Look for: Service Fees table with Administrative/Disbursement or Administrativa/Desembolso columns, fee names and amounts in any language.
"""

def get_payment_deposit_schedule_prompt() -> str:
    """Payment Deposit Schedule table extraction."""
    return f"""
{BASE_RULES}

Extract from Deposit Schedule table. Look for payment numbers, process dates, and amounts. CRITICAL: Extract ALL rows from the table, not just the first few.

Return JSON:
{{
  "payment_deposit_schedule": [
    {{
      "payment_no": "Payment number (e.g., 1, 2, 3)",
      "process_date": "Process date (YYYY-MM-DD format)",
      "amount": "Payment amount without $ symbol (e.g., 212.07)"
    }}
  ]
}}

SPANISH/ENGLISH TABLE HEADERS:
- Payment # / Pago #
- Process Date / Fecha de Proceso  
- Amount / Cantidad
- Deposit Schedule / Calendario De Depósito

CRITICAL: Scan the ENTIRE table from first row to last row. Extract EVERY payment entry, not just the first 3-5 rows. Tables may have 30-50+ payment entries.

Look for: Complete deposit schedule table with ALL payment entries in English or Spanish.
"""

def get_attorney_privileged_client_info_prompt() -> str:
    """Attorney Client Privileged Information extraction."""
    return f"""
{BASE_RULES}

Extract from Attorney Client Privileged / Client Information form. Look for client details, employment info, and yes/no questions.

Return JSON:
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

Look for: Client Information section, Employment Information, Contact Information, yes/no questions, signature lines.
"""

def get_clixsign_sender_prompt() -> str:
    """Clixsign Sender Information extraction."""
    return f"""
{BASE_RULES}

Extract from "Clixsign Completion Certificate" document. Look for these specific sections:

1. "Signature Package Details" table with columns: Final Status, Final Status Date, Package Title, Package ID, # of Signers
2. "Sender Information" table with columns: Name, Email Address, IP Address, Sending Entity

Return JSON with EXACT field names:
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

SPECIFIC EXTRACTION GUIDANCE:
- package_id: Look for "Package ID" value (numeric)
- package_title: Look for "Package Title" text
- final_status: Look for "Final Status" (e.g., "Completed")
- final_status_date: Look for "Final Status Date" timestamp
- sending_entity: Look for "Sending Entity" company name
- sender_name: Look for sender "Name" 
- sender_email_address: Look for sender "Email Address"
- sender_ip_address: Look for sender "IP Address"
- signers_count: Look for "# of Signers" number
"""

def get_clixsign_signers_prompt() -> str:
    """Clixsign Signers Information extraction."""
    return f"""
{BASE_RULES}

Extract from "Clixsign Completion Certificate" document. Look for "Signers" section with signer details.

Return JSON with EXACT field names:
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

SPECIFIC EXTRACTION GUIDANCE:
- package_id: Same Package ID from package details
- signer_name: Look for signer name 
- signer_email_address: Look for "Email Address" under signer
- signer_ip_address: Look for "IP Address" under signer  
- signer_user_agent: Look for "User Agent" technical details
- package_opened_at: Look for "Package Opened At" timestamp
- signature_adopted_at: Look for "Signature Adopted At" timestamp
- package_signed_at: Look for "Package Signed At" timestamp

NOTE: Keep timestamps in original format (e.g., "2025-08-29T12:27:43-05:00")
"""

def get_cancellation_notice_prompt() -> str:
    """Cancellation Notice / Right of Rescission extraction."""
    return f"""
{BASE_RULES}

Extract from Notice of Right of Rescission / Cancellation Notice section.

Return JSON:
{{
  "cancellation_deadline": null,
  "cancellation_date": null,
    "client_signature": null,
    "client_signature_date": null,
    "coclient_signature": null,
  "coclient_signature_date": null
}}

Look for: Transaction dates, cancellation deadlines, signature blocks at bottom.
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

CRITICAL: Extract ALL table rows completely. For tables, scan entire table from top to bottom.

Extract all sections present:

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
      "service_type": "Administrative",
      "service_name": "Setup Fee",
      "service_amount": "10.95"
    }},
    {{
      "service_type": "Administrative", 
      "service_name": "Monthly Service Fee",
      "service_amount": "10.95"
    }},
    {{
      "service_type": "Administrative",
      "service_name": "Stop Payment Fee", 
      "service_amount": "20.00"
    }},
    {{
      "service_type": "Disbursement",
      "service_name": "ACH Debit / Check by Phone",
      "service_amount": "6.00"
    }},
    {{
      "service_type": "Disbursement",
      "service_name": "Bank Wire",
      "service_amount": "25.00"
    }},
    {{
      "service_type": "Disbursement", 
      "service_name": "Check",
      "service_amount": "12.00"
    }}
  ],
  "payment_deposit_schedule": [
    {{
      "payment_no": "1",
      "process_date": "2025-09-26", 
      "amount": "212.07"
    }},
    {{
      "payment_no": "2",
      "process_date": "2025-10-10",
      "amount": "212.07"
    }},
    {{
      "payment_no": "3",
      "process_date": "2025-10-24",
      "amount": "212.07"
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

# Validation prompt - simplified
def get_validation_prompt(extracted_data: Dict[str, Any]) -> str:
    """Simple validation prompt."""
    return f"""
Review this extracted data for obvious errors:
{extracted_data}

Return JSON:
{{
  "validation_passed": true,
  "confidence_score": 0.95,
  "flagged_fields": [],
  "corrected_data": {{}}
}}

Flag only clear errors like future dates, obvious test data, or impossible values.
    """