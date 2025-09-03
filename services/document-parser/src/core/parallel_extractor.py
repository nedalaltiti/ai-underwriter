# services/document-parser/src/core/parallel_extractor.py
"""
Parallel document extractor that breaks down extraction into smaller chunks
to reduce LLM confusion and improve accuracy.
"""

import asyncio
from typing import Dict, Any, Optional, List
from loguru import logger

from models.underwriting_entities import ExtractedDocumentPackage


class ParallelDocumentExtractor:
    """Extract documents in parallel chunks to reduce cognitive load."""
    
    def __init__(self, gemini_client):
        """Initialize with Gemini client."""
        self.gemini_client = gemini_client
        
    async def extract_parallel(self, pdf_data: Dict[str, str], file_id: int) -> Optional[ExtractedDocumentPackage]:
        """
        Extract document entities in parallel chunks.
        Each chunk focuses on specific entity types to avoid overwhelming the LLM.
        """
        logger.info(f"Starting parallel extraction for file_id: {file_id}")
        
        # Step 1: Detect document type first
        detection_prompt = self._get_simple_detection_prompt()
        detection_result = await self.gemini_client._make_gemini_request(detection_prompt, pdf_data)
        
        if not detection_result:
            logger.warning("Failed to detect document type")
            return None
            
        doc_indicators = detection_result.get('indicators', [])
        logger.info(f"Detected indicators: {doc_indicators}")
        
        # Step 2: Extract core entities in focused chunks
        extraction_tasks = []
        package_data = {
            'file_id': file_id,
            'document_type': detection_result.get('document_type', 'unknown'),
            'confidence_score': detection_result.get('confidence', 0.85)
        }
        
        # Create focused extraction tasks based on detected sections
        if any('engagement' in str(ind).lower() or 'company agreement' in str(ind).lower() for ind in doc_indicators):
            extraction_tasks.append(('engagement_term', self._extract_engagement_term(pdf_data)))
            
        if any('account agreement' in str(ind).lower() or 'payment gateway' in str(ind).lower() for ind in doc_indicators):
            extraction_tasks.append(('payment_gateway', self._extract_payment_gateway(pdf_data)))
            
        if any('financial analysis' in str(ind).lower() or 'exhibit b' in str(ind).lower() for ind in doc_indicators):
            extraction_tasks.append(('financial_analysis', self._extract_financial_analysis(pdf_data)))
            
        if any('debt schedule' in str(ind).lower() or 'exhibit a' in str(ind).lower() for ind in doc_indicators):
            extraction_tasks.append(('debt_schedule', self._extract_debt_schedule(pdf_data)))
            
        if any('attorney' in str(ind).lower() and 'privileged' in str(ind).lower() or 'client information' in str(ind).lower() for ind in doc_indicators):
            extraction_tasks.append(('attorney_privileged', self._extract_attorney_privileged(pdf_data)))
        
        # Execute extractions in parallel
        if extraction_tasks:
            results = await asyncio.gather(*[task for _, task in extraction_tasks], return_exceptions=True)
            
            # Process results
            for i, (entity_type, _) in enumerate(extraction_tasks):
                if not isinstance(results[i], Exception) and results[i]:
                    result_data = results[i]
                    
                    if entity_type == 'engagement_term':
                        if isinstance(result_data, dict):
                            package_data['engagement_term'] = self._clean_entity(result_data)
                    elif entity_type == 'payment_gateway':
                        if isinstance(result_data, dict):
                            package_data['payment_gateway_agreement'] = self._clean_entity(result_data)
                    elif entity_type == 'financial_analysis':
                        if isinstance(result_data, dict):
                            package_data['financial_analysis'] = self._clean_entity(result_data)
                    elif entity_type == 'debt_schedule':
                        if isinstance(result_data, dict):
                            package_data['debt_schedule'] = result_data.get('debt_schedule', [])
                        elif isinstance(result_data, list):
                            package_data['debt_schedule'] = result_data
                        else:
                            package_data['debt_schedule'] = []
                    elif entity_type == 'attorney_privileged':
                        if isinstance(result_data, dict):
                            package_data['attorney_privileged_client_info'] = self._clean_entity(result_data)
                    else:
                        logger.warning(f"Unknown entity type: {entity_type}")
        
        # Add file_id to all entities
        self._add_file_ids(package_data, file_id)
        
        # Create package
        try:
            # Clean date formats before creating package
            self._clean_date_formats(package_data)
            
            package = ExtractedDocumentPackage(**package_data)
            logger.info(f"Successfully created package via parallel extraction")
            return package
        except Exception as e:
            logger.error(f"Failed to create package: {e}")
            return None
    
    def _get_simple_detection_prompt(self) -> str:
        """Get simplified detection prompt."""
        return """
Identify what type of document this is. Look for key indicators:

- Engagement Terms: Settlement company names (Clarity, Concordia, etc), settlement fee %
- Account Agreement: FORTH/RAM/CFT processor, bank account info
- Financial Analysis: Exhibit B, income/expense tables
- Debt Schedule: Exhibit A, creditor list
- Attorney Privileged: Attorney Client Privileged, Client Information forms
- Digital Signatures: ClixSign, Digital signatures
- Cancellation Notice: Cancellation Notice
- Legal Plan Agreement: Legal Plan Agreement
- FCRA Consent: FCRA Consent
- Program Disclosure: Program Disclosure
- Disclosure: Disclosure
- High Interest Disclosure: High Interest Disclosure
- Power of Attorney: Power of Attorney
- Fcra Consumer Report Consent: FCRA Consent
- Bank Info: Bank Info
- Deposit Schedule: Deposit Schedule
- Service Fees: Service Fees


Return:
{
  "document_type": "type detected",
  "confidence": 0.9,
  "indicators": ["list of key phrases found"]
}
"""
    
    async def _extract_engagement_term(self, pdf_data: Dict[str, str]) -> Optional[Dict]:
        """Extract ALL engagement term fields."""
        prompt = """
Extract ALL fields from the Engagement Terms/Company Agreement:

{
  "company_name": "Settlement company name",
  "company_address": "Complete address",
  "company_phone": "Phone number",
  "company_type": "LLC/Corp/etc",
  "settlement_fee": "Total fee amount",
  "settlement_fee_percentage": "Fee % (number only)",
  "monthly_payment": "Monthly payment amount",
  "client_name": "Client full name",
  "client_address": "Client address",
  "client_signature": "Actual client name from signature line",
  "client_signature_date": "Date signed YYYY-MM-DD",
  "coclient_name": "Co-client name",
  "coclient_signature": "Actual co-client name from signature line if present",
  "coclient_signature_date": "Co-client date",
  "client_initials": "Client initials",
  "client_initials_count": "Total count of client initials throughout ENTIRE document until signature page",
  "coclient_initials": "Co-client initials",
  "coclient_initials_count": "Total count of co-client initials throughout ENTIRE document until signature page",
  "page_count": "Total pages",
  "identified_debts_ack_client_signature": "Actual client name from signature line",
  "identified_debts_ack_coclient_signature": "Actual co-client name from signature line if present",
  "privacy_policy_client_initials": "Client initials",
  "privacy_policy_coclient_initials": "Co-client initials if present"
}

Return null for missing fields. ALL fields are required.

CRITICAL: For initial counts, scan ONLY the Engagement Term section:
- Typically pages 0-6 or until you see "Page X of Y" 
- Do NOT count initials from other sections (Financial Analysis, Debt Schedule, etc.)
- Count EVERY occurrence of client initials within the engagement term section only
- Stop when you reach the end of the engagement term section
"""
        return await self.gemini_client._make_gemini_request(prompt, pdf_data)
    
    async def _extract_payment_gateway(self, pdf_data: Dict[str, str]) -> Optional[Dict]:
        """Extract ALL payment gateway fields."""
        prompt = """
Extract ALL fields from the Account Agreement/Payment Gateway:

{
  "account_id": "Account ID",
  "client_first_name": "First name",
  "client_last_name": "Last name",
  "client_middle_initial": "Middle initial",
  "client_ssn": "SSN format XXX-XX-XXXX",
  "client_dob": "Birth date YYYY-MM-DD",
  "client_address": "Street address",
  "client_city": "City",
  "client_state": "State (2-letter)",
  "client_zipcode": "ZIP code",
  "client_phone": "Phone",
  "client_email": "Email",
  "coclient_first_name": "Co-client first name",
  "coclient_last_name": "Co-client last name",
  "coclient_middle_initial": "Co-client middle initial",
  "coclient_ssn": "Co-client SSN",
  "coclient_dob": "Co-client DOB",
  "client_initials": "Client initials",
  "coclient_initials": "Co-client initials if present",
  "client_signature": "Actual client name from signature line",
  "client_signature_date": "Client sign date",
  "coclient_signature": "Actual co-client name from signature line if present",
  "coclient_signature_date": "Co-client sign date",
  "pages_count": "Total pages"
}

Return null for missing fields. ALL fields are required.
"""
        return await self.gemini_client._make_gemini_request(prompt, pdf_data)
    
    async def _extract_financial_analysis(self, pdf_data: Dict[str, str]) -> Optional[Dict]:
        """Extract ALL financial analysis fields."""
        prompt = """
Extract ALL fields from Financial Analysis (Exhibit B):

{
  "applicant_name": "Applicant name",
  "applicant_email": "Applicant email",
  "coapplicant_name": "Co-applicant name",
  "coapplicant_email": "Co-applicant email",
  "draft_type": "Draft type",
  "fixed_income": "Fixed income",
  "day_phone": "Day phone",
  "evening_phone": "Evening phone",
  "cell_phone": "Cell phone",
  "program_start_date": "Start date YYYY-MM-DD",
  "estimated_program_start_date": "Est. start date",
  "lump_sum": "Lump sum amount",
  "applicant_monthly_income": "Applicant income",
  "coapplicant_monthly_income": "Co-applicant income",
  "applicant_expenses": "Applicant expenses",
  "coapplicant_expenses": "Co-applicant expenses",
  "applicant_total_net_income": "Applicant net income",
  "coapplicant_total_net_income": "Co-applicant net income",
  "total_enrolled_debt": "Total debt amount",
  "estimated_program_length": "Program months",
  "monthly_program_deposit": "Monthly deposit",
  "estimated_program_settle_amount": "Settlement amount",
  "fee_method": "Fee method",
  "total_program_fees": "Total fees",
  "estimated_program_savings": "Estimated savings",
  "estimated_total_cost": "Total cost",
  "hardship_details": "Hardship description",
  "client_signature": "Actual client name from signature line",
  "client_signature_date": "Sign date YYYY-MM-DD",
  "coclient_signature": "Actual co-client name from signature line if present",
  "coclient_signature_date": "Co-client sign date YYYY-MM-DD",
  "client_initials": "Client initials",
  "coclient_initials": "Co-client initials if present"
}

Return null for missing fields. ALL fields are required.
"""
        return await self.gemini_client._make_gemini_request(prompt, pdf_data)
    
    async def _extract_debt_schedule(self, pdf_data: Dict[str, str]) -> Optional[Dict]:
        """Extract only debt schedule."""
        prompt = """
Extract creditor list from Debt Schedule (Exhibit A):

{
  "debt_schedule": [
    {
      "file_id": null,
      "creditor_name": "Creditor/lender name",
      "name_on_account": "Account holder name",
      "account_number": "Account number",
      "current_balance": "Balance amount",
      "debt_type": "Type of debt (credit card, loan, etc.)",
      "client_name": "Client name if shown",
      "client_signature": "Actual client name from signature line if present",
      "client_signature_date": "Client signature date if present",
      "coclient_name": "Co-client name if shown", 
      "coclient_signature": "Actual co-client name from signature line if present",
      "coclient_signature_date": "Co-client signature date if present"
    }
  ]
}

Extract ALL creditors in the table. Focus on: creditor names and balances.
"""
        return await self.gemini_client._make_gemini_request(prompt, pdf_data)
    
    async def _extract_attorney_privileged(self, pdf_data: Dict[str, str]) -> Optional[Dict]:
        """Extract ALL attorney privileged client info fields."""
        prompt = """
Extract ALL fields from the Attorney Client Privileged / Client Information section:

{
  "client_name": "Client full name",
  "client_ssn": "Client SSN - if masked, keep masked format",
  "client_dob": "Client date of birth YYYY-MM-DD",
  "client_employer": "Main App Employer",
  "client_title": "Job title",
  "client_classification": "Employment classification",
  "client_email": "Main App Email",
  "client_street": "Street address",
  "client_city": "City",
  "client_state": "State (2-letter code)",
  "client_zipcode": "ZIP code",
  "client_home_phone": "Home phone",
  "client_cell_phone": "Cell phone",
  "coclient_name": "Co-client full name",
  "coclient_ssn": "Co-client SSN",
  "coclient_dob": "Co-client date of birth YYYY-MM-DD",
  "coclient_employer": "Co App Employer",
  "coclient_title": "Co-client job title",
  "coclient_classification": "Co-client employment classification",
  "coclient_email": "Co App Email",
  "is_married_to_coclient": "Married to Co-applicant? (true/false)",
  "has_security_clearance": "Security clearance question (true/false)",
  "is_in_bankruptcy": "Currently involved in bankruptcy proceeding? (true/false)",
  "is_enrolled_in_credit_counseling": "Currently enrolled in credit counseling program? (true/false)",
  "client_signature": "Actual client name from signature line (e.g., 'Robert Adams')",
  "client_signature_date": "Client signature date YYYY-MM-DD",
  "coclient_signature": "Actual co-client name from signature line if present",
  "coclient_signature_date": "Co-client signature date YYYY-MM-DD"
}

Return null for missing fields. ALL fields are required.

Focus on:
- Client Information section with personal details
- Employment Information section  
- Contact Information section
- Yes/No questions (marriage, security clearance, bankruptcy, credit counseling)
- Signature blocks at the bottom
"""
        return await self.gemini_client._make_gemini_request(prompt, pdf_data)
    
    def _clean_entity(self, entity: Dict) -> Dict:
        """Clean extracted entity data."""
        if not entity:
            return {}
            
        # Remove empty strings and convert to None
        cleaned = {}
        for key, value in entity.items():
            if isinstance(value, str):
                value = value.strip()
                if value in ['', 'null', 'NULL', 'None', 'N/A', 'n/a']:
                    value = None
            cleaned[key] = value
            
        return cleaned
    
    def _add_file_ids(self, package_data: Dict, file_id: int):
        """Add file_id to all entities."""
        for key, value in package_data.items():
            if isinstance(value, dict) and key not in ['extraction_metadata']:
                value['file_id'] = file_id
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        item['file_id'] = file_id
    
    def _clean_date_formats(self, data: Dict[str, Any]) -> None:
        """Clean date formats to prevent Pydantic validation errors."""
        import re
        
        def clean_date_string(date_str: str) -> str:
            """Convert MM/dd/yyyy or M/d/yyyy to YYYY-MM-DD format."""
            if not isinstance(date_str, str) or not date_str.strip():
                return None
                
            cleaned = re.sub(r"\s+", "", date_str)
            
            # Handle MM/dd/yyyy and M/d/yyyy
            if '/' in cleaned:
                parts = cleaned.split('/')
                if len(parts) == 3:
                    m, d, y = parts[0], parts[1], parts[2]
                    
                    # Handle 2-digit years
                    if len(y) == 2:
                        year_int = int(y)
                        if year_int < 50:
                            y = f"20{y}"
                        else:
                            y = f"19{y}"
                    
                    if len(y) == 4 and m.isdigit() and d.isdigit():
                        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
            
            return None
        
        # Date fields that need cleaning
        date_fields = [
            'client_dob', 'coclient_dob', 'member_dob', 'coapplicant_dob',
            'signature_date', 'client_signature_date', 'coclient_signature_date',
            'cancellation_deadline', 'cancellation_date',
            'first_payment_date', 'process_date', 'first_debit_date', 
            'program_start_date', 'estimated_program_start_date',
            'credit_card_expiration_date', 'monthly_recurring_date'
        ]
        
        # Clean dates recursively
        def clean_entity_dates(entity):
            if isinstance(entity, dict):
                for field, value in entity.items():
                    if field in date_fields and isinstance(value, str):
                        cleaned = clean_date_string(value)
                        entity[field] = cleaned
                    elif isinstance(value, dict):
                        clean_entity_dates(value)
                    elif isinstance(value, list):
                        for item in value:
                            clean_entity_dates(item)
        
        clean_entity_dates(data)
