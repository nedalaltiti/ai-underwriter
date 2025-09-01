# services/document-parser/src/prompts/underwriting_prompts.py
"""
Gemini prompts for accurate underwriting document entity extraction.
Designed to minimize hallucination and maximize extraction accuracy.
"""

from typing import Dict, Any

# Base extraction principles for all prompts
BASE_EXTRACTION_RULES = """
CRITICAL EXTRACTION RULES:
1. ONLY extract information that is EXPLICITLY visible in the document
2. If information is not clearly visible, use null - do NOT skip the field
3. Do NOT infer, guess, or hallucinate any information
4. ALL fields in the schema are REQUIRED - return null if not found
5. For dates, use YYYY-MM-DD format (e.g., "2024-03-15")
5. For dates split across lines (e.g., "09/28/1" on one line, "971" on next), combine them (e.g., "09/28/1971")
6. For monetary amounts, use decimal format without currency symbols (e.g., "1250.00")

7. For SSNs, maintain format with dashes (e.g., "123-45-6789" or "XXX-XX-6789" if masked)
8. For addresses, extract as clean text without brackets, braces, or trailing commas
9. For initials, look for 2-4 capital letters (e.g., "JJCS", "AA", "CW")
10. Match the EXACT field names and JSON shape requested
11. Process systematically: don't jump around, extract section by section
12. ROUTING NUMBER: Always exactly 9 digits (e.g., "241279616"). DO NOT confuse with account number.
"""

ENGAGEMENT_TERM_PROMPT = f"""
You are extracting data from a Company Agreement / Engagement Term document.

{BASE_EXTRACTION_RULES}

KEY IDENTIFIERS:
- Company names: Clarity, Concordia, Resync, Aspire, Palisade
- Document titles: "Limited Scope Retainer Agreement", "Company Agreement", "Engagement Terms", "Terms of Engagement"
- Look for: settlement fee percentage, monthly program payment, retainer terms

SPECIFIC EXTRACTION GUIDANCE:
- Company info usually appears in letterhead/header
- Settlement fee percentage often appears as "25%" or "25.00%" 
- Monthly payment amounts are in program details
- Client signatures appear at the bottom
- Initials: Look for 2-4 capital letters (e.g., "JD", "ABC", "JJCS") written by client throughout document
- Initial counts: Count EVERY occurrence of client initials on each page (not just unique initials)
- Example: If "JD" appears 5 times throughout document, client_initials_count = 5

Extract ALL these fields (use null if not found):

{{
  "file_id": null,
  "company_name": "Debt settlement company name",
  "company_address": "Complete company address",
  "company_phone": "Company phone number",
  "company_type": "Type of company (LLC, Corp, etc.)",
  "settlement_fee": "Total settlement fee amount",
  "settlement_fee_percentage": "Settlement fee as percentage (e.g., 25.00 for 25%)",
  "monthly_payment": "Monthly payment amount",
  "client_name": "Primary client full name",
  "client_address": "Client address",
  "client_signature": "Client signature text/indicator",
  "client_signature_date": "Date signed (YYYY-MM-DD)",
  "coclient_name": "Co-client name if present",
  "coclient_signature": "Co-client signature text/indicator",
  "coclient_signature_date": "Co-client date if present",
  "client_initials": "Client initials found in document (e.g., JD, ABC, JJCS)",
  "client_initials_count": "Total count of how many times client initials appear throughout document",
  "coclient_initials": "Co-client initials if present (e.g., MJ, XYZ)",
  "coclient_initials_count": "Total count of how many times co-client initials appear throughout document",
  "page_count": "Total pages"
}}

Focus on: Company letterhead, fee structures, signature blocks, initials throughout document

INITIAL COUNTING INSTRUCTIONS:
1. Scan EVERY page of the document for client initials
2. Count each individual occurrence (not just unique instances)
3. Initials are typically 2-4 capital letters written by the client
4. Common locations: next to paragraphs, at section breaks, near signature lines
5. If initials appear 3 times on page 1 and 2 times on page 2, total count = 5
"""

