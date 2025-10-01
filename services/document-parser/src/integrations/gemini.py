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
        self.fallback_model_name = self.config.gemini.fallback_model_name
        self.enable_fallback = self.config.gemini.enable_fallback_for_large_docs
        
        # Optimized settings for accuracy
        self.temperature = 0.1  # Lower temperature for less hallucination
        self.top_k = 20  # More focused sampling
        self.top_p = 0.8  # Balanced creativity/accuracy
        self.max_output_tokens = 8192
        
        self.credentials = None
        self.last_token_usage = {}
        self.current_model = self.model_name
        
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
    
    def _build_endpoint_url(self, model_name: Optional[str] = None) -> str:
        """Build the Gemini API endpoint URL."""
        model = model_name or self.model_name
        return (
            f"https://{self.region}-aiplatform.googleapis.com/v1/"
            f"projects/{self.project_id}/locations/{self.region}/"
            f"publishers/google/models/{model}:generateContent"
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
        Document extraction with multi-call fallback for large documents.
        Primary: Single comprehensive call
        Fallback: Multiple sequential calls using entity-specific prompts
        """
        start_time = time.time()
        
        try:
            logger.bind(file_id=file_id).info("extraction.start")
            
            # Try single comprehensive extraction first
            response = None
            try:
                prompt = get_comprehensive_prompt()
                self.current_model = self.model_name
                response = await self._make_gemini_request(prompt, pdf_data, model_name=self.model_name)
            except Exception as e:
                # Check if MAX_TOKENS error - use multi-call extraction
                if "MAX_TOKENS" in str(e) and self.enable_fallback:
                    pdf_size_mb = len(pdf_data.get('data', '')) / 1024 / 1024 * 0.75
                    logger.info(
                        f"gemini.multi_call_extraction doc={file_id} size={pdf_size_mb:.1f}MB reason=MAX_TOKENS"
                    )
                    
                    # Use multi-call extraction strategy
                    response = await self._multi_call_extraction(pdf_data, file_id)
                else:
                    raise
            
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
                    'model': self.current_model,
                    'temperature': self.temperature,
                    'method': 'single_pass'
                }
            }
            
            # Map response to package structure
            self._map_response_to_package(response, package_data)
            
            # Backfill critical entities if missing (e.g., payment_gateway_agreement)
            try:
                await self._backfill_entities_if_missing(pdf_data, file_id, package_data)
            except Exception as backfill_error:
                # Log as debug; continue with what we have
                logger.bind(file_id=file_id, error=str(backfill_error)[:200]).debug("extraction.backfill_skipped")
            
            
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
            # Re-raise NonRetryableError to let processor handle it
            from core.exceptions import NonRetryableError
            if isinstance(e, NonRetryableError):
                raise
            logger.bind(file_id=file_id, error=str(e)).error("extraction.failed")
            return None
    
    async def _multi_call_extraction(self, pdf_data: Dict[str, str], file_id: int) -> Optional[Dict[str, Any]]:
        """
        Multi-call extraction strategy for large documents.
        Uses individual entity-specific prompts from underwriting_prompts.py
        Executes ALL calls in PARALLEL for speed (critical for production).
        """
        import asyncio
        
        logger.bind(file_id=file_id).info("extraction.multi_call_start mode=parallel")
        
        # Define entity types and their corresponding prompt functions
        entity_extractions = [
            ('engagement_term', get_prompt_for_document_type('engagement_term')),
            ('financial_analysis', get_prompt_for_document_type('financial_analysis')),
            ('payment_gateway_agreement', get_prompt_for_document_type('payment_gateway_agreement')),
            ('payment_bank_info', get_prompt_for_document_type('payment_bank_info')),
            ('power_of_attorney', get_prompt_for_document_type('power_of_attorney')),
            ('legal_plan_agreement', get_prompt_for_document_type('legal_plan_agreement')),
            ('debt_schedule', get_prompt_for_document_type('debt_schedule')),
            ('disclosure', get_prompt_for_document_type('disclosure')),
            ('program_disclosure', get_prompt_for_document_type('program_disclosure')),
            ('fcra_consent', get_prompt_for_document_type('fcra_consent')),
            ('payment_service_fees', get_prompt_for_document_type('payment_service_fees')),
            ('payment_deposit_schedule', get_prompt_for_document_type('payment_deposit_schedule')),
            ('attorney_privileged_client_info', get_prompt_for_document_type('attorney_privileged_client_info')),
            ('clixsign_sender', get_prompt_for_document_type('clixsign_sender')),
            ('clixsign_signers', get_prompt_for_document_type('clixsign_signers')),
            ('cancellation_notice', get_prompt_for_document_type('cancellation_notice')),
        ]
        
        # Create all tasks for parallel execution with rate limiting
        async def extract_entity(entity_name: str, prompt: str, delay: float = 0):
            """Extract single entity type with optional delay for rate limiting."""
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                result = await self._make_gemini_request(prompt, pdf_data, model_name=self.model_name)
                return (entity_name, result, None)
            except Exception as e:
                error_msg = str(e)[:200]
                logger.bind(file_id=file_id, entity=entity_name, error=error_msg).debug("extraction.entity_error")
                return (entity_name, None, error_msg)
        
        # Execute in batches of 5 to avoid overwhelming Gemini API (prevents 503)
        batch_size = 5
        all_results = []
        
        for i in range(0, len(entity_extractions), batch_size):
            batch = entity_extractions[i:i+batch_size]
            tasks = [extract_entity(name, prompt, delay=0.1*idx) for idx, (name, prompt) in enumerate(batch)]
            batch_results = await asyncio.gather(*tasks, return_exceptions=False)
            all_results.extend(batch_results)
            logger.bind(file_id=file_id, batch=i//batch_size+1, completed=len(batch)).debug("extraction.batch_complete")
        
        results = all_results
        
        # Process results
        merged_response = {}
        successful_calls = 0
        failed_calls = 0
        
        for entity_name, result, error in results:
            if error:
                failed_calls += 1
                logger.bind(file_id=file_id, entity=entity_name, error=error).warning("extraction.entity_failed")
            elif result:
                # Check if response is wrapped in entity name or raw
                if entity_name in result:
                    # Wrapped format: 
                    merged_response[entity_name] = result[entity_name]
                    successful_calls += 1
                    logger.bind(file_id=file_id, entity=entity_name).debug("extraction.entity_success")
                elif isinstance(result, dict) and any(key != 'file_id' for key in result.keys()):
                    # Unwrapped format:
                    # Wrap it with entity name
                    merged_response[entity_name] = result
                    successful_calls += 1
                    logger.bind(file_id=file_id, entity=entity_name).debug("extraction.entity_success_unwrapped")
                elif isinstance(result, list) and len(result) > 0:
                    # List entities: [{"creditor_name": ...}, ...]
                    merged_response[entity_name] = result
                    successful_calls += 1
                    logger.bind(file_id=file_id, entity=entity_name, count=len(result)).debug("extraction.entity_success_list")
                else:
                    # Entity not found in document (empty result)
                    logger.bind(file_id=file_id, entity=entity_name).debug("extraction.entity_not_found")
            else:
                # No result returned
                logger.bind(file_id=file_id, entity=entity_name).debug("extraction.entity_no_result")
        
        if successful_calls == 0:
            logger.bind(file_id=file_id, failed=failed_calls).error("extraction.all_entities_failed")
            return None
        
        logger.bind(
            file_id=file_id, 
            successful=successful_calls, 
            failed=failed_calls,
            total=len(entity_extractions)
        ).info("extraction.multi_call_complete")
        
        return merged_response
    
    async def _backfill_entities_if_missing(self, pdf_data: Dict[str, str], file_id: int, package_data: Dict[str, Any]) -> None:
        """Run targeted extractions for entities that are missing after the main call.
        - Covers all supported single-entity and list-entity tables
        - Accepts wrapped/unwrapped responses
        - Sequential to avoid rate limits
        """
        import asyncio
        from prompts.underwriting_prompts import get_prompt_for_document_type
        
        # Define backfillable entities
        single_entities = [
            'engagement_term', 'financial_analysis', 'payment_gateway_agreement',
            'payment_bank_info', 'power_of_attorney', 'legal_plan_agreement',
            'fcra_consent', 'disclosure', 'program_disclosure',
            'cancellation_notice', 'attorney_privileged_client_info', 'clixsign_sender'
        ]
        list_entities = [
            'debt_schedule', 'payment_service_fees', 'payment_deposit_schedule', 'clixsign_signers'
        ]
        all_entities = single_entities + list_entities
        
        # Compute missing entities (None or empty list)
        missing_entities = []
        for name in all_entities:
            if name in list_entities:
                lst = package_data.get(name)
                if not lst or (isinstance(lst, list) and len(lst) == 0):
                    missing_entities.append(name)
            else:
                if not package_data.get(name):
                    missing_entities.append(name)
        
        if not missing_entities:
            return
        
        logger.bind(file_id=file_id, entities=missing_entities).info("extraction.backfill_start")
        
        async def fetch_entity(entity_name: str):
            prompt = get_prompt_for_document_type(entity_name)
            try:
                result = await self._make_gemini_request(prompt, pdf_data, model_name=self.model_name)
                if not result:
                    logger.bind(file_id=file_id, entity=entity_name).debug("extraction.backfill_empty")
                    return
                
                # Accept wrapped or unwrapped formats
                payload = None
                if isinstance(result, dict) and entity_name in result and isinstance(result[entity_name], (dict, list)):
                    payload = result[entity_name]
                else:
                    payload = result
                
                # Normalize list vs single
                if entity_name in list_entities:
                    # Ensure list
                    if isinstance(payload, list):
                        package_data[entity_name] = payload
                    elif isinstance(payload, dict):
                        package_data[entity_name] = [payload]
                    else:
                        # Unexpected type, skip
                        logger.bind(file_id=file_id, entity=entity_name).debug("extraction.backfill_ignored_type")
                        return
                else:
                    # Single entity: prefer dict
                    if isinstance(payload, dict):
                        package_data[entity_name] = payload
                    elif isinstance(payload, list) and len(payload) > 0 and isinstance(payload[0], dict):
                        # Some prompts may return single-item list
                        package_data[entity_name] = payload[0]
                    else:
                        logger.bind(file_id=file_id, entity=entity_name).debug("extraction.backfill_ignored_type")
                        return
                
                logger.bind(file_id=file_id, entity=entity_name).info("extraction.backfill_success")
            except Exception as e:
                logger.bind(file_id=file_id, entity=entity_name, error=str(e)[:200]).warning("extraction.backfill_failed")
        
        # Run backfills sequentially to avoid overwhelming the API
        for entity in missing_entities:
            await fetch_entity(entity)
        
        # Update metadata to reflect backfill
        try:
            previous_method = package_data.get('extraction_metadata', {}).get('method')
            if previous_method and 'backfill' not in previous_method:
                package_data['extraction_metadata']['method'] = f"{previous_method}+backfill"
            elif not previous_method:
                package_data.setdefault('extraction_metadata', {})['method'] = 'backfill'
        except Exception:
            # Best-effort only
            pass
    
    @retry(
        stop=stop_after_attempt(2),  # Only 2 attempts max
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        reraise=True
    )
    async def _make_gemini_request(self, prompt: str, pdf_data: Dict[str, str], model_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Make optimized Gemini API request."""
        try:
            url = self._build_endpoint_url(model_name)
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
                        finish_reason = candidate['finishReason']
                        
                        # Raise exception for MAX_TOKENS to enable fallback
                        if finish_reason == 'MAX_TOKENS':
                            from core.exceptions import GeminiMaxTokensError
                            logger.info(f"gemini.max_tokens model={model_name or self.model_name}")
                            raise GeminiMaxTokensError(f"Document exceeds model context window: {finish_reason}")
                        
                        logger.error(f"gemini.blocked reason={finish_reason}")
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
            elif status_code == 404:
                logger.error(f"gemini.model_not_found model={model_name or self.model_name} region={self.region}")
                raise
            elif status_code == 429:
                logger.warning("gemini.rate_limit")
                raise
            else:
                logger.error(f"gemini.http_error status={status_code}")
                raise
        except Exception as e:
            # Don't log NonRetryableError as ERROR - it's expected for invalid PDFs
            from core.exceptions import NonRetryableError
            if isinstance(e, NonRetryableError):
                raise  # Re-raise without logging as error
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
    
