# services/document-parser/src/core/processor.py
"""Core document processing logic."""

import time
from datetime import datetime
from typing import Dict

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from integrations.gemini import GeminiClient
from models.extraction import ProcessingResult, ProcessingStatus, ProcessingTask
from utils.logging import get_logger
from config import config

from .exceptions import DocumentProcessingError, ExtractionError, NonRetryableError

logger = get_logger(__name__)


class DocumentProcessor:
    """Main document processing class with retry logic and validation."""
    
    def __init__(self, gemini_client: GeminiClient):
        """Initialize processor with Gemini client."""
        self.gemini_client = gemini_client
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    async def process_document(self, task: ProcessingTask) -> ProcessingResult:
        """
        Main method to process a document.
        
        Args:
            task: Processing task containing document information
            
        Returns:
            ProcessingResult with extracted document and metadata
        """
        logger.info(f"Processing document: {task.doc_id}")
        start_time = time.time()
        
        try:
            # Update task status
            task.status = ProcessingStatus.PROCESSING
            task.processing_started_at = datetime.now()
            
            # Download and prepare document
            pdf_data = self._prepare_document(task)
            
            # Enhanced extraction and storage with validation
            try:
                from integrations.database.adapter import UnderwritingDatabaseAdapter
                
                # Extract document package with validation using existing client
                file_id = int(task.doc_id)
                # Use multi-attempt extraction and pick most complete result
                package = await self.gemini_client.extract_with_validation(pdf_data, file_id, attempts=3)
                
                if not package:
                    raise ExtractionError("Failed to extract valid entities from document")
                
                logger.info(f"Successfully extracted package for {task.doc_id}, type: {package.document_type}")
                
                # Initialize database adapter
                db_adapter = UnderwritingDatabaseAdapter()
                await db_adapter.initialize()
                
                # Store complete package to database
                success = await db_adapter.store_document_package(package)
                
                await db_adapter.close()
                
                if success:
                    logger.info(f"Document {task.doc_id} successfully processed and stored")
                    
                    # Create successful result
                    # Safely handle token usage data
                    token_usage = self.gemini_client.get_last_token_usage()
                    safe_token_usage = {}
                    if token_usage:
                        # Extract only safe integer values
                        for key, value in token_usage.items():
                            if isinstance(value, (int, float)):
                                safe_token_usage[key] = int(value)
                            elif isinstance(value, str) and value.isdigit():
                                safe_token_usage[key] = int(value)
                    
                    result = ProcessingResult(
                        task_id=task.task_id,
                        status=ProcessingStatus.COMPLETED,
                        extracted_document=package,  # Return the package for validation
                        processing_time_ms=int((time.time() - start_time) * 1000),
                        token_usage=safe_token_usage
                    )
                    
                    task.status = ProcessingStatus.COMPLETED
                    task.processing_completed_at = datetime.now()
                    
                    return result
                else:
                    raise ExtractionError("Failed to store document package to database")
                
            except Exception as e:
                logger.error(f"Enhanced processing error for {task.doc_id}: {e}")
                raise ExtractionError(f"Enhanced processing failed: {e}")
                
        except Exception as e:
            logger.error(f"Processing failed for {task.doc_id}: {e}")
            
            # Create failed result
            result = ProcessingResult(
                task_id=task.task_id,
                status=ProcessingStatus.FAILED,
                processing_time_ms=int((time.time() - start_time) * 1000),
                error_details={
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'task_id': str(task.task_id)
                }
            )
            
            task.status = ProcessingStatus.FAILED
            task.error_message = str(e)
            
            # Determine if error is retryable
            if isinstance(e, NonRetryableError):
                raise
            
            return result
    
    def _prepare_document(self, task: ProcessingTask) -> Dict[str, str]:
        """
        Download and prepare PDF for Gemini.
        Tries S3 direct access first, then falls back to URL download.
        
        Args:
            task: Processing task containing document information
            
        Returns:
            Dictionary with base64 encoded PDF data
        """
        logger.bind(
            contact_id=task.contact_id,
            doc_id=task.doc_id,
            s3_key_present=bool(task.s3_key),
            url_present=bool(task.document_url)
        ).debug("parse.prepare")
        
        # Strategy 1: Try S3 direct access first (most efficient)
        if task.s3_key and task.s3_key.strip():
            try:
                from integrations.s3 import S3Client
                s3_client = S3Client()
                logger.bind(
                    contact_id=task.contact_id,
                    doc_id=task.doc_id,
                    s3_key=task.s3_key
                ).debug("parse.s3_download")
                
                start_time = time.time()
                result = s3_client.download_document_from_s3(task.s3_key)
                download_time = int((time.time() - start_time) * 1000)
                
                logger.bind(
                    contact_id=task.contact_id,
                    doc_id=task.doc_id,
                    duration_ms=download_time
                ).info("parse.s3_success")
                return result
                
            except Exception as e:
                logger.bind(
                    contact_id=task.contact_id,
                    doc_id=task.doc_id,
                    error=type(e).__name__
                ).warning("parse.s3_failed")
        
        # Strategy 2: Fall back to URL download
        if task.document_url and task.document_url.strip():
            try:
                logger.bind(
                    contact_id=task.contact_id,
                    doc_id=task.doc_id,
                    url=task.document_url
                ).debug("parse.url_download")
                
                start_time = time.time()
                result = self._download_from_url(task.document_url)
                download_time = int((time.time() - start_time) * 1000)
                
                logger.bind(
                    contact_id=task.contact_id,
                    doc_id=task.doc_id,
                    duration_ms=download_time
                ).info("parse.url_success")
                return result
                
            except Exception as e:
                logger.bind(
                    contact_id=task.contact_id,
                    doc_id=task.doc_id,
                    error=type(e).__name__
                ).error("parse.url_failed")
                raise DocumentProcessingError(f"Failed to download document from URL: {e}")
        
        # No valid source available
        error_msg = f"No valid document source available"
        logger.bind(
            contact_id=task.contact_id,
            doc_id=task.doc_id,
            s3_key_present=bool(task.s3_key),
            url_present=bool(task.document_url)
        ).error("parse.no_source")
        raise DocumentProcessingError(error_msg)
    
    def _download_from_url(self, document_url: str) -> Dict[str, str]:
        """
        Download document from URL.
        
        Args:
            document_url: URL of the PDF document
            
        Returns:
            Dictionary with base64 encoded PDF data
        """
        try:
            timeout = config.processing_timeout if config.processing_timeout < 300 else 30.0
            with httpx.Client(follow_redirects=True, timeout=timeout) as client:
                response = client.get(document_url)
                response.raise_for_status()
                
                # Validate content type
                content_type = response.headers.get('content-type', '')
                if 'pdf' not in content_type.lower():
                    logger.warning(f"Unexpected content type: {content_type}")
                
                # Check file size
                content_length = len(response.content)
                max_size = config.max_file_size_mb * 1024 * 1024
                if content_length > max_size:
                    raise DocumentProcessingError(
                        f"Document too large: {content_length} bytes (max: {max_size})"
                    )
                
                import base64
                content_encoded = base64.b64encode(response.content).decode("utf-8")
                
                logger.info(f"Document downloaded from URL: {content_length} bytes")
                return {
                    "mimeType": "application/pdf",
                    "data": content_encoded
                }
                
        except httpx.RequestError as e:
            raise DocumentProcessingError(f"Failed to download document from URL: {e}")
        except Exception as e:
            raise DocumentProcessingError(f"Failed to prepare document from URL: {e}")