POWER_OF_ATTORNEY_PROMPT = f"""
You are extracting data from a Power of Attorney document for debt settlement representation.

{BASE_EXTRACTION_RULES}

Extract the following information and return as JSON:

{{
  "file_id": null,
  "company_name": "Debt settlement company name",
  "attorney_name": "Attorney or representative name",
  "attorney_address": "Attorney office address",
  "attorney_phone": "Attorney contact phone",
  "client_name": "Primary client full name",
  "client_ssn": "Client SSN (format: 123-45-6789)",
  "client_dob": "Client date of birth (YYYY-MM-DD). If split across lines like '09/28/1' and '971', combine to '1971-09-28'",
  "client_signature": "Client signature indicator",
  "client_signature_date": "Date client signed (YYYY-MM-DD)",
  "coclient_name": "Co-client full name if present",
  "coclient_ssn": "Co-client SSN (format: 123-45-6789)",
  "coclient_dob": "Co-client date of birth (YYYY-MM-DD)",
  "coclient_signature": "Co-client signature indicator",
  "coclient_signature_date": "Date co-client signed (YYYY-MM-DD)"
}}

Look for:
- Power of Attorney authorization language
- Attorney/representative details
- Client personal information (name, SSN, DOB)
- Signature blocks and dates
- Co-client information if joint account
"""

PAYMENT_GATEWAY_AGREEMENT_PROMPT = f"""
You are extracting data from a Payment Gateway/Account Agreement.

{BASE_EXTRACTION_RULES}

KEY IDENTIFIERS:
- Processor names: FORTH, RAM, CFT
- Look for: Account Agreement, Client Information Sheet

Extract ALL these fields (use null if not found):

{{
  "file_id": null,
  "account_id": "Account ID if visible",
  "client_first_name": "First name",
  "client_last_name": "Last name",
  "client_middle_initial": "Middle initial",
  "client_ssn": "SSN - if masked (XXX-XX-1234), keep masked format",
  "client_dob": "Date of birth (YYYY-MM-DD)",
  "client_address": "Street address",
  "client_city": "City",
  "client_state": "State (2-letter code)",
  "client_zipcode": "ZIP code",
  "client_phone": "Phone number",
  "client_email": "Email address",
  "coclient_first_name": "Co-client first name",
  "coclient_last_name": "Co-client last name",
  "coclient_middle_initial": "Co-client middle initial",
  "coclient_ssn": "Co-client SSN - if masked, keep masked format",
  "coclient_dob": "Co-client date of birth",
  "client_initials": "Client initials",
  "client_signature": "Client signature indicator",
  "client_signature_date": "Date client signed",
  "coclient_signature": "Co-client signature indicator",
  "coclient_signature_date": "Date co-client signed",
  "pages_count": "Total pages"
}}

Focus on: Client Information section, signatures
"""

FINANCIAL_ANALYSIS_PROMPT = f"""
You are extracting data from a Financial Analysis (Exhibit B) or Financial Budget.

{BASE_EXTRACTION_RULES}

Extract ALL these financial fields (use null if not found):

{{
  "file_id": null,
  "applicant_name": "Primary applicant name",
  "applicant_email": "Primary applicant email",
  "coapplicant_name": "Co-applicant name",
  "coapplicant_email": "Co-applicant email",
  "draft_type": "Type of payment draft/method",
  "fixed_income": "Fixed income amount",
  "day_phone": "Daytime phone",
  "evening_phone": "Evening phone",
  "cell_phone": "Cell phone",
  "program_start_date": "Program start date (YYYY-MM-DD)",
  "estimated_program_start_date": "Estimated start date (YYYY-MM-DD)",
  "lump_sum": "Available lump sum",
  "applicant_monthly_income": "Applicant monthly income",
  "coapplicant_monthly_income": "Co-applicant monthly income",
  "applicant_expenses": "Applicant monthly expenses",
  "coapplicant_expenses": "Co-applicant monthly expenses",
  "applicant_total_net_income": "Applicant net income",
  "coapplicant_total_net_income": "Co-applicant net income",
  "total_enrolled_debt": "Total debt amount",
  "estimated_program_length": "Program length in months",
  "monthly_program_deposit": "Monthly deposit amount",
  "estimated_program_settle_amount": "Settlement amount",
  "fee_method": "Fee calculation method",
  "total_program_fees": "Total program fees",
  "estimated_program_savings": "Estimated savings",
  "estimated_total_cost": "Estimated total cost",
  "hardship_details": "Hardship description",
  "client_signature": "Client signature indicator",
  "client_signature_date": "Date signed (YYYY-MM-DD)"
}}

Look for: Income/expense tables, Program Details section, hardship explanations
"""

