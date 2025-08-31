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
        
        # Execute extractions in parallel
        if extraction_tasks:
            results = await asyncio.gather(*[task for _, task in extraction_tasks], return_exceptions=True)
            
            # Process results
            for i, (entity_type, _) in enumerate(extraction_tasks):
                if not isinstance(results[i], Exception) and results[i]:
                    if entity_type == 'engagement_term':
                        package_data['engagement_term'] = self._clean_entity(results[i])
                    elif entity_type == 'payment_gateway':
                        package_data['payment_gateway_agreement'] = self._clean_entity(results[i])
                    elif entity_type == 'financial_analysis':
                        package_data['financial_analysis'] = self._clean_entity(results[i])
                    elif entity_type == 'debt_schedule':
                        package_data['debt_schedule'] = results[i].get('debt_schedule', [])
        
        # Add file_id to all entities
        self._add_file_ids(package_data, file_id)
        
        # Create package
        try:
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
  "client_signature": "Signature indicator",
  "client_signature_date": "Date signed YYYY-MM-DD",
  "coclient_name": "Co-client name",
  "coclient_signature": "Co-client signature",
  "coclient_signature_date": "Co-client date",
  "client_initials": "Client initials",
  "client_initials_count": "Number of initials",
  "coclient_initials": "Co-client initials",
  "coclient_initials_count": "Co-client initial count",
  "page_count": "Total pages"
}

Return null for missing fields. ALL fields are required.
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
  "client_signature": "Client signature",
  "client_signature_date": "Client sign date",
  "coclient_signature": "Co-client signature",
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
  "client_signature": "Client signature",
  "client_signature_date": "Sign date YYYY-MM-DD"
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
      "creditor_name": "Creditor name",
      "current_balance": "Balance amount"
    }
  ]
}

Extract ALL creditors in the table. Focus on: creditor names and balances.
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
