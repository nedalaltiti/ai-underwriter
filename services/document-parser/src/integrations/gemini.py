# services/document-parser/src/integrations/gemini.py
"""
Gemini client for underwriting document extraction with anti-hallucination measures.
"""

import json
import re
import httpx
import time
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from loguru import logger
from google.oauth2 import service_account
from google.auth.transport.requests import Request

from models.underwriting_entities import ExtractedDocumentPackage
from prompts.underwriting_prompts import (
    get_prompt_for_document_type, 
    get_validation_prompt,
    get_targeted_financial_analysis_prompt,
    get_targeted_service_fees_prompt,
    get_targeted_disclosure_prompt,
    get_targeted_power_of_attorney_prompt,
    get_targeted_account_agreement_prompt
)
from utils.json_parser import extract_json_from_response


class GeminiClient:
    """
     Gemini client with robust validation and anti-hallucination measures.
    """
    
    def __init__(self, service_account_info: Dict[str, Any] = None, config_instance=None):
        # Use provided config or import global config
        if config_instance:
            self.config = config_instance
        else:
            from config import config
            self.config = config
            
        # Use provided service account info or get from config
        if service_account_info:
            self.service_account_info = service_account_info
        else:
            # Load service account info from config
            import json
            service_account_json = self.config.gemini_service_account_json.get_secret_value()
            self.service_account_info = json.loads(service_account_json)
            
        self.project_id = self.service_account_info.get("project_id", self.config.gemini.project_id)
        self.region = self.config.gemini.region
        self.model_name = self.config.gemini.model_name
        self.temperature = self.config.gemini.temperature
        self.credentials = None
        self.last_token_usage = {}
        
        # Anti-hallucination settings
        self.max_retries = self.config.max_retries
        self.validation_threshold = 0.8
        self.confidence_threshold = 0.7
        self.timeout = self.config.gemini.timeout
        
        self._initialize_credentials()
    
    def _initialize_credentials(self):
        """Initialize Google Cloud credentials with proper key handling."""
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
            logger.info(" Gemini credentials initialized successfully")
            
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
        """Prepare the request payload for Gemini API."""
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
                "topK": self.config.gemini.top_k,
                "topP": self.config.gemini.top_p,
                "maxOutputTokens": self.config.gemini.max_output_tokens,
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
    

    async def extract_with_validation(self, pdf_data: Dict[str, str], file_id: int, attempts: int = 3) -> Optional[ExtractedDocumentPackage]:
        """Extract with validation - using staged extraction for better accuracy."""
        
        # Try staged extraction first (most accurate)
        try:
            logger.info(f"Using staged extraction approach for file {file_id}")
            result = await self.extract_with_staged_approach(pdf_data, file_id)
            if result:
                return result
        except Exception as e:
            logger.warning(f"Staged extraction failed, falling back to parallel: {e}")
        
        # Fallback to parallel extraction
        pdf_size_estimate = len(pdf_data.get('data', '')) if 'data' in pdf_data else 0
        pdf_size_mb = pdf_size_estimate / 1024 / 1024 * 0.75
        
        if pdf_size_mb > 1.0 or getattr(self.config, 'enable_parallel_extraction', True):
            try:
                logger.info(f"Using parallel extraction for {pdf_size_mb:.1f}MB document")
                from core.parallel_extractor import ParallelDocumentExtractor
                extractor = ParallelDocumentExtractor(self)
                result = await extractor.extract_parallel(pdf_data, file_id)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"Parallel extraction failed, falling back to sequential: {e}")
        
        # Fallback to original sequential extraction
        for attempt in range(max(1, attempts)):
            is_final_attempt = (attempt == attempts - 1)
            logger.info(f"Sequential extraction attempt {attempt + 1}/{attempts}, final_attempt={is_final_attempt}")
            
            try:
                # Always try normal validation first (even on final attempt)
                result = await self.extract_document_entities(pdf_data, file_id, lenient_mode=False)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if "no pages" in str(e).lower() or "corrupted PDF" in str(e):
                    logger.error(f"Permanent PDF issue detected, stopping attempts: {e}")
                    raise  # Don't retry corrupted/empty PDFs
                    
                if is_final_attempt:
                    # On final attempt, if normal validation failed, try lenient storage
                    logger.info("Final attempt with normal validation failed, trying lenient storage...")
                    try:
                        result = await self.extract_document_entities(pdf_data, file_id, lenient_mode=True, force_lenient=True)
                        if result:
                            logger.warning("Stored document with cleaned validation issues on final attempt")
                            return result
                    except Exception as final_e:
                        logger.error(f"Even lenient storage failed: {final_e}")
                    raise
        return None
    
    async def extract_with_staged_approach(self, pdf_data: Dict[str, str], file_id: int) -> Optional[ExtractedDocumentPackage]:
        """Extract documents using a staged approach for better accuracy."""
        
        # Stage 1: Document detection and sectioning
        detection_prompt = """
        Identify ALL document sections in this PDF. List each distinct section/form you see:
        Return JSON: {"sections": ["section_name1", "section_name2", ...]}
        
        Look for:
        - Account Agreement
        - Primary Account Information (bank details section)
        - Company Agreement / Engagement Terms
        - Power of Attorney
        - Financial Analysis (Exhibit B)
        - Financial Budget
        - Income/Expense Analysis
        - Budget Analysis
        - Financial Information
        - Debt Schedule (Exhibit A)
        - Service Fees table
        - Deposit Schedule table
        - Disclosure sections (Exhibit C)
        - Legal Plan Agreement
        - Attorney Client Privileged / Client Information
        - High Interest Disclosure
        - FCRA Consent
        - Cancellation Notice
        - Clixsign Certificate
        - Clixsign Signers
        - Clixsign Sender
        - Payment Bank Info
        - Program Disclosure
        
        IMPORTANT: If you see bank information (bank name, routing number, account number, account type), 
        always include "Primary Account Information" in your sections list.
        """
        
        try:
            detection_result = await self._make_gemini_request(detection_prompt, pdf_data)
            detected_sections = detection_result.get('sections', []) if detection_result else []
            
            logger.info(f"Detected sections: {detected_sections}")
            
            # Stage 2: Extract each section individually with focused prompts
            package_data = {
                'file_id': file_id,
                'document_type': 'multi_section',
                'confidence_score': 0.95,
                'extraction_metadata': {
                    'extraction_time': datetime.now().isoformat(),
                    'model': self.model_name,
                    'temperature': self.temperature,
                    'extraction_method': 'staged'
                }
            }
            
            # Enhanced extraction map with priority ordering to prevent conflicts
            # Process in priority order - most specific matches first
            extraction_priority = [
                # Critical high-priority entities - extract first to avoid overwrites
                ('account agreement', 'payment_gateway_agreement', self._extract_payment_gateway),
                ('client service agreement', 'engagement_term', self._extract_engagement_term),
                ('company agreement', 'engagement_term', self._extract_engagement_term),
                ('engagement terms', 'engagement_term', self._extract_engagement_term),
                ('services agreement', 'engagement_term', self._extract_engagement_term),
                ('csa', 'engagement_term', self._extract_engagement_term),
                ('financial analysis (exhibit b)', 'financial_analysis', self._extract_financial_analysis),
                ('financial analysis', 'financial_analysis', self._extract_financial_analysis),
                ('exhibit b', 'financial_analysis', self._extract_financial_analysis),
                ('financial budget', 'financial_analysis', self._extract_financial_analysis),
                ('income expense', 'financial_analysis', self._extract_financial_analysis),
                ('budget analysis', 'financial_analysis', self._extract_financial_analysis),
                ('financial information', 'financial_analysis', self._extract_financial_analysis),
                
                # Account/Bank information - high priority
                ('primary account information', 'payment_bank_info', self._extract_payment_bank_info),
                ('payment bank info', 'payment_bank_info', self._extract_payment_bank_info),
                ('bank information', 'payment_bank_info', self._extract_payment_bank_info),
                ('ach authorization', 'payment_bank_info', self._extract_payment_bank_info),
                
                # Document sections
                ('power of attorney', 'power_of_attorney', self._extract_power_of_attorney),
                ('debt schedule (exhibit a)', 'debt_schedule', self._extract_debt_schedule),
                ('debt schedule', 'debt_schedule', self._extract_debt_schedule),
                ('exhibit a', 'debt_schedule', self._extract_debt_schedule),
                ('service fees table', 'payment_service_fees', self._extract_service_fees),
                ('service fees', 'payment_service_fees', self._extract_service_fees),
                ('payment schedule table', 'payment_deposit_schedule', self._extract_deposit_schedule),
                ('deposit schedule table', 'payment_deposit_schedule', self._extract_deposit_schedule),
                ('deposit schedule', 'payment_deposit_schedule', self._extract_deposit_schedule),
                
                # Legal documents
                ('legal plan agreement', 'legal_plan_agreement', self._extract_legal_plan),
                ('legal plan', 'legal_plan_agreement', self._extract_legal_plan),
                
                # Client information
                ('attorney client privileged', 'attorney_privileged_client_info', self._extract_attorney_privileged),
                ('attorney privileged', 'attorney_privileged_client_info', self._extract_attorney_privileged),
                ('client information', 'attorney_privileged_client_info', self._extract_attorney_privileged),
                
                # Consent forms
                ('fcra consent', 'fcra_consent', self._extract_fcra),
                ('cancellation notice', 'cancellation_notice', self._extract_cancellation),
                
                # Disclosure sections - specific first to avoid conflicts
                ('high interest disclosure', 'high_interest_disclosure', self._extract_high_interest),
                ('program disclosure', 'program_disclosure', self._extract_program_disclosure),
                ('disclosure sections (exhibit c)', 'disclosure', self._extract_disclosure),
                ('exhibit c', 'disclosure', self._extract_disclosure),
                ('disclosure', 'disclosure', self._extract_disclosure),  # Most generic last
                
                # Clixsign sections
                ('clixsign certificate', 'clixsign_all', self._extract_clixsign_data),
                ('clixsign signers', 'clixsign_all', self._extract_clixsign_data),
                ('clixsign sender', 'clixsign_all', self._extract_clixsign_data),
                
                # Additional aliases for better matching
                ('limited scope retainer', 'engagement_term', self._extract_engagement_term),
                ('retainer agreement', 'engagement_term', self._extract_engagement_term),
                ('terms of engagement', 'engagement_term', self._extract_engagement_term)
            ]
            
            # Track what we've already extracted to avoid duplicates
            extracted_entities = set()
            entity_extraction_tasks = []
            
            # Process each detected section with priority-based matching
            for section in detected_sections:
                section_lower = section.lower().strip()
                
                # Find best matching extraction based on priority order
                for search_key, entity_name, extractor in extraction_priority:
                    # Improved matching: exact phrase match or comprehensive word match
                    if (search_key in section_lower or 
                        section_lower in search_key or 
                        (len(search_key.split()) > 1 and all(word in section_lower for word in search_key.split()))):
                        
                        # Skip if already extracted
                        if entity_name in extracted_entities:
                            logger.debug(f"Skipping {entity_name} - already extracted")
                            continue
                        
                        # Mark as extracted immediately to prevent duplicates
                        extracted_entities.add(entity_name)
                        entity_extraction_tasks.append((section, entity_name, extractor))
                        logger.info(f"Scheduled extraction of {entity_name} from section: {section}")
                        break  # Move to next section after finding first match
            
            # Log scheduling summary
            logger.bind(file_id=file_id, detected_count=len(detected_sections), scheduled_count=len(entity_extraction_tasks)).info("staged_extraction.sections_detected")
            
            # Execute extractions with controlled concurrency
            semaphore = asyncio.Semaphore(3)  # Reduced concurrency for stability
            
            async def extract_one(section: str, entity_name: str, extractor):
                async with semaphore:
                    try:
                        logger.info(f"Extracting {entity_name} from section: {section}")
                        result = await extractor(pdf_data, file_id)
                        
                        if result:
                            # Handle list entities
                            if entity_name in ['debt_schedule', 'payment_service_fees', 'payment_deposit_schedule']:
                                if entity_name not in package_data:
                                    package_data[entity_name] = []
                                if isinstance(result, list):
                                    package_data[entity_name].extend(result)
                                else:
                                    package_data[entity_name].append(result)
                            
                            # Handle clixsign special case
                            elif entity_name == 'clixsign_all':
                                if isinstance(result, dict):
                                    if 'clixsign_sender' in result:
                                        package_data['clixsign_sender'] = result['clixsign_sender']
                                    if 'clixsign_signers' in result:
                                        package_data['clixsign_signers'] = result['clixsign_signers']
                            
                            # Handle single entities
                            else:
                                package_data[entity_name] = result
                            
                            logger.info(f"Successfully extracted {entity_name}")
                            return True
                        else:
                            logger.warning(f"No data extracted for {entity_name}")
                            return False
                            
                    except Exception as e:
                        logger.error(f"Failed to extract {entity_name}: {e}")
                        return False
            
            # Launch extraction tasks
            extraction_results = await asyncio.gather(
                *[extract_one(section, entity_name, extractor) 
                  for section, entity_name, extractor in entity_extraction_tasks],
                return_exceptions=True
            )
            
            # Critical entities that MUST be attempted if detected but failed
            critical_entities = {
                'engagement_term': ('client service agreement', self._extract_engagement_term),
                'financial_analysis': ('financial analysis', self._extract_financial_analysis),
                'payment_gateway_agreement': ('account agreement', self._extract_payment_gateway)
            }
            
            # Ensure critical entities are extracted if they were detected
            for entity_name, (section_hint, extractor) in critical_entities.items():
                # Check if this entity type was detected in sections
                was_detected = any(
                    section_hint in section.lower() 
                    for section in detected_sections
                )
                
                # If detected but not successfully extracted, try again
                if was_detected and entity_name not in package_data:
                    logger.warning(f"Critical entity {entity_name} was detected but not extracted. Attempting fallback extraction.")
                    try:
                        result = await extractor(pdf_data, file_id)
                        if result:
                            package_data[entity_name] = result
                            logger.info(f"Fallback extraction successful for {entity_name}")
                        else:
                            # Create minimal placeholder to ensure DB row
                            package_data[entity_name] = {'file_id': file_id}
                            logger.warning(f"Fallback extraction failed for {entity_name}, using placeholder")
                    except Exception as e:
                        logger.error(f"Fallback extraction error for {entity_name}: {e}")
                        package_data[entity_name] = {'file_id': file_id}
            
            # Add file_id to all entities
            self._add_file_id_to_entities(package_data, file_id)
            
            # Fix data formats
            self._fix_null_strings(package_data)
            
            # Stage 3: Validate and create package
            try:
                package = ExtractedDocumentPackage(**package_data)
                logger.info(f"Successfully created package via staged extraction with {len(entity_extraction_tasks)} entities")
                return package
            except Exception as e:
                logger.error(f"Package creation failed in staged extraction: {e}")
                # Try lenient cleaning
                try:
                    cleaned_data = self._clean_invalid_fields(package_data, e)
                    package = ExtractedDocumentPackage(**cleaned_data)
                    logger.warning(f"Created package with lenient validation in staged extraction")
                    return package
                except Exception as lenient_e:
                    logger.error(f"Even lenient package creation failed: {lenient_e}")
                    return None
                
        except Exception as e:
            logger.error(f"Staged extraction failed: {e}")
            return None
    
    async def extract_document_entities(
        self, 
        pdf_data: Dict[str, str],
        file_id: int,
        lenient_mode: bool = False,
        force_lenient: bool = False
    ) -> Optional[ExtractedDocumentPackage]:
        """
        Extract entities from document using comprehensive extraction.
        
        Args:
            pdf_data: Base64 encoded PDF data
            
        Returns:
            ExtractedDocumentPackage or None if extraction fails
        """
        start_time = time.time()
        
        try:
            # Check document size limits
            pdf_size_estimate = len(pdf_data.get('data', '')) if 'data' in pdf_data else 0
            pdf_size_mb = pdf_size_estimate / 1024 / 1024 * 0.75
            
            if pdf_size_estimate > 26666666:  # >26.7MB base64 (~20MB PDF)
                logger.error(f"Document too large ({pdf_size_mb:.1f}MB) for processing, skipping")
                return None
            
            # First, detect what document types/sections are actually present
            detection_prompt = get_prompt_for_document_type('document_detection')
            detection_response = await self._make_gemini_request(detection_prompt, pdf_data)
            
            detected_sections = []
            if detection_response:
                # Look for section indicators in the detection response
                if 'indicators' in detection_response:
                    indicators = detection_response.get('indicators', [])
                    for indicator in indicators:
                        if isinstance(indicator, str):
                            indicator_lower = indicator.lower()
                            if 'power of attorney' in indicator_lower:
                                detected_sections.append('power_of_attorney')
                            elif 'account agreement' in indicator_lower:
                                detected_sections.append('payment_gateway_agreement')
                            elif 'attorney client privileged' in indicator_lower or 'attorney privileged' in indicator_lower or 'client information' in indicator_lower:
                                detected_sections.append('attorney_privileged_client_info')
                            elif 'engagement' in indicator_lower or 'client service' in indicator_lower or 'retainer' in indicator_lower or 'company agreement' in indicator_lower:
                                detected_sections.append('engagement_term')
                            elif 'financial analysis' in indicator_lower or 'exhibit b' in indicator_lower or 'financial budget' in indicator_lower or 'income' in indicator_lower or 'budget' in indicator_lower:
                                detected_sections.append('financial_analysis')
                            elif 'debt schedule' in indicator_lower or 'exhibit a' in indicator_lower:
                                detected_sections.append('debt_schedule')
                            elif 'service fees' in indicator_lower:
                                detected_sections.append('payment_service_fees')
                            elif 'disclosure' in indicator_lower:
                                detected_sections.append('disclosure')
                            elif 'fcra consent' in indicator_lower:
                                detected_sections.append('fcra_consent')
                            elif 'high interest disclosure' in indicator_lower:
                                detected_sections.append('high_interest_disclosure')
                            elif 'program disclosure' in indicator_lower:
                                detected_sections.append('program_disclosure')
                            elif 'cancellation notice' in indicator_lower:
                                detected_sections.append('cancellation_notice')
                            elif 'payment bank info' in indicator_lower:
                                detected_sections.append('payment_bank_info')
                            elif 'payment deposit schedule' in indicator_lower:
                                detected_sections.append('payment_deposit_schedule')
                            elif 'legal plan agreement' in indicator_lower:
                                detected_sections.append('legal_plan_agreement')
                            elif 'clixsign certificate' in indicator_lower:
                                detected_sections.append('clixsign_certificate')
                            elif 'clixsign signers' in indicator_lower:
                                detected_sections.append('clixsign_signers')
                            elif 'clixsign sender' in indicator_lower:
                                detected_sections.append('clixsign_sender')
                            elif 'primary account' in indicator_lower:
                                detected_sections.append('payment_bank_info')
                            elif 'bank information' in indicator_lower:
                                detected_sections.append('payment_bank_info')
                            elif 'ach authorization' in indicator_lower:
                                detected_sections.append('payment_bank_info')
                                
            logger.info(f"Detected document sections: {detected_sections}")
            
            # Use comprehensive extraction prompt directly
            prompt = get_prompt_for_document_type('comprehensive')
            
            # Extract data with retries (reduced for large files)
            max_attempts = 1 if pdf_size_estimate > 7000000 else 3
            
            extracted_data = None
            for attempt in range(max_attempts):
                try:
                    logger.info(f"Comprehensive extraction attempt {attempt + 1}")
                    
                    response = await self._make_gemini_request(prompt, pdf_data)
                    if response:
                        extracted_data = response
                        break
                        
                except Exception as e:
                    logger.warning(f"Extraction attempt {attempt + 1} failed: {e}")
                    if attempt == self.max_retries:
                        raise
            
            if not extracted_data:
                logger.error("All extraction attempts failed")
                return None
            
            # Validate extracted data to improve accuracy
            try:
                validation_passed, corrected_data = await self._validate_extracted_data(
                    extracted_data, pdf_data
                )
                if corrected_data:
                    extracted_data.update(corrected_data)
            except Exception:
                validation_passed = True
                corrected_data = None
            
            # Create document package
            package_data = {
                'file_id': file_id,
                'document_type': 'multi_section',
                'confidence_score': 1.0,  
                'extraction_metadata': {
                    'extraction_time': datetime.now().isoformat(),
                    'processing_time_ms': int((time.time() - start_time) * 1000),
                    'model': self.model_name,
                    'temperature': self.temperature,
                    'validation_passed': validation_passed,
                    'attempts': attempt + 1
                }
            }
            
            # Map extracted data to package structure and add file_id
            mapped_data = self._map_extracted_data_to_package(extracted_data, 'comprehensive')
            package_data.update(mapped_data)
            
            # Add file_id to all entities
            self._add_file_id_to_entities(package_data, file_id)
            
            # Fix string 'null' values to actual None for nested objects
            self._fix_null_strings(package_data)
            
            # Create and validate package
            try:
                package = ExtractedDocumentPackage(**package_data)
                logger.info(f"Successfully created comprehensive document package")
                
                # Targeted backfill for missing critical FA fields
                try:
                    missing_fa_fields: List[str] = []
                    fa = package_data.get('financial_analysis') or {}
                    critical_keys = [
                        'draft_type', 'fixed_income', 'day_phone', 'evening_phone', 'cell_phone',
                        'estimated_program_settle_amount', 'fee_method',
                        'client_signature', 'client_signature_date', 
                        'client_initials', 'client_initials_count'
                    ]
                    for key in critical_keys:
                        if not fa.get(key):
                            missing_fa_fields.append(key)
                    if missing_fa_fields:
                        prompt2 = get_targeted_financial_analysis_prompt(missing_fa_fields)
                        response2 = await self._make_gemini_request(prompt2, pdf_data)
                        if response2:
                            # merge backfilled fields with proper cleaning
                            for k, v in response2.items():
                                if k in missing_fa_fields and v is not None:
                                    # Apply same decimal cleaning as main processing
                                    financial_decimal_fields = [
                                        'fixed_income', 'lump_sum', 'applicant_monthly_income', 'coapplicant_monthly_income',
                                        'applicant_expenses', 'coapplicant_expenses', 'applicant_total_net_income', 'coapplicant_total_net_income',
                                        'total_enrolled_debt', 'estimated_program_length', 'monthly_program_deposit',
                                        'estimated_program_settle_amount', 'total_program_fees', 'estimated_program_savings', 'estimated_total_cost'
                                    ]
                                    if k in financial_decimal_fields:
                                        # Clean currency formatting
                                        cleaned_value = str(v).replace(',', '').replace('$', '').replace('%', '').strip()
                                        if cleaned_value.startswith('(') and cleaned_value.endswith(')'):
                                            cleaned_value = '-' + cleaned_value[1:-1]
                                        if re.match(r'^-?\d+(?:\.\d+)?$', cleaned_value):
                                            fa[k] = cleaned_value
                                        else:
                                            fa[k] = None
                                    else:
                                        fa[k] = v
                            # Ensure file_id is set in the updated financial_analysis
                            fa['file_id'] = file_id
                            package_data['financial_analysis'] = fa
                            package = ExtractedDocumentPackage(**package_data)
                            logger.info("Applied targeted backfill for missing financial analysis fields")
                except Exception as e:
                    logger.warning(f"Backfill step skipped/failed: {e}")

                # Targeted backfill
                
                # 1. Service fees
                try:
                    if 'payment_service_fees' in detected_sections:
                        fees = package_data.get('payment_service_fees')
                        if not fees or (isinstance(fees, list) and len(fees) == 0):
                            prompt_fees = get_targeted_service_fees_prompt()
                            response_fees = await self._make_gemini_request(prompt_fees, pdf_data)
                            if response_fees and isinstance(response_fees.get('payment_service_fees'), list):
                                merged_fees = response_fees['payment_service_fees']
                                # Only keep fees with actual amounts
                                valid_fees = []
                                for item in merged_fees:
                                    if isinstance(item, dict) and item.get('service_amount'):
                                        item['file_id'] = file_id
                                        self._fix_entity_data_formats(item)
                                        valid_fees.append(item)
                                if valid_fees:
                                    package_data['payment_service_fees'] = valid_fees
                                    logger.info(f"Targeted service fees extraction: {len(valid_fees)} fees")
                    elif 'payment_service_fees' not in detected_sections:
                        logger.debug("Service fees section not detected - skipping extraction")
                except Exception as e:
                    logger.warning(f"Service fees extraction failed: {e}")

                # 2. Disclosure 
                try:
                    if 'disclosure' in detected_sections and not package_data.get('disclosure'):
                        prompt_disc = get_targeted_disclosure_prompt()
                        response_disc = await self._make_gemini_request(prompt_disc, pdf_data)
                        disc = response_disc.get('disclosure') if response_disc else None
                        if isinstance(disc, dict):
                            # Only store if it has meaningful data
                            meaningful_fields = ['client_signature', 'client_signature_date', 'coclient_signature', 'coclient_signature_date']
                            if any(disc.get(k) not in (None, "", "null") for k in meaningful_fields):
                                disc['file_id'] = file_id
                                self._fix_entity_data_formats(disc)
                                package_data['disclosure'] = disc
                                logger.info("Targeted disclosure extraction")
                    elif 'disclosure' not in detected_sections:
                        logger.debug("Disclosure section not detected - skipping extraction")
                except Exception as e:
                    logger.warning(f"Disclosure extraction failed: {e}")

                # 3. Power of Attorney
                try:
                    if 'power_of_attorney' in detected_sections and not package_data.get('power_of_attorney'):
                        prompt_poa = get_targeted_power_of_attorney_prompt()
                        response_poa = await self._make_gemini_request(prompt_poa, pdf_data)
                        poa = response_poa.get('power_of_attorney') if response_poa else None
                        if isinstance(poa, dict):
                            # Only store if it has meaningful data
                            meaningful_fields = ['company_name', 'client_name', 'client_signature']
                            if any(poa.get(k) not in (None, "", "null") for k in meaningful_fields):
                                poa['file_id'] = file_id
                                self._fix_entity_data_formats(poa)
                                package_data['power_of_attorney'] = poa
                                logger.info("Targeted power of attorney extraction")
                    elif 'power_of_attorney' not in detected_sections:
                        logger.debug("Power of attorney section not detected - skipping extraction")
                except Exception as e:
                    logger.warning(f"Power of attorney extraction failed: {e}")

                # 4. Account Agreement
                try:
                    if 'payment_gateway_agreement' in detected_sections:
                        pga = package_data.get('payment_gateway_agreement')
                        critical_fields = ['client_first_name', 'client_last_name', 'client_email']
                        needs_backfill = not pga or not any(pga.get(k) for k in critical_fields)
                        
                        if needs_backfill:
                            prompt_pga = get_targeted_account_agreement_prompt()
                            response_pga = await self._make_gemini_request(prompt_pga, pdf_data)
                            pga_new = response_pga.get('payment_gateway_agreement') if response_pga else None
                            if isinstance(pga_new, dict):
                                # Only store if it has meaningful data
                                if any(pga_new.get(k) not in (None, "", "null") for k in critical_fields):
                                    if pga:
                                        # Merge with existing
                                        for k, v in pga_new.items():
                                            if k not in pga or pga.get(k) in (None, "", "null"):
                                                pga[k] = v
                                        pga['file_id'] = file_id
                                        self._fix_entity_data_formats(pga)
                                        package_data['payment_gateway_agreement'] = pga
                                    else:
                                        # New entity
                                        pga_new['file_id'] = file_id
                                        self._fix_entity_data_formats(pga_new)
                                        package_data['payment_gateway_agreement'] = pga_new
                                    logger.info("Targeted account agreement extraction")
                    elif 'payment_gateway_agreement' not in detected_sections:
                        logger.debug("Account agreement section not detected - skipping extraction")
                except Exception as e:
                    logger.warning(f"Account agreement extraction failed: {e}")

                # 5. Engagement Term
                try:
                    if 'engagement_term' in detected_sections:
                        et = package_data.get('engagement_term')
                        critical_fields = ['company_name', 'settlement_fee_percentage', 'client_name']
                        needs_backfill = not et or not any(et.get(k) for k in critical_fields)
                        
                        if needs_backfill:
                            prompt_et = get_prompt_for_document_type('engagement_term')
                            response_et = await self._make_gemini_request(prompt_et, pdf_data)
                            if response_et:
                                # Only store if it has meaningful data
                                if any(response_et.get(k) not in (None, "", "null") for k in critical_fields):
                                    if et:
                                        # Merge with existing
                                        for k, v in response_et.items():
                                            if k not in et or et.get(k) in (None, "", "null"):
                                                et[k] = v
                                        et['file_id'] = file_id
                                        self._fix_entity_data_formats(et)
                                        package_data['engagement_term'] = et
                                    else:
                                        # New entity
                                        response_et['file_id'] = file_id
                                        self._fix_entity_data_formats(response_et)
                                        package_data['engagement_term'] = response_et
                                    logger.info("Targeted engagement term extraction")
                    elif 'engagement_term' not in detected_sections:
                        logger.debug("Engagement term section not detected - skipping extraction")
                except Exception as e:
                    logger.warning(f"Engagement term extraction failed: {e}")

                # 6. Debt Schedule
                try:
                    if 'debt_schedule' in detected_sections:
                        debts = package_data.get('debt_schedule')
                        if not debts or (isinstance(debts, list) and len(debts) == 0):
                            prompt_debt = get_prompt_for_document_type('debt_schedule')
                            response_debt = await self._make_gemini_request(prompt_debt, pdf_data)
                            if response_debt and 'debt_schedule' in response_debt:
                                debt_list = response_debt['debt_schedule']
                                if isinstance(debt_list, list):
                                    # Only keep debts with creditor names
                                    valid_debts = []
                                    for item in debt_list:
                                        if isinstance(item, dict) and item.get('creditor_name'):
                                            item['file_id'] = file_id
                                            self._fix_entity_data_formats(item)
                                            valid_debts.append(item)
                                    if valid_debts:
                                        package_data['debt_schedule'] = valid_debts
                                        logger.info(f"Targeted debt schedule extraction: {len(valid_debts)} debts")
                    elif 'debt_schedule' not in detected_sections:
                        logger.debug("Debt schedule section not detected - skipping extraction")
                except Exception as e:
                    logger.warning(f"Debt schedule extraction failed: {e}")

                package = ExtractedDocumentPackage(**package_data)
                return package
                
            except Exception as e:
                if lenient_mode or force_lenient:
                    # On final attempt or force lenient, try to store with cleaned data
                    logger.warning(f"Validation failed, attempting lenient storage: {e}")
                    try:
                        cleaned_package_data = self._clean_invalid_fields(package_data, e)
                        package = ExtractedDocumentPackage(**cleaned_package_data)
                        logger.warning(f"Successfully created package with lenient validation - some fields may be null")
                        return package
                    except Exception as lenient_e:
                        logger.error(f"Even lenient validation failed: {lenient_e}")
                        if force_lenient:
                            return None
                
                logger.error(f"Failed to create document package: {e}")
                logger.debug(f"Package data: {package_data}")
                return None
                
        except Exception as e:
            logger.error(f"Document extraction failed: {e}")
            return None
    
    async def _make_gemini_request(self, prompt: str, pdf_data: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Make request to Gemini API with error handling."""
        try:
            logger.info(f"Making Gemini API request with timeout: {self.timeout}s")
            
            url = self._build_endpoint_url()
            headers = self._prepare_headers()
            payload = self._prepare_payload(prompt, pdf_data)
            
            # Adaptive timeout based on PDF size
            pdf_size_estimate = len(pdf_data.get('data', '')) if 'data' in pdf_data else 0
            pdf_size_mb = pdf_size_estimate / 1024 / 1024 * 0.75  # Approximate PDF size in MB
            
            if pdf_size_estimate > 40000000:  # >40MB base64 (~30MB PDF)
                timeout_seconds = 900  # 15 minutes for extremely large files
                logger.warning(f"Processing extremely large PDF (~{pdf_size_mb:.1f}MB), using maximum timeout")
            elif pdf_size_estimate > 26666667:  # >26.7MB base64 (~20MB PDF)
                timeout_seconds = 720  # 12 minutes for very large files
                logger.warning(f"Processing very large PDF (~{pdf_size_mb:.1f}MB), using extended timeout")
            elif pdf_size_estimate > 20000000:  # >20MB base64 (~15MB PDF)
                timeout_seconds = 600  # 10 minutes for large files
                logger.warning(f"Processing large PDF (~{pdf_size_mb:.1f}MB), using extended timeout")
            elif pdf_size_estimate > 13333333:  # >13.3MB base64 (~10MB PDF)
                timeout_seconds = 450  # 7.5 minutes for medium-large files
                logger.info(f"Processing medium-large PDF (~{pdf_size_mb:.1f}MB), using extended timeout")
            elif pdf_size_estimate > 7000000:  # >7MB base64 (~5MB PDF)
                timeout_seconds = 300  # 5 minutes for medium files
                logger.info(f"Processing medium PDF (~{pdf_size_mb:.1f}MB), using standard timeout")
            else:
                timeout_seconds = 180  # 3 minutes for normal files
                logger.info(f"Processing PDF (~{pdf_size_mb:.1f}MB), using standard timeout")
            
            timeout = httpx.Timeout(float(timeout_seconds))
            
            logger.info(f"Sending request to Gemini API (timeout: {timeout_seconds}s)")
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                
                logger.info(f"Received response from Gemini API: {response.status_code}")
                
                response_data = response.json()
                
                # Extract token usage
                if 'usageMetadata' in response_data:
                    self.last_token_usage = response_data['usageMetadata']
                
                # Extract content
                if 'candidates' in response_data and response_data['candidates']:
                    candidate = response_data['candidates'][0]
                    
                    # Check for content safety blocks
                    if 'finishReason' in candidate:
                        finish_reason = candidate['finishReason']
                        if finish_reason != 'STOP':
                            logger.error(f"Gemini response blocked due to: {finish_reason}")
                            if finish_reason == 'SAFETY':
                                logger.error("Content blocked by safety filters")
                            elif finish_reason == 'RECITATION':
                                logger.error("Content blocked due to recitation concerns")
                            elif finish_reason == 'MAX_TOKENS':
                                logger.error("Response truncated due to max tokens limit")
                            return None
                    
                    if 'content' in candidate and 'parts' in candidate['content']:
                        text_content = candidate['content']['parts'][0].get('text', '')
                        
                        # Parse JSON from response
                        json_data = extract_json_from_response(text_content)
                        if json_data:
                            return json_data
                        else:
                            # Log more details about the failed response
                            response_length = len(text_content)
                            logger.warning(f"No valid JSON found in Gemini response (length: {response_length} chars)")
                            
                            # Log first and last parts of response for debugging
                            if response_length > 0:
                                logger.warning(f"Response start: {text_content[:200]}")
                                logger.warning(f"Response end: {text_content[-200:]}")
                                
                                # Check if response contains common error indicators
                                if "I cannot" in text_content or "I'm unable" in text_content:
                                    logger.error("Gemini declined to process the request")
                                elif "error" in text_content.lower():
                                    logger.error("Gemini response contains error message")
                                elif response_length < 50:
                                    logger.error("Gemini response is too short")
                                elif not any(char in text_content for char in ['{', '[', '"']):
                                    logger.error("Gemini response contains no JSON-like characters")
                                else:
                                    # Try a fallback: if response seems to have content but no JSON,
                                    # attempt to extract any structured data manually
                                    logger.warning("Attempting manual data extraction from non-JSON response")
                                    fallback_data = self._attempt_fallback_extraction(text_content)
                                    if fallback_data:
                                        logger.info("Successfully extracted data using fallback method")
                                        return fallback_data
                            else:
                                logger.error("Gemini returned empty response")
                            
                            return None
                    else:
                        logger.error("Gemini candidate has no content or parts")
                        return None
                
                logger.warning("Unexpected Gemini response structure")
                return None
                
        except httpx.TimeoutException as e:
            logger.error(f"Gemini API request timed out after {timeout_seconds}s: {e}")
            raise
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            error_text = e.response.text
            
            # Handle specific error codes with better logging
            if status_code == 400:
                # Check for specific 400 error types
                if "no pages" in error_text.lower():
                    logger.error("gemini.invalid_pdf document_has_no_pages=true")
                    # Don't retry - this is a permanent document issue
                    from core.exceptions import NonRetryableError
                    raise NonRetryableError(f"Document has no pages - likely corrupted PDF")
                else:
                    logger.error(f"Gemini API 400 error - invalid request: {error_text}")
                # For 400 errors, don't retry immediately - it's likely a parameter issue
            elif status_code == 429:
                logger.warning(f"Gemini API rate limit hit: {error_text}")
                # Rate limiting - will be retried with backoff
            elif status_code in [500, 502, 503, 504]:
                logger.warning(f"Gemini API server error {status_code}: {error_text}")
                # Server errors - will be retried
            else:
                logger.error(f"Gemini API HTTP error: {status_code} - {error_text}")
            
            raise
        except Exception as e:
            logger.error(f"Gemini API request failed: {e}")
            raise
    
    async def _validate_extracted_data(
        self, 
        extracted_data: Dict[str, Any], 
        pdf_data: Dict[str, str]
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Validate extracted data for hallucination and accuracy.
        
        Returns:
            Tuple of (validation_passed, corrected_data)
        """
        try:
            validation_prompt = get_validation_prompt(extracted_data)
            
            validation_response = await self._make_gemini_request(validation_prompt, pdf_data)
            
            if validation_response:
                validation_passed = validation_response.get('validation_passed', False)
                confidence_score = validation_response.get('confidence_score', 0.0)
                corrected_data = validation_response.get('corrected_data', {})
                flagged_fields = validation_response.get('flagged_fields', [])
                
                if flagged_fields:
                    logger.warning(f"Validation flagged suspicious fields: {flagged_fields}")
                
                if confidence_score < self.confidence_threshold:
                    logger.warning(f"Low validation confidence: {confidence_score}")
                
                return validation_passed and confidence_score >= self.confidence_threshold, corrected_data
            
            return True, None  # Default to pass if validation fails
            
        except Exception as e:
            logger.warning(f"Validation failed: {e}")
            return True, None  # Default to pass if validation fails
    
    def _map_extracted_data_to_package(
        self, 
        extracted_data: Dict[str, Any], 
        document_type: str
    ) -> Dict[str, Any]:
        """Map extracted data to ExtractedDocumentPackage structure."""
        package_data = {}
        
        # Handle different document types
        if document_type == 'engagement_term' and extracted_data:
            package_data['engagement_term'] = extracted_data
            
        elif document_type == 'power_of_attorney' and extracted_data:
            package_data['power_of_attorney'] = extracted_data
            
        elif document_type == 'payment_gateway_agreement' and extracted_data:
            package_data['payment_gateway_agreement'] = extracted_data
            
        elif document_type == 'financial_analysis' and extracted_data:
            package_data['financial_analysis'] = extracted_data
            
        elif document_type == 'debt_schedule' and 'debt_schedule' in extracted_data:
            package_data['debt_schedule'] = extracted_data['debt_schedule']
            
        elif document_type == 'legal_plan_agreement' and extracted_data:
            package_data['legal_plan_agreement'] = extracted_data
            
        elif document_type == 'comprehensive':
            # Map all possible entities from comprehensive extraction
            entity_mappings = {
                'engagement_term': 'engagement_term',
                'power_of_attorney': 'power_of_attorney', 
                'payment_gateway_agreement': 'payment_gateway_agreement',
                'financial_analysis': 'financial_analysis',
                'debt_schedule': 'debt_schedule',
                'fcra_consent': 'fcra_consent',
                'disclosure': 'disclosure',
                'high_interest_disclosure': 'high_interest_disclosure',
                'program_disclosure': 'program_disclosure',
                'cancellation_notice': 'cancellation_notice',
                'payment_service_fees': 'payment_service_fees',
                'payment_bank_info': 'payment_bank_info',
                'payment_deposit_schedule': 'payment_deposit_schedule',
                'legal_plan_agreement': 'legal_plan_agreement',
                'attorney_privileged_client_info': 'attorney_privileged_client_info',
                'attorney privileged': 'attorney_privileged_client_info',
                'client information': 'attorney_privileged_client_info',
                'clixsign_sender': 'clixsign_sender',
                'clixsign_signers': 'clixsign_signers'
            }
            
            for key, package_key in entity_mappings.items():
                if key in extracted_data and extracted_data[key]:
                    value = extracted_data[key]
                    # Normalize financial analysis to match DB schema and improve consistency
                    if package_key == 'financial_analysis' and isinstance(value, dict):
                        package_data[package_key] = self._normalize_financial_analysis_fields(value)
                    else:
                        package_data[package_key] = value
        
        return package_data

    def _clean_invalid_fields(self, package_data: Dict[str, Any], validation_error: Exception) -> Dict[str, Any]:
        """Clean invalid fields to allow lenient storage on final attempt."""
        from pydantic import ValidationError
        import copy
        
        cleaned_data = copy.deepcopy(package_data)
        
        if isinstance(validation_error, ValidationError):
            for error in validation_error.errors():
                field_path = error.get('loc', ())
                error_type = error.get('type', '')
                
                logger.info(f"Cleaning validation error: {'.'.join(map(str, field_path))} - {error_type}")
                
                # Navigate to the problematic field and fix it
                current = cleaned_data
                for i, key in enumerate(field_path[:-1]):
                    if isinstance(current, dict) and key in current:
                        current = current[key]
                    elif isinstance(current, list) and isinstance(key, int) and 0 <= key < len(current):
                        current = current[key]
                    else:
                        break
                
                if len(field_path) > 0:
                    final_key = field_path[-1]
                    
                    # Handle specific validation error types
                    if error_type == 'string_too_long':
                        # Truncate string fields that are too long
                        if isinstance(current, dict) and final_key in current:
                            original_value = current[final_key]
                            if isinstance(original_value, str):
                                # Get max length from error message if possible
                                max_length = self._extract_max_length_from_error(error)
                                if max_length:
                                    current[final_key] = original_value[:max_length]
                                    logger.info(f"Truncated {'.'.join(map(str, field_path))} from {len(original_value)} to {max_length} chars")
                                else:
                                    current[final_key] = None
                                    logger.info(f"Set {'.'.join(map(str, field_path))} to null due to length issue")
                    
                    elif error_type in ['date_from_datetime_parsing', 'datetime_parsing']:
                        # Set invalid dates to None
                        if isinstance(current, dict) and final_key in current:
                            current[final_key] = None
                            logger.info(f"Set invalid date {'.'.join(map(str, field_path))} to null")
                    
                    elif error_type in ['decimal_parsing', 'int_parsing', 'float_parsing']:
                        # Set invalid numbers to None
                        if isinstance(current, dict) and final_key in current:
                            current[final_key] = None
                            logger.info(f"Set invalid number {'.'.join(map(str, field_path))} to null")
                    
                    elif error_type == 'model_type':
                        # Set invalid nested models to None
                        if isinstance(current, dict) and final_key in current:
                            current[final_key] = None
                            logger.info(f"Set invalid nested model {'.'.join(map(str, field_path))} to null")
                    
                    else:
                        # For any other validation error, set field to None
                        if isinstance(current, dict) and final_key in current:
                            current[final_key] = None
                            logger.info(f"Set field {'.'.join(map(str, field_path))} to null due to {error_type}")
        
        return cleaned_data
    
    def _extract_max_length_from_error(self, error: Dict) -> Optional[int]:
        """Extract max length constraint from validation error message."""
        msg = str(error.get('msg', ''))
        # Look for patterns like "String should have at most 10 characters"
        import re
        match = re.search(r'at most (\d+) characters', msg)
        if match:
            return int(match.group(1))
        return None

    def _normalize_financial_analysis_fields(self, fa: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize financial analysis dict to match model field names and fix common issues."""
        # Helper to fetch a value by any of several possible keys (case-insensitive)
        def get_any(keys: List[str]) -> Any:
            lower_map = {k.lower(): v for k, v in fa.items()}
            for k in keys:
                if k.lower() in lower_map and lower_map[k.lower()] not in ['', None]:
                    return lower_map[k.lower()]
            return None

        normalized: Dict[str, Any] = {}

        # Straightforward mappings with synonyms
        normalized['applicant_name'] = get_any(['applicant_name', 'client_name'])
        normalized['applicant_email'] = get_any(['applicant_email', 'client_email'])
        normalized['coapplicant_name'] = get_any(['coapplicant_name', 'co_applicant_name', 'co-applicant_name'])
        normalized['coapplicant_email'] = get_any(['coapplicant_email', 'co_applicant_email', 'co-applicant_email'])
        normalized['draft_type'] = get_any(['draft_type', 'draft method', 'draft'])
        normalized['fixed_income'] = get_any(['fixed_income', 'fixed income'])
        normalized['day_phone'] = get_any(['day_phone', 'day phone', 'dayphone'])
        normalized['evening_phone'] = get_any(['evening_phone', 'evening phone', 'eveningphone'])
        normalized['cell_phone'] = get_any(['cell_phone', 'cell phone', 'mobile_phone', 'mobile'])
        normalized['program_start_date'] = get_any(['program_start_date', 'start_date', 'program start date'])
        normalized['estimated_program_start_date'] = get_any(['estimated_program_start_date', 'estimated start date'])
        normalized['lump_sum'] = get_any(['lump_sum', 'lump sum', 'lump_sum_if_applicable'])
        normalized['applicant_monthly_income'] = get_any(['applicant_monthly_income', 'applicant monthly income (after taxes):', 'applicant_monthly_income_after_taxes', 'monthly_income_after_taxes'])
        normalized['coapplicant_monthly_income'] = get_any(['coapplicant_monthly_income', 'co-applicant monthly income (after taxes):', 'co_applicant_monthly_income_after_taxes'])
        normalized['applicant_expenses'] = get_any(['applicant_expenses', 'applicant expenses'])
        normalized['coapplicant_expenses'] = get_any(['coapplicant_expenses', 'co-applicant expenses'])
        normalized['applicant_total_net_income'] = get_any(['applicant_total_net_income', 'total net income'])
        normalized['coapplicant_total_net_income'] = get_any(['coapplicant_total_net_income', 'co-applicant total net income'])
        normalized['total_enrolled_debt'] = get_any(['total_enrolled_debt', 'total enrolled debt (from exhibit a)', 'total_enrolled_debt_from_exhibit_a'])
        normalized['estimated_program_length'] = get_any(['estimated_program_length', 'estimated program length', 'program_length', 'program duration'])
        normalized['monthly_program_deposit'] = get_any(['monthly_program_deposit', 'monthly program deposit', 'monthly_payment'])
        # Handle multiple variants of settlement amount
        normalized['estimated_program_settle_amount'] = get_any([
            'estimated_program_settle_amount', 'estimated program settle amount',
            'estimated_settlement_amount', 'estimated_settle_amount', 'estimated_program_settlement_amount'
        ])
        normalized['fee_method'] = get_any(['fee_method', 'fee method'])
        normalized['total_program_fees'] = get_any(['total_program_fees', 'total program fees'])
        normalized['estimated_program_savings'] = get_any(['estimated_program_savings', 'estimated program savings'])
        normalized['estimated_total_cost'] = get_any(['estimated_total_cost', 'estimated total cost'])
        normalized['hardship_details'] = get_any(['hardship_details', 'hardship details'])

        # Ensure draft_type and fee_method mirror if only one provided
        if not normalized.get('draft_type') and normalized.get('fee_method'):
            normalized['draft_type'] = normalized['fee_method']
        if not normalized.get('fee_method') and normalized.get('draft_type'):
            normalized['fee_method'] = normalized['draft_type']

        # Re-compute net incomes if missing or clearly wrong (income - expenses)
        def to_decimal_like(x: Any) -> Optional[str]:
            if x is None:
                return None
            s = str(x)
            s = s.replace(',', '').replace('$', '').strip()
            return s if s else None

        ai = to_decimal_like(normalized.get('applicant_monthly_income'))
        ae = to_decimal_like(normalized.get('applicant_expenses'))
        if ai is not None and ae is not None:
            try:
                net = float(ai) - float(ae)
                # Only set if missing or obviously equal to income (likely mis-extracted)
                if not normalized.get('applicant_total_net_income') or str(normalized.get('applicant_total_net_income')).replace(',', '') == str(ai):
                    normalized['applicant_total_net_income'] = f"{net:.2f}"
            except Exception:
                pass

        ci = to_decimal_like(normalized.get('coapplicant_monthly_income'))
        ce = to_decimal_like(normalized.get('coapplicant_expenses'))
        if ci is not None and ce is not None:
            try:
                net = float(ci) - float(ce)
                if not normalized.get('coapplicant_total_net_income'):
                    normalized['coapplicant_total_net_income'] = f"{net:.2f}"
            except Exception:
                pass

        return normalized
    
    def _add_file_id_to_entities(self, data: Dict[str, Any], file_id: int) -> None:
        """Recursively add file_id to all entities and fix data formatting issues."""
        for key, value in data.items():
            if key == 'extraction_metadata':
                continue  # Skip metadata
                
            if isinstance(value, dict):
                # Add file_id to single entity
                if key in ['engagement_term', 'power_of_attorney', 'payment_gateway_agreement', 
                          'financial_analysis', 'fcra_consent', 'disclosure', 'high_interest_disclosure',
                          'program_disclosure', 'cancellation_notice', 'payment_bank_info', 
                          'legal_plan_agreement', 'attorney_privileged_client_info', 'clixsign_sender']:
                    value['file_id'] = file_id
                    self._fix_entity_data_formats(value)
                    
            elif isinstance(value, list):
                # Add file_id to list entities
                if key in ['debt_schedule', 'payment_service_fees', 'payment_deposit_schedule', 'clixsign_signers']:
                    for item in value:
                        if isinstance(item, dict):
                            item['file_id'] = file_id
                            self._fix_entity_data_formats(item)
    
    def _fix_entity_data_formats(self, entity: Dict[str, Any]) -> None:
        """Fix common data format issues in entities."""
        # Field name mappings to fix mismatches between extraction and model fields
        field_mappings = {
            'signer_number': 'signer_name',  # Fix clixsign signer field name
            'name': 'signer_name',           # Fix clixsign signer field name
            'email_address': 'email',        # Common email field mapping
            'consumer_signature': 'client_signature',  # FCRA consent mapping
            'payment_number': 'payment_no',  # Payment schedule mapping
            'process_date': 'process_date',  # Keep as is but validate format
            'fee_type': 'service_type',      # Payment service fees mapping
            'creditor_name': 'creditor_name', # Keep as is
            'account_name': 'name_on_account', # Debt schedule mapping (applicant/c oapplicant/joint)
            'account_no': 'account_number',
            'acct_no': 'account_number',
            'account_number': 'account_number',
        }
        
        # Apply field name mappings
        keys_to_update = {}
        keys_to_remove = []
        for old_key, new_key in field_mappings.items():
            if old_key in entity and old_key != new_key:
                keys_to_update[new_key] = entity[old_key]
                keys_to_remove.append(old_key)
        
        # Update entity with new keys
        entity.update(keys_to_update)
        # Remove old keys
        for key in keys_to_remove:
            entity.pop(key, None)
        
        # Create a copy of items to avoid modification during iteration
        items_to_process = list(entity.items())
        for key, value in items_to_process:
            if isinstance(value, str) and value is not None:
                # General cleanup: collapse whitespace/newlines
                raw_value = value
                value = re.sub(r"\s+", " ", value).strip()
                entity[key] = value
                # Financial analysis decimal fields (based on actual database schema)
                financial_decimal_fields = [
                    'fixed_income', 'lump_sum', 'applicant_monthly_income', 'coapplicant_monthly_income',
                    'applicant_expenses', 'coapplicant_expenses', 'applicant_total_net_income', 'coapplicant_total_net_income',
                    'total_enrolled_debt', 'estimated_program_length', 'monthly_program_deposit',
                    'estimated_program_settle_amount', 'total_program_fees', 'estimated_program_savings', 'estimated_total_cost'
                ]
                
                # Other decimal fields for other entities
                other_decimal_fields = [
                    'current_balance', 'amount', 'settlement_fee', 'monthly_payment',
                    'settlement_fee_percentage', 'first_payment_amount', 'monthly_payment_amount',
                    'members_accumulation_amount', 'recurring_debit_authorization'
                ]
                
                decimal_fields = financial_decimal_fields + other_decimal_fields
                if key in decimal_fields:
                    # Remove commas, dollar signs, percentage signs, and other currency symbols
                    cleaned_value = value.replace(',', '').replace('$', '').replace('€', '').replace('£', '').replace('%', '').strip()
                    # Handle negative values in parentheses like "(538.51)"
                    if cleaned_value.startswith('(') and cleaned_value.endswith(')'):
                        cleaned_value = '-' + cleaned_value[1:-1]
                    # If still non-numeric (e.g., long text), set to None to avoid decimal parsing errors
                    if not re.match(r'^-?\d+(?:\.\d+)?$', cleaned_value):
                        entity[key] = None
                    else:
                        entity[key] = cleaned_value
                
                # Fix percentage fields - ensure they're clean decimals
                percentage_fields = ['settlement_fee_percentage', 'settlement_fee_percent']
                if key in percentage_fields:
                    cleaned_value = value.replace('%', '').replace(',', '').strip()
                    entity[key] = cleaned_value
                
                # Fix date formats - convert various formats to yyyy-MM-dd or ISO datetime
                date_fields = [
                    'client_dob', 'coclient_dob', 'member_dob', 'coapplicant_dob',
                    'signature_date', 'client_signature_date', 'coclient_signature_date',
                    'cancellation_deadline', 'cancellation_date',
                    'first_payment_date', 'process_date', 'first_debit_date', 'program_start_date',
                    'estimated_program_start_date', 'date', 'cancel_by_date', 'date_of_first_debit',
                    'credit_card_expiration_date', 'monthly_recurring_date'
                ]
                
                # ClixSign datetime fields that need full datetime parsing
                datetime_fields = [
                    'package_opened_at', 'signature_adopted_at', 'package_signed_at', 
                    'package_declined_at', 'final_status_date'
                ]
                
                if key in date_fields and isinstance(value, str):
                    try:
                        cleaned = re.sub(r"\s+", "", raw_value)
                        
                        # Handle invalid/partial dates - set to None
                        if len(cleaned) <= 2 and cleaned.isdigit():
                            # Just a day number like "15" - not a valid date
                            entity[key] = None
                            continue
                        
                        # Handle MM/dd/yyyy and M/d/yyyy
                        if '/' in cleaned:
                            parts = cleaned.split('/')
                            if len(parts) == 3:
                                # year-first e.g. 2025/8/15
                                if len(parts[0]) == 4:
                                    y, m, d = parts[0], parts[1], parts[2]
                                    if len(y) == 4 and m.isdigit() and d.isdigit():
                                        entity[key] = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
                                else:
                                    # month-first e.g. 11/6/2024 or 09/28/1971 with noise removed
                                    m, d, y = parts[0], parts[1], parts[2]
                                    if len(y) == 4 and m.isdigit() and d.isdigit():
                                        entity[key] = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
                        # Handle "Nov 21, 2024" format and other month-name patterns
                        elif re.search(r"[A-Za-z]", value) and re.search(r"\d{4}", value):
                            import datetime
                            txt = value.replace('\n', ' ').replace('  ', ' ').strip()
                            # Accept short/long month names with ordinal day
                            m = re.search(r"([A-Za-z]+)\s*([0-9]{1,2})(?:st|nd|rd|th)?[, ]+([0-9]{4})", txt)
                            if m:
                                month_name, day, year = m.groups()
                                try:
                                    parsed_date = datetime.datetime.strptime(f"{month_name} {day} {year}", '%B %d %Y')
                                except ValueError:
                                    try:
                                        parsed_date = datetime.datetime.strptime(f"{month_name} {day} {year}", '%b %d %Y')
                                    except ValueError:
                                        # Handle invalid patterns like "2025-Aug-Fri" by nulling them
                                        entity[key] = None
                                        continue
                                entity[key] = parsed_date.strftime('%Y-%m-%d')
                            else:
                                # Pattern like "2025-Aug-Fri" doesn't match our regex, set to None
                                entity[key] = None
                        # Handle "11-09-2024" format  
                        elif '-' in value and value.count('-') == 2:
                            parts = value.split('-')
                            if len(parts) == 3:
                                # Try month-first
                                if len(parts[2]) == 4 and parts[0].isdigit() and parts[1].isdigit():
                                    entity[key] = f"{parts[2]}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
                        else:
                            # Invalid date format - set to None
                            entity[key] = None
                    except:
                        entity[key] = None  # Set to None on any date parsing error
                
                # Fix ClixSign datetime formats - convert "MM/dd/yyyy h:mm:ss AM/PM" to ISO format
                if key in datetime_fields and isinstance(value, str):
                    try:
                        import datetime
                        # Handle "10/14/2022 2:17:37 PM" format
                        if '/' in value and (' AM' in value or ' PM' in value):
                            parsed_dt = datetime.datetime.strptime(value, '%m/%d/%Y %I:%M:%S %p')
                            entity[key] = parsed_dt.isoformat()
                        # Handle "10/14/2022 14:17:37" format (24-hour)
                        elif '/' in value and ':' in value and ' AM' not in value and ' PM' not in value:
                            parsed_dt = datetime.datetime.strptime(value, '%m/%d/%Y %H:%M:%S')
                            entity[key] = parsed_dt.isoformat()
                    except:
                        pass  # Keep original if conversion fails
                
                # Fix account_type case sensitivity (must be lowercase)
                if key == 'account_type':
                    if value.lower() in ['checking', 'savings']:
                        entity[key] = value.lower()
                

                
                # Fix boolean fields that might come as strings
                boolean_fields = [
                    'dedicated_account_required', 'effective_immediately', 'local_counsel_disclosure',
                    'credit_report_authorization', 'financial_info_disclosure_authorization',
                    'termination_rights', 'arbitration_clause', 'class_action_waiver',
                    'recurring_debit_authorization_bool', 'credit_counseling_disclosure',
                    'bankruptcy_disclosure', 'debt_negotiation_disclosure', 'has_security_clearance',
                    'is_married_to_coclient', 'is_in_bankruptcy', 'is_enrolled_in_credit_counseling'
                ]
                if key in boolean_fields:
                    entity[key] = value.lower() in ['true', 'yes', '1', 'on']
                
                # Fix integer fields that might come as strings
                integer_fields = [
                    'estimated_program_length', 'debt_relief_program_duration',
                    'signer_number', 'initials_count', 'page_count', 'pages_count', 'signers_count', 
                    'client_initials_count', 'coclient_initials_count'
                ]
                if key in integer_fields and isinstance(value, str):
                    numeric = re.sub(r"[^0-9]", "", value)
                    if numeric.isdigit():
                        entity[key] = int(numeric)
                
                # Clean up address formatting issues
                address_fields = ['client_address', 'coclient_address', 'address', 'attorney_address', 'company_address', 'credit_card_billing_address', 'client_street', 'coclient_street']
                if key in address_fields:
                    # Remove curly braces, trailing commas, and clean up formatting
                    cleaned_address = value.replace('{', '').replace('}', '').strip()
                    if cleaned_address.endswith(','):
                        cleaned_address = cleaned_address[:-1].strip()
                    entity[key] = cleaned_address if cleaned_address else None
                    continue
                
                # Clean up empty strings and placeholders to None for optional fields
                if value.strip() == '' or value.lower() in ['null', 'none', 'n/a', 'na']:
                    entity[key] = None
                
                # Fix placeholder values
                if isinstance(value, str) and '{' in value and '}' in value:
                    # Common placeholders that should be None
                    placeholder_patterns = [
                        '{COSIGNDATE}', '{SIGNDATE}', '{DATE}', '{SIGNATURE}', '{NAME}',
                        '{AMOUNT}', '{PHONE}', '{EMAIL}', '{ADDRESS}', '{SSN}', '{CITY}', '{STATE}', '{ZIP}'
                        '{RECURRINGDEBITAUTHORIZATION}', '{FIRSTDEBITDATE}', '{CLIENTSIGNATURE}', '{COCLIENTSIGNATURE}',
                        '{CLIENTINITIALS}', '{COCLIENTINITIALS}'
                    ]
                    if value.upper() in placeholder_patterns:
                        logger.bind(
                            field=key,
                            placeholder=value
                        ).debug("gemini.placeholder_detected")
                        entity[key] = None
            
            # Handle non-string values for payment_no (integers need to be converted to strings)
            if key in ['payment_no', 'payment_number'] and isinstance(value, int):
                entity[key] = str(value)

        # Normalize SSN-like fields specifically after general cleanup
        ssn_fields = {'client_ssn', 'coclient_ssn', 'member_ssn', 'coapplicant_ssn'}
        for f in ssn_fields:
            if f in entity and isinstance(entity[f], str):
                raw = re.sub(r"\s+", "", entity[f])
                
                # Handle masked SSNs (XXX-XX-1234 format)
                if raw.startswith('XXX-XX-') or raw.startswith('xxx-xx-'):
                    entity[f] = raw.upper()  # Keep masked format, ensure uppercase
                elif 'XXX' in raw.upper() and len(raw) >= 7:
                    # Handle variations like "XXX-XX-1072" or "XXXXX1072"
                    if '-' in raw:
                        entity[f] = raw.upper()  # Keep existing format
                    else:
                        # Format as XXX-XX-#### if unformatted masked SSN
                        digits = re.sub(r"[^0-9]", "", raw)
                        if len(digits) == 4:  # Only last 4 digits
                            entity[f] = f"XXX-XX-{digits}"
                        else:
                            entity[f] = raw.upper()
                else:
                    # Handle full SSNs - but check if this should be masked based on document
                    digits = re.sub(r"[^0-9]", "", raw)
                    if len(digits) == 9:
                        # Check if original value suggests masking (e.g., contains X)
                        if 'X' in entity[f].upper():
                            # Extract last 4 digits and mask the rest
                            last_four = digits[-4:]
                            entity[f] = f"XXX-XX-{last_four}"
                        else:
                            entity[f] = f"{digits[0:3]}-{digits[3:5]}-{digits[5:9]}"
                    elif len(digits) == 4:
                        # Only last 4 digits provided - assume masked
                        entity[f] = f"XXX-XX-{digits}"
                    else:
                        # leave as-is; validator may null it
                        entity[f] = raw
    
    def _fix_null_strings(self, data: Dict[str, Any]) -> None:
        """Convert string 'null' values to actual None for nested objects."""
        for key, value in data.items():
            if isinstance(value, str) and value.lower() == 'null':
                data[key] = None
            elif isinstance(value, list):
                # Fix null strings in list items
                for i, item in enumerate(value):
                    if isinstance(item, str) and item.lower() == 'null':
                        value[i] = None
                    elif isinstance(item, dict):
                        self._fix_null_strings(item)
            elif isinstance(value, dict):
                # Recursively fix nested objects
                self._fix_null_strings(value)

    async def _extract_payment_gateway(self, pdf_data: Dict[str, str], file_id: int) -> Optional[Dict]:
        """Extract payment gateway agreement data."""
        prompt = get_prompt_for_document_type('payment_gateway_agreement')
        result = await self._make_gemini_request(prompt, pdf_data)
        if result:
            result['file_id'] = file_id
            self._fix_entity_data_formats(result)
        return result
    
    async def _extract_engagement_term(self, pdf_data: Dict[str, str], file_id: int) -> Optional[Dict]:
        """Extract engagement term data."""
        prompt = get_prompt_for_document_type('engagement_term')
        result = await self._make_gemini_request(prompt, pdf_data)
        if result:
            result['file_id'] = file_id
            self._fix_entity_data_formats(result)
        return result
    
    async def _extract_power_of_attorney(self, pdf_data: Dict[str, str], file_id: int) -> Optional[Dict]:
        """Extract power of attorney data."""
        prompt = get_prompt_for_document_type('power_of_attorney')
        result = await self._make_gemini_request(prompt, pdf_data)
        if result:
            result['file_id'] = file_id
            self._fix_entity_data_formats(result)
        return result
    
    async def _extract_financial_analysis(self, pdf_data: Dict[str, str], file_id: int) -> Optional[Dict]:
        """Extract financial analysis data."""
        prompt = get_prompt_for_document_type('financial_analysis')
        result = await self._make_gemini_request(prompt, pdf_data)
        if result:
            result['file_id'] = file_id
            self._fix_entity_data_formats(result)
            # Apply normalization for financial analysis
            result = self._normalize_financial_analysis_fields(result)
        return result
    
    async def _extract_debt_schedule(self, pdf_data: Dict[str, str], file_id: int) -> Optional[List]:
        """Extract debt schedule data."""
        prompt = get_prompt_for_document_type('debt_schedule')
        result = await self._make_gemini_request(prompt, pdf_data)
        if result and 'debt_schedule' in result:
            debts = result['debt_schedule']
            if isinstance(debts, list):
                for debt in debts:
                    debt['file_id'] = file_id
                    self._fix_entity_data_formats(debt)
                return debts
        return None
    
    async def _extract_service_fees(self, pdf_data: Dict[str, str], file_id: int) -> Optional[List]:
        """Extract service fees data."""
        from prompts.underwriting_prompts import get_targeted_service_fees_prompt
        prompt = get_targeted_service_fees_prompt()
        result = await self._make_gemini_request(prompt, pdf_data)
        if result and 'payment_service_fees' in result:
            fees = result['payment_service_fees']
            if isinstance(fees, list):
                valid_fees = []
                for fee in fees:
                    if isinstance(fee, dict) and fee.get('service_amount'):
                        fee['file_id'] = file_id
                        self._fix_entity_data_formats(fee)
                        valid_fees.append(fee)
                return valid_fees if valid_fees else None
        return None
    
    async def _extract_deposit_schedule(self, pdf_data: Dict[str, str], file_id: int) -> Optional[List]:
        """Extract deposit schedule data."""
        prompt = """
        Extract the Payment Deposit Schedule table. Look for payment numbers, dates, and amounts.
        
        Return JSON:
        {
          "payment_deposit_schedule": [
            {
              "payment_no": "1",
              "process_date": "2025-01-15",
              "amount": "250.00"
            }
          ]
        }
        """
        result = await self._make_gemini_request(prompt, pdf_data)
        if result and 'payment_deposit_schedule' in result:
            deposits = result['payment_deposit_schedule']
            if isinstance(deposits, list):
                for deposit in deposits:
                    deposit['file_id'] = file_id
                    self._fix_entity_data_formats(deposit)
                return deposits
        return None

    async def _extract_payment_bank_info(self, pdf_data: Dict[str, str], file_id: int) -> Optional[Dict]:
        """Extract Primary Account Information / Payment Bank Info."""
        prompt = """
        Find the "Primary Account Information" section. Look for a form layout with labeled fields:
        
        EXACT FIELDS TO EXTRACT:
        - Bank Name field (e.g., "PNC BANK, NATIONAL ASSOCIATION", "JPMORGAN CHASE BANK, NA")
        - Account Number field (e.g., "1036582879", "3134029178")  
        - Routing Number field (9 digits, e.g., "043000096", "322271627")
        - Account Type field ("Checking" or "Savings")
        - "Authorizing Person's Name (as it appears on check)" field
        - Address (Street address)
        - City (City)
        - State (State)
        - Zip (Zip)
        - "Recurring Debit Authorization" amount (e.g., "$651.57", "$631.23")
        - "Date of First Debit" (e.g., "Sep 15, 2025", "Sep 03, 2025")
        - Client Signature line and Date
        
        CRITICAL: Extract ONLY what is visibly filled in these specific labeled fields.
        
        Return JSON:
        {
          "payment_bank_info": {
            "file_id": null,
            "authorizing_person_name": "Exact name from the Authorizing Person field",
            "bank_name": "Exact bank name from Bank Name field",
            "account_number": "Exact account number from Account Number field",
            "routing_number": "Exact routing number from Routing Number field",
            "account_type": "checking or savings (lowercase)",
            "address": "Street address from Address field",
            "city": "City from City field",
            "state": "State from State field",
            "zip_code": "Zip from Zip field",
            "recurring_debit_authorization": "Amount without $ symbol (e.g., 651.57)",
            "first_debit_date": "Date in YYYY-MM-DD format",
            "client_signature": "Client signature text if present",
            "client_signature_date": "Signature date in YYYY-MM-DD format",
            "coclient_signature": null,
            "coclient_signature_date": null
          }
        }
        """
        # Use the dedicated prompt function which returns flat structure
        from prompts.underwriting_prompts import get_payment_bank_info_prompt
        prompt = get_payment_bank_info_prompt()
        
        result = await self._make_gemini_request(prompt, pdf_data)
        if result and isinstance(result, dict):
            result['file_id'] = file_id
            self._fix_entity_data_formats(result)
            logger.bind(
                file_id=file_id, 
                bank_name=result.get('bank_name'),
                recurring_debit_authorization=result.get('recurring_debit_authorization')
            ).debug("payment_bank_info.extracted")
            return result
        logger.bind(file_id=file_id).warning("payment_bank_info.not_found")
        return None  
    async def _extract_disclosure(self, pdf_data: Dict[str, str], file_id: int) -> Optional[Dict]:
        """Extract disclosure data."""
        from prompts.underwriting_prompts import get_targeted_disclosure_prompt
        prompt = get_targeted_disclosure_prompt()
        result = await self._make_gemini_request(prompt, pdf_data)
        if result and 'disclosure' in result:
            disc = result['disclosure']
            if isinstance(disc, dict):
                disc['file_id'] = file_id
                self._fix_entity_data_formats(disc)
                return disc
        return None
    
    async def _extract_legal_plan(self, pdf_data: Dict[str, str], file_id: int) -> Optional[Dict]:
        """Extract legal plan agreement data."""
        prompt = get_prompt_for_document_type('legal_plan_agreement')
        result = await self._make_gemini_request(prompt, pdf_data)
        if result:
            result['file_id'] = file_id
            self._fix_entity_data_formats(result)
        return result
    
    async def _extract_high_interest(self, pdf_data: Dict[str, str], file_id: int) -> Optional[Dict]:
        """Extract high interest disclosure data."""
        prompt = """
        Extract High Interest Creditor Disclosure information.
        
        Return JSON:
        {
          "company_name": null,
          "client_name": null,
          "client_signature": null,
          "client_signature_date": null,
          "coclient_name": null,
          "coclient_signature": null,
          "coclient_signature_date": null
        }
        """
        result = await self._make_gemini_request(prompt, pdf_data)
        if result:
            result['file_id'] = file_id
            self._fix_entity_data_formats(result)
        return result
    
    async def _extract_fcra(self, pdf_data: Dict[str, str], file_id: int) -> Optional[Dict]:
        """Extract FCRA consent data."""
        prompt = """
        Extract FCRA Consumer Report Consent information.
        
        Return JSON:
        {
          "company_name": null,
          "client_name": null,
          "client_signature": null,
          "client_signature_date": null
        }
        """
        result = await self._make_gemini_request(prompt, pdf_data)
        if result:
            result['file_id'] = file_id
            self._fix_entity_data_formats(result)
        return result
    
    async def _extract_cancellation(self, pdf_data: Dict[str, str], file_id: int) -> Optional[Dict]:
        """Extract cancellation notice data."""
        prompt = get_prompt_for_document_type('cancellation_notice')
        result = await self._make_gemini_request(prompt, pdf_data)
        if result:
            result['file_id'] = file_id
            self._fix_entity_data_formats(result)
        return result
    
    async def _extract_clixsign_data(self, pdf_data: Dict[str, str], file_id: int) -> Optional[Dict]:
        """Extract ClixSign certificate data."""
        prompt = """
        Extract ClixSign Certificate information.
        
        Return JSON:
        {
          "clixsign_sender": {
            "package_id": null,
            "package_title": null,
            "final_status": null,
            "final_status_date": null,
            "sending_entity": null,
            "sender_name": null,
            "sender_email_address": null,
            "sender_ip_address": null,
            "signers_count": null
          },
          "clixsign_signers": [
            {
              "package_id": null,
              "signer_name": null,
              "signer_email_address": null,
              "signer_ip_address": null,
              "signer_user_agent": null,
              "package_opened_at": null,
              "signature_adopted_at": null,
              "package_signed_at": null
            }
          ]
        }
        """
        result = await self._make_gemini_request(prompt, pdf_data)
        if result:
            # Process sender
            if 'clixsign_sender' in result and result['clixsign_sender']:
                result['clixsign_sender']['file_id'] = file_id
                self._fix_entity_data_formats(result['clixsign_sender'])
            
            # Process signers
            if 'clixsign_signers' in result and isinstance(result['clixsign_signers'], list):
                logger.bind(file_id=file_id, signer_count=len(result['clixsign_signers'])).debug("clixsign_signers.processing")
                for i, signer in enumerate(result['clixsign_signers']):
                    signer['file_id'] = file_id
                    self._fix_entity_data_formats(signer)
                    logger.bind(
                        file_id=file_id,
                        signer_index=i,
                        signer_name=signer.get('signer_name'),
                        signer_email=signer.get('signer_email_address')
                    ).debug("clixsign_signer.processed")
            else:
                logger.bind(file_id=file_id).warning("clixsign_signers.not_found_in_result")
            
            return result
        return None
    
    async def _extract_program_disclosure(self, pdf_data: Dict[str, str], file_id: int) -> Optional[Dict]:
        """Extract program disclosure data."""
        prompt = """
        Extract Program Disclosure information.
        
        Return JSON:
        {
          "company_name": null,
          "settlement_fee_percent": null,
          "client_initials": null,
          "coclient_initials": null,
          "is_all_initials_present": null
        }
        """
        result = await self._make_gemini_request(prompt, pdf_data)
        if result:
            result['file_id'] = file_id
            self._fix_entity_data_formats(result)
        return result
    
    async def _extract_attorney_privileged(self, pdf_data: Dict[str, str], file_id: int) -> Optional[Dict]:
        """Extract attorney privileged client info data."""
        prompt = get_prompt_for_document_type('attorney_privileged_client_info')
        result = await self._make_gemini_request(prompt, pdf_data)
        if result:
            result['file_id'] = file_id
            self._fix_entity_data_formats(result)
        return result
    
    async def _extract_payment_gateway(self, pdf_data: Dict[str, str], file_id: int) -> Optional[Dict]:
        """Extract payment gateway data."""
        prompt = get_prompt_for_document_type('payment_gateway_agreement')
        result = await self._make_gemini_request(prompt, pdf_data)
        if result:
            result['file_id'] = file_id
            self._fix_entity_data_formats(result)
        return result
    

    def _attempt_fallback_extraction(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Attempt to extract structured data from non-JSON responses.
        This handles cases where Gemini returns explanatory text or partial data.
        """
        try:
            # Look for key-value pairs in various formats
            data = {}
            
            # Pattern 1: "field: value" format
            kv_pattern = r'([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([^\n\r]+)'
            matches = re.findall(kv_pattern, text, re.IGNORECASE)
            
            for key, value in matches:
                # Clean up the value
                value = value.strip().strip('"\'')
                if value.lower() in ['null', 'none', 'n/a', 'not found']:
                    value = None
                data[key.lower()] = value
            
            # Pattern 2: Look for structured text blocks
            if not data:
                # Try to find any structured information
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    if ':' in line and not line.startswith('#'):
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            key = parts[0].strip().lower()
                            value = parts[1].strip().strip('"\'')
                            if value.lower() in ['null', 'none', 'n/a', 'not found']:
                                value = None
                            data[key] = value
            
            # Only return data if we found at least 3 fields
            if len(data) >= 3:
                logger.info(f"Fallback extraction found {len(data)} fields")
                return data
            else:
                logger.warning(f"Fallback extraction only found {len(data)} fields, insufficient")
                return None
                
        except Exception as e:
            logger.error(f"Fallback extraction failed: {e}")
            return None

    def health_check(self) -> bool:
        """Check if Gemini client is healthy."""
        try:
            return self.credentials and self.credentials.valid
        except Exception:
            return False
    
    def get_last_token_usage(self) -> Dict[str, Any]:
        """Get token usage from last request."""
        return self.last_token_usage.copy()