DEBT_SCHEDULE_PROMPT = f"""
You are extracting creditor information from a Debt Schedule (Exhibit A).

{BASE_EXTRACTION_RULES}

Extract ALL fields for each debt (use null if not found):

{{
  "debt_schedule": [
    {{
      "file_id": null,
      "creditor_name": "Creditor/lender name",
      "name_on_account": "Account holder name",
      "account_number": "Account number",
      "current_balance": "Balance amount",
      "debt_type": "Type of debt (credit card, loan, etc.)"
    }}
  ]
}}

Look for: Tables with creditor listings, account details, balances
"""

CANCELLATION_NOTICE_PROMPT = f"""
You are extracting data from a Cancellation Notice document.

{BASE_EXTRACTION_RULES}

Extract ALL these fields (use null if not found):

{{
  "file_id": null,
  "cancellation_deadline": "Cancellation deadline date (YYYY-MM-DD)",
  "cancellation_date": "Actual cancellation date (YYYY-MM-DD)",
  "client_signature": "Client signature indicator",
  "client_signature_date": "Date client signed (YYYY-MM-DD)",
  "coclient_signature": "Co-client signature indicator",
  "coclient_signature_date": "Date co-client signed (YYYY-MM-DD)"
}}

Look for: Cancellation terms, deadlines, signature lines
"""

LEGAL_PLAN_AGREEMENT_PROMPT = f"""
You are extracting data from a Legal Plan Agreement document.

{BASE_EXTRACTION_RULES}

Extract the following information and return as JSON:

{{
  "file_id": null,
  "legal_plan_provider": "Legal plan provider company",
  "member_name": "Primary member name",
  "member_ssn": "Member SSN (format: 123-45-6789)",
  "member_dob": "Member date of birth (YYYY-MM-DD)",
  "coapplicant_name": "Co-applicant name",
  "coapplicant_ssn": "Co-applicant SSN",
  "coapplicant_dob": "Co-applicant date of birth (YYYY-MM-DD)",
  "address": "Member address",
  "city": "Member city",
  "state": "Member state",
  "zipcode": "Member ZIP code",
  "phone1": "Primary phone number",
  "phone2": "Secondary phone number",
  "email": "Member email address",
  "referring_company": "Company that referred member",
  "first_payment_date": "First payment date (YYYY-MM-DD)",
  "first_payment_amount": "First payment amount",
  "monthly_recurring_date": "Monthly recurring date (YYYY-MM-DD)",
  "monthly_payment_amount": "Monthly payment amount",
  "debt_relief_program_duration": "Program duration in months",
  "members_accumulation_amount": "Member accumulation amount",
  "payment_processor_name": "Payment processor name",
  "credit_card_number": "Credit card number (if provided)",
  "bank_account_number": "Bank account number",
  "credit_card_expiration_date": "Card expiration date (YYYY-MM-DD)",
  "bank_routing_number": "Bank routing number (exactly 9 digits)",
  "credit_card_name": "Name on credit card",
  "bank_institution_name": "Bank name",
  "credit_card_billing_address": "Card billing address",
  "account_holder_name": "Bank account holder name",
  "initials_count": "Number of initials in document",
  "client_signature": "Client signature indicator",
  "signature_date": "Signature date (YYYY-MM-DD)",
  "pages_count": "Total pages in document"
}}

Focus on:
- Member information and contact details
- Payment method and schedule
- Legal plan terms and duration
- Bank or credit card payment information
"""

