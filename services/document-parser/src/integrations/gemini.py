# services/document-parser/src/integrations/gemini.py
"""Gemini API integration for document extraction."""

import json
from typing import Any, Dict

import httpx
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from tenacity import retry, stop_after_attempt, wait_exponential

from config import config
from core.exceptions import GeminiAPIError, GeminiRateLimitError, GeminiTimeoutError
from utils.logging import get_logger
from utils.json_parser import extract_json_from_response

logger = get_logger(__name__)


class PromptBuilder:
    """Build consistent, structured prompts for extraction."""
    
    @staticmethod
    def build_extraction_prompt() -> str:
        """Build the main extraction prompt."""
        return """You are an expert legal document analyst specializing in debt settlement contract analysis.

TASK: Extract ALL information from the document in a structured JSON format that EXACTLY matches the schema below.

CRITICAL RULES:
1. Extract EVERY piece of information present in the document
2. Use null for missing information - DO NOT skip fields
3. Maintain exact data types as specified in the schema
4. Extract ALL document sections, even if they seem redundant
5. Include ALL creditors and payment schedules
6. Validate formats (dates: YYYY-MM-DD, SSN: XXX-XX-XXXX, IP: x.x.x.x)

OUTPUT SCHEMA:
{
    "client_info": {
        "name": "string",
        "ssn": "string (XXX-XX-XXXX format)",
        "dob": "YYYY-MM-DD",
        "email": "string",
        "phone": "XXX-XXX-XXXX",
        "address": {
            "street": "string",
            "city": "string",
            "state": "string (2 letter code)",
            "zip_code": "string"
        }
    },
    "financial_analysis": {
        "monthly_income": number,
        "monthly_expenses": number,
        "net_income": number,
        "total_enrolled_debt": number,
        "estimated_program_length": integer,
        "monthly_program_deposit": number,
        "estimated_settlement_amount": number,
        "total_program_fees": number,
        "estimated_savings": number,
        "estimated_total_cost": number
    },
    "creditors": [
        {
            "creditor_name": "string",
            "account_name": "string",
            "current_balance": number,
            "debt_type": "Credit Card|Installment|Personal Loan|Collection|Medical|Other",
            "account_number": "string or null"
        }
    ],
    "bank_details": {
        "bank_name": "string",
        "account_number": "string",
        "routing_number": "string (9 digits)",
        "account_type": "Checking|Savings"
    },
    "document_sections": [
        {
            "section_name": "string",
            "data": {object with all fields from that section},
            "signatures_valid": boolean,
            "dates_valid": boolean
        }
    ],
    "vlp_enrolled": boolean,
    "contract_date": "YYYY-MM-DD",
    "first_payment_date": "YYYY-MM-DD",
    "sender_ip": "string (IP address)",
    "signer_ip": "string (IP address)"
}

IMPORTANT: 
- Extract COMPLETE payment schedules with ALL dates and amounts
- Include ALL fee structures and charges
- Capture EVERY signature and initial field
- Return ONLY valid JSON - no additional text or formatting"""


