# services/document-parser/src/integrations/gemini_simple.py
"""
Simplified Gemini client for efficient underwriting document extraction.
Focused on accuracy and token efficiency.
"""

import json
import time
import httpx
from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.oauth2 import service_account
from google.auth.transport.requests import Request

from models.underwriting_entities import ExtractedDocumentPackage
from prompts.underwriting_prompts import get_prompt_for_document_type, get_comprehensive_prompt
from utils.json_parser import extract_json_from_response


class GeminiClient:
    """Gemini client focused on efficiency and accuracy."""
    
    def __init__(self, service_account_info: Dict[str, Any] = None, config_instance=None):
        # Configuration
        if config_instance:
            self.config = config_instance
        else:
            from config import config
            self.config = config
            
        # Service account setup
        if service_account_info:
            self.service_account_info = service_account_info
        else:
            service_account_json = self.config.gemini_service_account_json.get_secret_value()
            self.service_account_info = json.loads(service_account_json)
            
        self.project_id = self.service_account_info.get("project_id", self.config.gemini.project_id)
        self.region = self.config.gemini.region
        self.model_name = self.config.gemini.model_name
        
        # Optimized settings for accuracy
        self.temperature = 0.1  # Lower temperature for less hallucination
        self.top_k = 20  # More focused sampling
        self.top_p = 0.8  # Balanced creativity/accuracy
        self.max_output_tokens = 8192
        
        self.credentials = None
        self.last_token_usage = {}
        
        self._initialize_credentials()
    
    def _initialize_credentials(self):
        """Initialize Google Cloud credentials."""
        try:
            service_account_info = self.service_account_info.copy()
            
            # Fix newline handling in private key
            if 'private_key' in service_account_info:
                private_key = service_account_info['private_key']
                if '\\n' in private_key:
                    service_account_info['private_key'] = private_key.replace('\\n', '\n')
            
            self.credentials = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            self.credentials.refresh(Request())
            logger.info("Gemini credentials initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize Gemini credentials: {e}")
            raise
    
    def _build_endpoint_url(self) -> str:
        """Build the Gemini API endpoint URL."""
        return (
            f"https://{self.region}-aiplatform.googleapis.com/v1/"
            f"projects/{self.project_id}/locations/{self.region}/"
            f"publishers/google/models/{self.model_name}:generateContent"
        )
    
    def _prepare_headers(self) -> Dict[str, str]:
        """Prepare request headers with authentication."""
        if not self.credentials.valid:
            self.credentials.refresh(Request())
        
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.credentials.token}"
        }
    
    def _prepare_payload(self, prompt: str, pdf_data: Dict[str, str]) -> Dict[str, Any]:
        """Prepare optimized request payload."""
        return {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {"inlineData": pdf_data}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": self.temperature,
                "topK": self.top_k,
                "topP": self.top_p,
                "maxOutputTokens": self.max_output_tokens,
                "candidateCount": 1
            },
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT", 
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                }
            ]
        }
    
    async def extract_document(self, pdf_data: Dict[str, str], file_id: int) -> Optional[ExtractedDocumentPackage]:
        """
        Document extraction - no retries, no complexity.
        Extract everything in one efficient request.
        """
        start_time = time.time()
        
        try:
            # Use comprehensive prompt for extraction
            prompt = get_comprehensive_prompt()
            
            logger.bind(file_id=file_id).info("extraction.start")
            
            # Extraction call
            response = await self._make_gemini_request(prompt, pdf_data)
            
            if not response:
                logger.bind(file_id=file_id).error("extraction.no_response")
                return None
            
            # Create document package
            package_data = {
                'file_id': file_id,
                'document_type': 'comprehensive',
                'confidence_score': 0.9,
                'extraction_metadata': {
                    'extraction_time': datetime.now().isoformat(),
                    'processing_time_ms': int((time.time() - start_time) * 1000),
                    'model': self.model_name,
                    'temperature': self.temperature,
                    'method': 'single_pass'
                }
            }
            
            # Map response to package structure
            self._map_response_to_package(response, package_data)
            
            
            # Add file_id to all entities
            self._add_file_ids(package_data, file_id)
            
            # Clean data formats
            self._clean_data_formats(package_data)
            
            # Create and return package
            try:
                package = ExtractedDocumentPackage(**package_data)
                logger.bind(
                    file_id=file_id,
                    processing_time_ms=package_data['extraction_metadata']['processing_time_ms']
                ).info("extraction.success")
                return package
                
            except Exception as e:
                logger.bind(file_id=file_id, error=str(e)).error("extraction.validation_failed")
                return None
                
        except Exception as e:
            logger.bind(file_id=file_id, error=str(e)).error("extraction.failed")
            return None
    
    @retry(
        stop=stop_after_attempt(2),  # Only 2 attempts max
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        reraise=True
    )
    async def _make_gemini_request(self, prompt: str, pdf_data: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Make optimized Gemini API request."""
        try:
            url = self._build_endpoint_url()
            headers = self._prepare_headers()
            payload = self._prepare_payload(prompt, pdf_data)
            
            # Calculate timeout based on PDF size
            pdf_size_mb = len(pdf_data.get('data', '')) / 1024 / 1024 * 0.75
            timeout_seconds = min(600, max(120, int(pdf_size_mb * 60)))  # 60s per MB, max 10min
            
            timeout = httpx.Timeout(float(timeout_seconds))
            
            logger.info(f"gemini.request size={pdf_size_mb:.1f}MB timeout={timeout_seconds}s")
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                
                response_data = response.json()
                
                # Extract token usage
                if 'usageMetadata' in response_data:
                    self.last_token_usage = response_data['usageMetadata']
                
                # Extract content
                if 'candidates' in response_data and response_data['candidates']:
                    candidate = response_data['candidates'][0]
                    
                    # Check finish reason
                    if 'finishReason' in candidate and candidate['finishReason'] != 'STOP':
                        logger.error(f"gemini.blocked reason={candidate['finishReason']}")
                        return None
                    
                    if 'content' in candidate and 'parts' in candidate['content']:
                        text_content = candidate['content']['parts'][0].get('text', '')
                        
                        # Parse JSON response
                        json_data = extract_json_from_response(text_content)
                        if json_data:
                            return json_data
                        else:
                            logger.warning("gemini.no_json_found")
                            return None
                
                logger.warning("gemini.unexpected_response_structure")
                return None
                
        except httpx.TimeoutException as e:
            logger.error(f"gemini.timeout after {timeout_seconds}s")
            raise
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            error_text = e.response.text
            
            if status_code == 400 and "no pages" in error_text.lower():
                logger.error("gemini.invalid_pdf")
                from core.exceptions import NonRetryableError
                raise NonRetryableError("Document has no pages")
            elif status_code == 429:
                logger.warning("gemini.rate_limit")
                raise
            else:
                logger.error(f"gemini.http_error status={status_code}")
                raise
        except Exception as e:
            logger.error(f"gemini.request_failed error={str(e)}")
            raise
    
    def _map_response_to_package(self, response: Dict[str, Any], package_data: Dict[str, Any]) -> None:
        """Map Gemini response to package structure."""
        # Direct mapping of entities
        entity_mappings = [
            'engagement_term', 'financial_analysis', 'payment_gateway_agreement',
            'payment_bank_info', 'power_of_attorney', 'legal_plan_agreement',
            'debt_schedule', 'disclosure', 'program_disclosure', 'fcra_consent',
            'payment_service_fees', 'payment_deposit_schedule', 'attorney_privileged_client_info',
            'clixsign_sender', 'clixsign_signers', 'cancellation_notice'
        ]
        
        for entity_name in entity_mappings:
            if entity_name in response and response[entity_name]:
                package_data[entity_name] = response[entity_name]
    
    def _add_file_ids(self, package_data: Dict[str, Any], file_id: int) -> None:
        """Add file_id to all entities."""
        for key, value in package_data.items():
            if key in ['extraction_metadata', 'validation_results']:
                continue
                
            if isinstance(value, dict):
                value['file_id'] = file_id
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        item['file_id'] = file_id
    
    def _clean_data_formats(self, package_data: Dict[str, Any]) -> None:
        """Clean and format data for database storage."""
        for key, value in package_data.items():
            if isinstance(value, dict):
                self._clean_entity_data(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._clean_entity_data(item)
    
    def _clean_entity_data(self, entity: Dict[str, Any]) -> None:
        """Clean individual entity data."""
        for field, value in entity.items():
            if isinstance(value, str):
                # Clean whitespace and newlines for ALL string fields
                value = value.strip()
                
                # Convert multi-line text to single line (generalized for all fields)
                if '\n' in value or '\r' in value:
                    # For address fields, use comma separation
                    if 'address' in field:
                        value = value.replace('\n', ', ').replace('\r', ', ')
                        # Clean up multiple commas
                        import re
                        value = re.sub(r',\s*,', ',', value)
                        value = value.strip().strip(',')
                    else:
                        # For non-address fields, use space separation
                        value = value.replace('\n', ' ').replace('\r', ' ')
                        # Clean up multiple spaces
                        import re
                        value = re.sub(r'\s+', ' ', value)
                        value = value.strip()
                
                # Convert empty strings to None
                if value == '' or value.lower() in ['null', 'none', 'n/a']:
                    entity[field] = None
                    continue
                
                # Clean monetary fields
                if field in ['settlement_fee', 'monthly_payment', 'fixed_income', 'current_balance',
                           'recurring_debit_authorization', 'first_payment_amount', 'monthly_payment_amount',
                           'total_enrolled_debt', 'estimated_program_settle_amount', 'lump_sum',
                           'applicant_monthly_income', 'coapplicant_monthly_income', 'applicant_expenses',
                           'coapplicant_expenses', 'applicant_total_net_income', 'coapplicant_total_net_income',
                           'monthly_program_deposit', 'total_program_fees', 'estimated_program_savings',
                           'estimated_total_cost', 'members_accumulation_amount', 'service_amount', 'amount']:
                    # Handle both English and Spanish number formats
                    cleaned = value.replace(',', '').replace('$', '').replace('€', '').replace('£', '').strip()
                    # Handle Spanish decimal separator (replace comma with period if needed)
                    if ',' in cleaned and '.' not in cleaned:
                        # This might be Spanish decimal format (e.g., "531,80")
                        parts = cleaned.split(',')
                        if len(parts) == 2 and len(parts[1]) <= 2:  # Decimal part should be 1-2 digits
                            cleaned = f"{parts[0]}.{parts[1]}"
                    
                    if cleaned and cleaned.replace('.', '').replace('-', '').isdigit():
                        entity[field] = cleaned
                    else:
                        entity[field] = None
                
                # Clean payment number fields
                elif field in ['payment_no', 'payment_number']:
                    # Ensure payment numbers are clean strings/integers
                    cleaned = value.strip()
                    if cleaned.isdigit():
                        entity[field] = cleaned
                    else:
                        entity[field] = None
                
                # Clean fields with strict length constraints
                elif field in ['client_middle_initial', 'coclient_middle_initial']:
                    # Middle initial should be 1 character only
                    cleaned = value.strip()
                    if cleaned and cleaned.isalpha():
                        entity[field] = cleaned[0].upper()  # Take only first character
                    else:
                        entity[field] = None
                
                elif field in ['client_state', 'state']:
                    # State should be 2 characters only
                    cleaned = value.strip().upper()
                    if cleaned and cleaned.isalpha() and len(cleaned) <= 2:
                        entity[field] = cleaned
                    else:
                        entity[field] = None
                
                # Clean percentage fields
                elif field in ['settlement_fee_percentage', 'settlement_fee_percent']:
                    cleaned = value.replace('%', '').strip()
                    if cleaned and cleaned.replace('.', '').isdigit():
                        entity[field] = cleaned
                    else:
                        entity[field] = None
                
                # Clean date fields
                elif 'date' in field or 'dob' in field or 'deadline' in field:
                    if value:
                        try:
                            # Handle multiple date formats
                            import re
                            from datetime import datetime
                            
                            # Remove any extra whitespace
                            date_str = value.strip()
                            
                            # Format 1: MM/DD/YYYY (e.g., "07/14/1980", "12/14/1953")
                            if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', date_str):
                                parts = date_str.split('/')
                                if len(parts) == 3:
                                    month, day, year = parts
                                    entity[field] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                            
                            # Format 1b: MM-DD-YYYY (e.g., "09-01-2025")
                            elif re.match(r'^\d{1,2}-\d{1,2}-\d{4}$', date_str):
                                parts = date_str.split('-')
                                if len(parts) == 3:
                                    month, day, year = parts
                                    entity[field] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                            
                            # Format 2: "Sep 25, 2025" or "September 25, 2025"
                            elif re.match(r'^[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}$', date_str):
                                try:
                                    parsed_date = datetime.strptime(date_str, "%b %d, %Y")
                                    entity[field] = parsed_date.strftime("%Y-%m-%d")
                                except:
                                    try:
                                        parsed_date = datetime.strptime(date_str, "%B %d, %Y")
                                        entity[field] = parsed_date.strftime("%Y-%m-%d")
                                    except:
                                        entity[field] = None
                            
                            # Format 3: Already in YYYY-MM-DD format
                            elif re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                                entity[field] = date_str
                            
                            # Format 4: YYYY/MM/DD
                            elif re.match(r'^\d{4}/\d{1,2}/\d{1,2}$', date_str):
                                parts = date_str.split('/')
                                if len(parts) == 3:
                                    year, month, day = parts
                                    entity[field] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                            
                            # If no format matches, set to None
                            else:
                                entity[field] = None
                                
                        except:
                            entity[field] = None
                    else:
                        entity[field] = None
                
                # Clean SSN fields
                elif 'ssn' in field and value:
                    # Ensure proper SSN format
                    digits = ''.join(filter(str.isdigit, value))
                    if len(digits) == 9:
                        entity[field] = f"{digits[0:3]}-{digits[3:5]}-{digits[5:9]}"
                    elif len(digits) == 4:
                        entity[field] = f"XXX-XX-{digits}"
                    else:
                        entity[field] = value
                
                # Clean account_type field
                elif field == 'account_type' and value:
                    # Normalize to lowercase for Pydantic validation
                    normalized = value.lower().strip()
                    if normalized in ['checking', 'savings']:
                        entity[field] = normalized
                    else:
                        entity[field] = None
                
                else:
                    entity[field] = value
    
    def health_check(self) -> bool:
        """Check if client is healthy."""
        try:
            return self.credentials and self.credentials.valid
        except Exception:
            return False
    
    def get_last_token_usage(self) -> Dict[str, Any]:
        """Get token usage from last request."""
        return self.last_token_usage
    