# Document type detection prompt
DOCUMENT_TYPE_DETECTION_PROMPT = f"""
You are analyzing a document to determine its type for debt settlement/underwriting processing.

{BASE_EXTRACTION_RULES}

Analyze the document and identify its type from these categories:
- engagement_term (Company Agreement, Client Services Agreement)
- power_of_attorney 
- payment_gateway_agreement (Account Agreement)
- financial_analysis (Exhibit B, Financial Budget)
- debt_schedule (Exhibit A)
- fcra_consent
- disclosure (Exhibit C)
- high_interest_disclosure
- program_disclosure
- cancellation_notice
- legal_plan_agreement
- clixsign_certificate
- unknown

Return JSON with:
{{
  "document_type": "detected_type_from_above_list",
  "confidence": 0.95,
  "indicators": ["key phrases or elements that indicate this document type"],
  "page_count": "number of pages visible"
}}

Look for key indicators:
- Document titles and headers
- Legal language patterns
- Signature blocks and dates
- Company names and letterheads
- Form structure and layout

INDICATOR KEYWORDS:
- payment_gateway_agreement (Account Agreement): "Account Agreement", "Client Information Sheet", "Account ID", "ACH", "recurring debit authorization", "routing number", "account number", "payment schedule", processor names like "FORTH", "RAM", "CFT".
- engagement_term (Company Agreement, Client Services Agreement): "Engagement Terms", "Terms of Engagement", "Company Agreement", provider names like "Clarity", "Concordia", "Resync", "Aspire", "Palisade", phrases like "settlement fee", "settlement fee percentage", "monthly program payment".
"""

