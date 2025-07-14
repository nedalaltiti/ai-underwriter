# services/document-downloader/src/integrations/forth_api.py
import httpx
from typing import Optional, Dict, Any
from loguru import logger


class ForthAPIClient:
    """Client for interacting with Forth CRM API."""
    
    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None
        
        # Headers for all requests
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    async def initialize(self):
        """Initialize the HTTP client."""
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=httpx.Timeout(self.timeout)
        )
        logger.info(f"Forth API client initialized: {self.base_url}")
    
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
            # Construct endpoint
            endpoint = f"/contacts/{contact_id}/documents/{doc_id}"
            
            logger.info(f"Fetching document from Forth API: {endpoint}")
            
            response = await self.client.get(endpoint)
            
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
                    "filename": document_data.get("filename"),
                    "file_type": document_data.get("file_type"),
                    "created_at": document_data.get("created_at"),
                    "raw_response": document_data
                }
            
            elif response.status_code == 404:
                logger.warning(f"Document not found: {contact_id}/{doc_id}")
                return None
            
            else:
                logger.error(
                    f"Forth API error: {response.status_code} - {response.text}"
                )
                return None
                
        except httpx.TimeoutException:
            logger.error(f"Forth API timeout for document {contact_id}/{doc_id}")
            return None
        except Exception as e:
            logger.error(f"Forth API error: {e}")
            return None
    
    async def get_contact(self, contact_id: str) -> Optional[Dict[str, Any]]:
        """Get contact information from Forth API."""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        try:
            response = await self.client.get(f"/contacts/{contact_id}")
            
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
            response = await self.client.get("/health", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False