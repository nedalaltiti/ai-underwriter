# services/document-downloader/src/integrations/forth_api.py
import httpx
from typing import Optional, Dict, Any
from loguru import logger

from integrations.forth_auth import ForthAuthManager
from core.exceptions import DocumentNotFoundError, ForthAPIError


class ForthAPIClient:
    """Client for interacting with Forth CRM API."""
    
    def __init__(self, base_url: str, auth_manager: ForthAuthManager, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.auth_manager = auth_manager
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None
    
    async def initialize(self):
        """Initialize the HTTP client."""
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout)
        )
        logger.info(f"Forth API client initialized: {self.base_url}")
    
    async def _get_headers(self) -> Dict[str, str]:
        """Get headers with current API key."""
        api_key = await self.auth_manager.get_current_api_key()
        if not api_key:
            raise RuntimeError("No valid API key available")
        
        return {
            "Api-Key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            logger.info("Forth API client closed")
    
    async def get_document(self, contact_id: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        Get document information from Forth API.
        
        Args:
            contact_id: Contact identifier
            doc_id: Document identifier
            
        Returns:
            Document information including download URL
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Call initialize() first.")
        
        try:
            # Construct endpoint - API requires file_type parameter (using 'uploaded' as default)
            endpoint = f"/contacts/{contact_id}/documents/{doc_id}/uploaded"
            
            logger.debug(f"forth.request endpoint={endpoint}")
            
            # Retry on rate limits
            max_attempts = 5
            attempt = 0
            last_exc: Optional[Exception] = None
            while attempt < max_attempts:
                attempt += 1
                headers = await self._get_headers()
                response = await self.client.get(endpoint, headers=headers)
                status = response.status_code
                if status == 401 or status == 403:
                    # Auth errors are not retryable here
                    break
                if status == 429 or 500 <= status < 600:
                    retry_after = 0
                    try:
                        ra = response.headers.get("Retry-After")
                        if ra:
                            retry_after = int(ra)
                    except Exception:
                        retry_after = 0
                    if attempt < max_attempts:
                        import asyncio, random
                        base_delay = min(2 ** (attempt - 1), 30)
                        delay = retry_after or base_delay + random.uniform(0, 0.5)
                        logger.warning(
                            f"forth.retry contact={contact_id} doc={doc_id} status={status} attempt={attempt}/{max_attempts} delay_s={delay:.2f}"
                        )
                        await asyncio.sleep(delay)
                        continue
                # Either success or non-retryable
                break
            
            if response.status_code == 200:
                data = response.json()
                
                # Handle Forth API response structure
                if isinstance(data, dict) and "response" in data:
                    document_data = data["response"]
                else:
                    document_data = data
                
                # Extract download URL - try multiple possible fields
                download_url = (
                    document_data.get("file_content") or
                    document_data.get("download_url") or
                    document_data.get("url") or
                    document_data.get("download")
                )
                
                # If relative URL, make it absolute
                if download_url and download_url.startswith("/"):
                    # Remove /v1 if present in base URL
                    base = self.base_url.replace("/v1", "")
                    download_url = f"{base}{download_url}"
                
                return {
                    "doc_id": doc_id,
                    "contact_id": contact_id,
                    "download_url": download_url,
                    "file_name": document_data.get("file_name"),  
                    "file_type": document_data.get("file_type"),
                    "doc_type": document_data.get("doc_type"),
                    "created_at": document_data.get("created_at"),
                    "raw_response": document_data
                }
            
            elif response.status_code == 404:
                logger.warning(f"forth.not_found contact={contact_id} doc={doc_id}")
                raise DocumentNotFoundError(f"{contact_id}/{doc_id}")
            
            else:
                # Log compact error without raw JSON body to avoid formatter issues
                logger.error(
                    f"forth.error contact={contact_id} doc={doc_id} status={response.status_code}"
                )
                # Normalize common auth errors to explicit codes upstream
                msg = response.text
                raise ForthAPIError(response.status_code, msg)
                
        except httpx.TimeoutException:
            logger.warning(f"forth.timeout contact={contact_id} doc={doc_id} timeout_s={self.timeout}")
            raise ForthAPIError(408, f"timeout after {self.timeout}s")
        except DocumentNotFoundError:
            raise
        except Exception as e:
            if not isinstance(e, ForthAPIError):
                logger.error(f"forth.error contact={contact_id} doc={doc_id} error={type(e).__name__}")
            raise
    
    async def get_contact(self, contact_id: str) -> Optional[Dict[str, Any]]:
        """Get contact information from Forth API."""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        try:
            headers = await self._get_headers()
            response = await self.client.get(f"/contacts/{contact_id}", headers=headers)
            
            if response.status_code == 200:
                return response.json()
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get contact {contact_id}: {e}")
            return None
    

    async def health_check(self) -> bool:
        """Check if Forth API is accessible."""
        if not self.client:
            return False
        
        try:
            # Health check doesn't need authentication
            response = await self.client.get("/health", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False