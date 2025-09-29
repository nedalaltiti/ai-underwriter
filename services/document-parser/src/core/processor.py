# services/document-parser/src/core/processor_simple.py
"""
Simplified document processor focused on efficiency and accuracy.
Single-pass extraction with direct database storage.
"""

import time
import httpx
from datetime import datetime
from typing import Dict
from tenacity import retry, stop_after_attempt, wait_exponential

from integrations.gemini import GeminiClient
from models.extraction import ProcessingResult, ProcessingStatus, ProcessingTask
from utils.logging import get_logger
from config import config

from .exceptions import DocumentProcessingError, ExtractionError, NonRetryableError

logger = get_logger(__name__)


class DocumentProcessor:
    """Document processor with single-pass extraction."""
    
    def __init__(self, gemini_client: GeminiClient):
        """Initialize processor with Gemini client."""
        self.gemini_client = gemini_client
    
    async def process_document(self, task: ProcessingTask) -> ProcessingResult:
        """
        Process document with extraction and storage.
        
        Args:
            task: Processing task containing document information
            
        Returns:
            ProcessingResult with extracted document and metadata
        """
        logger.bind(doc_id=task.doc_id).info("processing.start")
        start_time = time.time()
        
        try:
            # Update task status
            task.status = ProcessingStatus.PROCESSING
            task.processing_started_at = datetime.now()
            
            # Download and prepare document
            pdf_data = await self._prepare_document(task)
            
            # Single-pass extraction
            file_id = int(task.doc_id)
            package = await self.gemini_client.extract_document(pdf_data, file_id)
            
            if not package:
                raise ExtractionError("Failed to extract entities from document")
            
            logger.bind(
                doc_id=task.doc_id, 
                document_type=package.document_type,
                entities_count=self._count_extracted_entities(package)
            ).info("extraction.success")
            
            # Store to database
            storage_success = await self._store_to_database(package, task.doc_id)
            
            # Update task status
            task.status = ProcessingStatus.COMPLETED
            task.processing_completed_at = datetime.now()
            
            # Return result
            return ProcessingResult(
                task_id=task.task_id,
                status=ProcessingStatus.COMPLETED,
                extracted_document=package,
                processing_time_ms=int((time.time() - start_time) * 1000),
                token_usage=self.gemini_client.get_last_token_usage(),
                validation_summary={
                    'extraction_method': 'single_pass',
                    'database_stored': storage_success,
                    'confidence_score': package.confidence_score,
                    'document_type': package.document_type,
                    'entities_extracted': self._count_extracted_entities(package)
                }
            )
                
        except NonRetryableError as e:
            logger.bind(doc_id=task.doc_id, error=str(e)).error("processing.non_retryable")
            task.status = ProcessingStatus.FAILED
            task.error_message = str(e)
            return ProcessingResult(
                task_id=task.task_id,
                status=ProcessingStatus.FAILED,
                processing_time_ms=int((time.time() - start_time) * 1000),
                error_details={'error_message': str(e), 'error_type': 'NonRetryableError'}
            )
        except Exception as e:
            logger.bind(doc_id=task.doc_id, error=str(e)).error("processing.failed")
            task.status = ProcessingStatus.FAILED
            task.error_message = str(e)
            raise DocumentProcessingError(f"Failed to process document: {e}") from e
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def _prepare_document(self, task: ProcessingTask) -> Dict[str, str]:
        """Download and prepare document for processing."""
        try:
            if task.s3_key:
                # Download from S3
                from integrations.s3 import S3Client
                s3_client = S3Client()
                pdf_data_result = s3_client.download_document_from_s3(task.s3_key)
                
                # Extract the PDF content from the result
                import base64
                pdf_content = base64.b64decode(pdf_data_result['data'])
            elif task.document_url:
                # Download from URL
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(task.document_url)
                    response.raise_for_status()
                    pdf_content = response.content
            else:
                raise DocumentProcessingError("No document source provided (s3_key or document_url)")
            
            if not pdf_content:
                raise DocumentProcessingError("Downloaded document is empty")
            
            # Prepare for Gemini
            import base64
            pdf_data = {
                "mimeType": "application/pdf",
                "data": base64.b64encode(pdf_content).decode('utf-8')
            }
            
            logger.bind(
                doc_id=task.doc_id,
                size_mb=len(pdf_content) / 1024 / 1024
            ).info("document.prepared")
            
            return pdf_data
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise NonRetryableError(f"Document not found: {e}")
            else:
                raise DocumentProcessingError(f"Failed to download document: {e}")
        except Exception as e:
            raise DocumentProcessingError(f"Failed to prepare document: {e}")
    
    async def _store_to_database(self, package, doc_id: str) -> bool:
        """Store extracted package to database."""
        try:
            from integrations.database.adapter import UnderwritingDatabaseAdapter
            
            db_adapter = UnderwritingDatabaseAdapter()
            await db_adapter.initialize()
            
            success = await db_adapter.store_document_package(package)
            await db_adapter.close()
            
            if success:
                logger.bind(doc_id=doc_id).info("storage.success")
            else:
                logger.bind(doc_id=doc_id).warning("storage.failed")
                
            return success
            
        except Exception as db_error:
            logger.bind(doc_id=doc_id, error=str(db_error)).error("storage.error")
            return False
    
    def _count_extracted_entities(self, package) -> int:
        """Count number of extracted entities in package."""
        count = 0
        
        # Single entities
        single_entities = [
            'engagement_term', 'financial_analysis', 'payment_gateway_agreement',
            'payment_bank_info', 'power_of_attorney', 'legal_plan_agreement',
            'disclosure', 'program_disclosure', 'fcra_consent', 'attorney_privileged_client_info',
            'clixsign_sender', 'cancellation_notice'
        ]
        
        for entity_name in single_entities:
            if getattr(package, entity_name, None):
                count += 1
        
        # List entities
        list_entities = ['debt_schedule', 'payment_service_fees', 'payment_deposit_schedule', 'clixsign_signers']
        for entity_name in list_entities:
            entity_list = getattr(package, entity_name, None)
            if entity_list and len(entity_list) > 0:
                count += len(entity_list)
        
        return count