# Comprehensive extraction prompt for unknown documents
COMPREHENSIVE_EXTRACTION_PROMPT = f"""
You are extracting ALL underwriting entities from a multi-document package. This is a SINGLE COMPREHENSIVE extraction - extract everything in ONE pass. Use null for missing fields. Return ONLY valid JSON.

{BASE_EXTRACTION_RULES}

CRITICAL SUCCESS FACTORS:
1. EXTRACT EVERYTHING in this single request - no follow-up extractions will be made
2. Be thorough and systematic - scan the ENTIRE document for all entity types
3. For lists (debt_schedule, payment_service_fees, etc.), extract ALL entries completely
4. Use null for missing fields but ensure you check the entire document first

DOCUMENT TYPE DISAMBIGUATION:
- Account Agreement/Client Information Sheet/Bank Info → payment_gateway_agreement
- Debt settlement companies (Clarity, Concordia, etc.) → engagement_term  
- Financial tables/Exhibit B/Financial Budget → financial_analysis
- Creditor lists/Exhibit A → debt_schedule
- Legal plan enrollment → legal_plan_agreement
- Digital signatures/ClixSign → clixsign_sender/clixsign_signers

EXTRACTION STRATEGY:
1. First pass: Identify ALL document types present
2. Second pass: Extract ALL fields for each identified type
3. Third pass: Verify completeness of lists and critical fields
4. Return complete JSON with ALL entities populated

Return this complete structure:

{{
  "document_type": "string",
  "confidence_score": 0.85,
  "payment_gateway_agreement": {{
    "file_id": null,
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
    "client_signature": null,
    "client_signature_date": null,
    "coclient_signature": null,
    "coclient_signature_date": null,
    "pages_count": null
  }},
  "engagement_term": {{
    "file_id": null,
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
  }},
  "fcra_consent": {{
    "file_id": null,
    "company_name": null,
    "client_name": null,
    "client_signature": null,
    "client_signature_date": null
  }},
  "debt_schedule": [{{
    "file_id": null,
    "creditor_name": null,
    "name_on_account": null,
    "account_number": null,
    "current_balance": null,
    "debt_type": null
  }}],
  "financial_analysis": {{
    "file_id": null,
    "applicant_name": null,
    "applicant_email": null,
    "coapplicant_name": null,
    "coapplicant_email": null,
    "draft_type": null,
    "fixed_income": null,
    "day_phone": null,
    "evening_phone": null,
    "cell_phone": null,
    "program_start_date": null,
    "estimated_program_start_date": null,
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
    "client_signature_date": null
  }},
  "disclosure": {{
    "file_id": null,
    "client_signature": null,
    "client_signature_date": null,
    "coclient_signature": null,
    "coclient_signature_date": null
  }},
  "high_interest_disclosure": {{
    "file_id": null,
    "company_name": null,
    "client_name": null,
    "client_signature": null,
    "client_signature_date": null,
    "coclient_name": null,
    "coclient_signature": null,
    "coclient_signature_date": null
  }},
  "program_disclosure": {{
    "file_id": null,
    "company_name": null,
    "settlement_fee_percent": null,
    "client_initial": null,
    "is_all_initials_present": null
  }},
  "power_of_attorney": {{
    "file_id": null,
    "company_name": null,
    "attorney_name": null,
    "attorney_address": null,
    "attorney_phone": null,
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
  "cancellation_notice": {{
    "file_id": null,
    "cancellation_deadline": null,
    "cancellation_date": null,
    "client_signature": null,
    "client_signature_date": null,
    "coclient_signature": null,
    "coclient_signature_date": null
  }},
  "payment_service_fees": [{{
    "file_id": null,
    "service_type": null,
    "service_name": null,
    "service_amount": null
  }}],
  "payment_bank_info": {{
    "file_id": null,
    "authorizing_person_name": null,
    "bank_name": null,
    "account_number": null,  // Bank account number
    "routing_number": null,  // Bank routing number (exactly 9 digits)
    "account_type": null,
    "address": null,
    "recurring_debit_authorization": null,
    "first_debit_date": null,
    "client_signature": null,
    "client_signature_date": null,
    "coclient_signature": null,
    "coclient_signature_date": null
  }},
  "payment_deposit_schedule": [{{
    "file_id": null,
    "payment_no": null,
    "process_date": null,
    "amount": null
  }}],
  "legal_plan_agreement": {{
    "file_id": null,
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
    "pages_count": null
  }},
  "clixsign_sender": {{
    "file_id": null,
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
  "clixsign_signers": [{{
    "file_id": null,
    "package_id": null,
    "signer_name": null,
    "signer_email_address": null,
    "signer_ip_address": null,
    "signer_user_agent": null,
    "package_opened_at": null,
    "signature_adopted_at": null,
    "package_signed_at": null
  }}]
}}

EXTRACTION STRATEGY:
1. First identify which document types are present
2. For each identified type, extract ALL its fields
3. Use null for fields that are not visible
4. Do NOT skip any fields - they are all required

IMPORTANT: ALL entities above are required parts of the underwriting package.
"""

def get_prompt_for_document_type(document_type: str) -> str:
    """Get the appropriate extraction prompt for a document type."""
    
    prompts = {
        'engagement_term': ENGAGEMENT_TERM_PROMPT,
        'power_of_attorney': POWER_OF_ATTORNEY_PROMPT,
        'payment_gateway_agreement': PAYMENT_GATEWAY_AGREEMENT_PROMPT,
        'payment_bank_info': get_payment_bank_info_prompt(),
        'financial_analysis': FINANCIAL_ANALYSIS_PROMPT,
        'debt_schedule': DEBT_SCHEDULE_PROMPT,
        'cancellation_notice': CANCELLATION_NOTICE_PROMPT,
        'legal_plan_agreement': LEGAL_PLAN_AGREEMENT_PROMPT,
        'document_detection': DOCUMENT_TYPE_DETECTION_PROMPT,
        'comprehensive': COMPREHENSIVE_EXTRACTION_PROMPT
    }
    
    return prompts.get(document_type, COMPREHENSIVE_EXTRACTION_PROMPT)