class GeminiClient:
    """Client for interacting with Google Gemini API."""
    
    def __init__(self, service_account_info: Dict[str, Any]):
        """
        Initialize Gemini client.
        
        Args:
            service_account_info: Service account credentials dictionary
        """
        self.service_account_info = service_account_info
        self.model_name = config.gemini.model_name
        self.credentials = self._initialize_credentials()
        self.endpoint_url = self._build_endpoint_url()
        self._last_token_usage = {}
        
        logger.info(f"Gemini client initialized for model: {self.model_name}")
    
    def _initialize_credentials(self):
        """Initialize Google Cloud credentials."""
        try:
            credentials = service_account.Credentials.from_service_account_info(
                self.service_account_info,
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            credentials.refresh(Request())
            logger.info("Gemini credentials initialized successfully")
            return credentials
        except Exception as e:
            logger.error(f"Failed to initialize Gemini credentials: {e}")
            raise GeminiAPIError(f"Credential initialization failed: {e}")
    
    def _build_endpoint_url(self) -> str:
        """Build Gemini API endpoint URL."""
        base_url = f"https://{config.gemini.region}-aiplatform.googleapis.com/v1"
        return (f"{base_url}/projects/{config.gemini.project_id}"
                f"/locations/{config.gemini.region}"
                f"/publishers/google/models/{self.model_name}:generateContent")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    def extract_document_data(self, pdf_data: Dict[str, str]) -> Dict[str, Any]:
        """
        Extract document data using Gemini API.
        
        Args:
            pdf_data: Dictionary containing base64 encoded PDF data
            
        Returns:
            Extracted document data as dictionary
        """
        payload = self._build_extraction_payload(pdf_data)
        response = self._call_gemini_api(payload)
        return self._extract_json_from_response(response)
    
    def _build_extraction_payload(self, pdf_data: Dict[str, str]) -> Dict[str, Any]:
        """Build the API payload for extraction."""
        return {
            "contents": [{
                "role": "user",
                "parts": [
                    {"text": PromptBuilder.build_extraction_prompt()},
                    {"inlineData": pdf_data}
                ]
            }],
            "generationConfig": {
                "temperature": config.gemini.temperature,
                "topK": config.gemini.top_k,
                "topP": config.gemini.top_p,
                "maxOutputTokens": config.gemini.max_output_tokens,
                "responseMimeType": "application/json"
            },
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT", 
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_NONE"
                }
            ]
        }
    
    def _call_gemini_api(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Call Gemini API with error handling."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.credentials.token}"
        }
        
        try:
            with httpx.Client(timeout=config.gemini.timeout) as client:
                response = client.post(
                    url=self.endpoint_url,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                
                result = response.json()
                
                # Store token usage for metrics
                self._last_token_usage = result.get('usageMetadata', {})
                
                logger.info(f"Gemini API call successful. Tokens used: {self._last_token_usage}")
                return result
                
        except httpx.TimeoutException as e:
            logger.error(f"Gemini API timeout: {e}")
            raise GeminiTimeoutError(f"API call timed out: {e}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.error("Gemini API rate limit exceeded")
                raise GeminiRateLimitError("Rate limit exceeded")
            else:
                logger.error(f"Gemini API HTTP error: {e}")
                raise GeminiAPIError(f"HTTP error {e.response.status_code}: {e}")
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise GeminiAPIError(f"API call failed: {e}")
    
    def _extract_json_from_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and parse JSON from Gemini response."""
        try:
            if 'candidates' not in response:
                raise GeminiAPIError("No candidates in response")
            
            candidates = response['candidates']
            if not candidates:
                raise GeminiAPIError("Empty candidates list")
            
            candidate = candidates[0]
            if 'content' not in candidate:
                raise GeminiAPIError("No content in candidate")
            
            content = candidate['content']
            if 'parts' not in content or not content['parts']:
                raise GeminiAPIError("No parts in content")
            
            text_content = content['parts'][0].get('text', '')
            if not text_content:
                raise GeminiAPIError("Empty text content")
            
            # Extract JSON using utility function
            return extract_json_from_response(text_content)
            
        except Exception as e:
            logger.error(f"Failed to extract JSON from response: {e}")
            raise GeminiAPIError(f"Response parsing failed: {e}")
    
    def get_last_token_usage(self) -> Dict[str, int]:
        """Get token usage from last API call."""
        return self._last_token_usage.copy()
    
    def health_check(self) -> bool:
        """Perform a basic health check of the Gemini API."""
        try:
            # Simple test payload
            test_payload = {
                "contents": [{
                    "role": "user",
                    "parts": [{"text": "Hello, respond with just 'OK'"}]
                }],
                "generationConfig": {
                    "temperature": 0.0,
                    "maxOutputTokens": 10
                }
            }
            
            response = self._call_gemini_api(test_payload)
            return 'candidates' in response and len(response['candidates']) > 0
            
        except Exception as e:
            logger.error(f"Gemini health check failed: {e}")
            return False