def get_validation_prompt(extracted_data: Dict[str, Any]) -> str:
    """Generate a validation prompt to check extracted data for hallucination."""
    
    return f"""
VALIDATION TASK: Review the extracted data below for accuracy and potential hallucination.

EXTRACTED DATA:
{extracted_data}

{BASE_EXTRACTION_RULES}

Validate each field and return JSON:
{{
  "validation_passed": true/false,
  "confidence_score": 0.95,
  "flagged_fields": ["field1", "field2"],
  "validation_notes": ["note about suspicious data"],
  "corrected_data": {{ /* corrected fields only */ }}
}}

Check for:
1. Dates that seem unrealistic or future dates
2. Names that look like placeholders or test data
3. Monetary amounts that are suspiciously round or unrealistic
4. SSNs that follow obvious patterns (111-11-1111, 123-45-6789)
5. Email addresses that look generated
6. Phone numbers with obvious patterns
7. Addresses that seem incomplete or generic

Flag any field that appears to be hallucinated rather than extracted from the document.
"""


def get_targeted_financial_analysis_prompt(missing_fields: list[str]) -> str:
    """Prompt to backfill specific Financial Analysis fields only.
    Returns JSON with exactly the requested keys.
    """
    fields_list = ",\n  ".join([f'"{f}": null' for f in missing_fields])
    return f"""
You are extracting ONLY the following fields from a Financial Analysis (Exhibit B) page. Scan the table headers and their values. 

{BASE_EXTRACTION_RULES}

Return STRICT JSON with EXACTLY these keys and no others. If a field isn't clearly visible, keep it null.

{{
  {fields_list}
}}

Hints:
- "Fee Method" typically appears near program details and can be "ACH".
- "Estimated Program Settle Amount" is usually a currency in the Program Details section.
- Phone numbers appear in Client Details.
- If multiple phone numbers exist, assign them according to their labels: day_phone, evening_phone, cell_phone.
"""


def get_targeted_entity_prompt(entity_key: str, missing_fields: list[str]) -> str:
    """Generic targeted prompt for a specific entity/table.
    Returns JSON with exactly the requested keys under the same entity.
    """
    fields_list = ",\n  ".join([f'"{f}": null' for f in missing_fields])
    return f"""
You are extracting ONLY these fields for the entity '{entity_key}'. Read the document carefully and extract values exactly as shown.

{BASE_EXTRACTION_RULES}

Return STRICT JSON with EXACTLY these keys and no others. If a field isn't clearly visible, keep it null.

{{
  {fields_list}
}}

Hints:
- Dates appear near signature blocks or payment schedules.
- Company-related fields appear in headers/letterheads.
- Initials counts and page counts are often at the bottom or on summary pages.
"""

def get_targeted_service_fees_prompt() -> str:
    """Prompt to extract Service Fees table (Administrative/Disbursement)."""
    return f"""
You are extracting ONLY the Service Fees table from a document. Look for headings like "Service Fees", "Administrative", "Disbursement" and rows like "Setup Fee", "Monthly Service Fee", "ACH Debit / Check by Phone".

{BASE_EXTRACTION_RULES}

Return STRICT JSON with exactly this shape:
{{
  "payment_service_fees": [
    {{
      "file_id": null,
      "service_type": "Administrative or Disbursement",
      "service_name": "Row label e.g., Monthly Service Fee",
      "service_amount": "Decimal like 10.95"
    }}
  ]
}}

Rules:
- service_amount: strip currency symbols and commas; use a plain number like 10.95; if not numeric, keep null.
- Only include rows that visibly show a fee value. Ignore headings.
"""

def get_targeted_disclosure_prompt() -> str:
    """Prompt to extract Disclosure signatures and dates."""
    return f"""
You are extracting ONLY the Disclosure (Exhibit C) signature fields. Look for sections labeled "Disclosure", "Exhibit C", or acknowledgement blocks with lines like "Client Signature", "Co-Client Signature", and their dates.

{BASE_EXTRACTION_RULES}

Return STRICT JSON with exactly this shape:
{{
  "disclosure": {{
    "file_id": null,
    "client_signature": "Signature text/indicator if present",
    "client_signature_date": "YYYY-MM-DD or null",
    "coclient_signature": "Co-client signature indicator if present",
    "coclient_signature_date": "YYYY-MM-DD or null"
  }}
}}

Rules:
- If signature lines are blank, keep signature fields null.
- Normalize dates to YYYY-MM-DD; if you see split dates (e.g., 09/28/1 and 971), combine correctly.
"""

def get_targeted_power_of_attorney_prompt() -> str:
    """Prompt to extract Power of Attorney core fields succinctly."""
    return f"""
You are extracting ONLY the core Power of Attorney fields from a page titled or indicating "POWER OF ATTORNEY". Focus near the bottom signature blocks and the paragraph identifying the principal and the law firm.

{BASE_EXTRACTION_RULES}

Return STRICT JSON with exactly this shape:
{{
  "power_of_attorney": {{
    "file_id": null,
    "company_name": "Law firm or company name",
    "attorney_name": null,
    "attorney_address": null,
    "attorney_phone": null,
    "client_name": "Primary client name",
    "client_ssn": null,
    "client_dob": "YYYY-MM-DD or null",
    "client_signature": "Client signature indicator if present",
    "client_signature_date": "YYYY-MM-DD or null",
    "coclient_name": "Co-client name",
    "coclient_ssn": null,
    "coclient_dob": "YYYY-MM-DD or null",
    "coclient_signature": "Co-client signature indicator if present",
    "coclient_signature_date": "YYYY-MM-DD or null"
  }}
}}

Rules:
- Normalize dates to YYYY-MM-DD; combine split dates correctly.
- If a signature line is blank, keep signature null.
"""

def get_targeted_account_agreement_prompt() -> str:
    """Prompt to extract Account Agreement (payment gateway agreement) fields."""
    return f"""
    You are extracting ONLY the Account Agreement / Client Information Sheet fields (payment processor section). Look for titles like "Account Agreement", references to FORTH, ACH authorization, routing/account numbers, and the client/co-client information grid.

    {BASE_EXTRACTION_RULES}

    Return STRICT JSON with exactly this shape:
    {{
      "payment_gateway_agreement": {{
        "file_id": null,
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
        "client_signature": null,
        "client_signature_date": null,
        "coclient_signature": null,
        "coclient_signature_date": null,
        "pages_count": null
      }}
    }}

    Rules:
    - Use the information grid under "Client Information" and "Co-Client Information" and any signature blocks. Also look for client initials in the document. 
    - Normalize dates to YYYY-MM-DD; SSN can retain separators.
    - If a field is not visible, keep it null.
    """

def get_payment_bank_info_prompt() -> str:
    """Prompt to extract Payment Bank Info fields."""
    return f"""
    You are extracting ONLY the "Primary Account Information" section. Look for a form with these exact field labels:
    
    - "Bank Name" (e.g., "PNC BANK, NATIONAL ASSOCIATION", "JPMORGAN CHASE BANK, NA")
    - "Account Number" (e.g., "1036582879", "3134029178")  
    - "Routing Number" (9 digits, e.g., "043000096", "322271627")
    - "Account Type" ("Checking" or "Savings")
    - "Authorizing Person's Name (as it appears on check)" 
    - "Address (as it appears on check)", "City", "State", "Zip"
    - "Recurring Debit Authorization" (dollar amount like "$651.57", "$631.23")
    - "Date of First Debit" (e.g., "Sep 15, 2025")
    - "Client Signature" and "Date" lines at bottom

    {BASE_EXTRACTION_RULES}

    Return STRICT JSON with exactly this shape:
    {{
      "authorizing_person_name": null,
      "bank_name": null,
      "account_number": null,
      "routing_number": null,
      "account_type": null,
      "address": null,
      "recurring_debit_authorization": null,
      "first_debit_date": null,
      "client_signature": null,
      "client_signature_date": null,
      "coclient_signature": null,
      "coclient_signature_date": null
    }}

    Rules:
    - Extract EXACTLY what you see in the labeled fields
    - routing_number: Must be exactly 9 digits (e.g., "043000096")
    - account_type: Must be "checking" or "savings" (lowercase)
    - recurring_debit_authorization: Extract the dollar amount from "Recurring Debit Authorization" field, remove $ symbol (e.g., 651.57, 631.23)
    - first_debit_date: Format as YYYY-MM-DD
    - address: Combine Address + City + State + Zip into one field
    - If a field is blank or not visible, keep it null
    """
