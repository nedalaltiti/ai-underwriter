# services/document-downloader/src/core/downloader.py
import os
import asyncio
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, UTC
import aiofiles
import httpx
from loguru import logger

from config import DocumentConfig
from models.download import DownloadTask, DownloadResult
from integrations.forth_api import ForthAPIClient
from forth_shared.adapters.storage import S3Adapter


class DocumentDownloader:
    """Core document download logic."""
    
    def __init__(
        self,
        config: DocumentConfig,
        forth_client: Optional[ForthAPIClient],
        s3_adapter: S3Adapter
    ):
        self.config = config
        self.forth_client = forth_client
        self.s3_adapter = s3_adapter
        self.download_semaphore = asyncio.Semaphore(config.worker_concurrency)
        
        # Metrics
        self.metrics = {
            "total_downloads": 0,
            "successful_downloads": 0,
            "failed_downloads": 0,
            "total_bytes": 0,
            "average_download_time_ms": 0
        }
    
    async def download_document(self, task: DownloadTask) -> DownloadResult:
        """Download a document and upload to S3."""
        start_time = datetime.now(UTC)
        temp_file_path = None
        
        try:
            async with self.download_semaphore:
                # Get document URL
                document_url = await self._resolve_document_url(task)
                if not document_url:
                    return DownloadResult(
                        success=False,
                        error_message="Could not resolve document URL"
                    )
                
                # Download to temp file
                temp_file_path = await self._download_to_temp(
                    url=document_url,
                    filename=task.doc_name or f"{task.doc_id}.pdf"
                )
                
                if not temp_file_path:
                    return DownloadResult(
                        success=False,
                        error_message="Download failed"
                    )
                
                # Get file info
                file_size = os.path.getsize(temp_file_path)
                
                # Generate S3 key
                s3_key = self._generate_s3_key(task)
                
                # Upload to S3
                upload_result = await self.s3_adapter.upload_file(
                    file_path=temp_file_path,
                    s3_key=s3_key,
                    metadata={
                        "contact_id": task.contact_id,
                        "doc_id": task.doc_id,
                        "doc_type": task.doc_type,
                        "doc_name": task.doc_name or "",
                        "correlation_id": task.correlation_id or "",
                        "download_timestamp": datetime.now(UTC).isoformat()
                    }
                )
                
                # Update metrics
                processing_time_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)
                self._update_metrics(True, file_size, processing_time_ms)
                
                logger.bind(
                    contact_id=task.contact_id,
                    doc_id=task.doc_id,
                    s3_key=s3_key,
                    file_size=file_size,
                    processing_time_ms=processing_time_ms
                ).info(
                    f"✅ Document downloaded: {task.doc_id} -> {s3_key} ({file_size} bytes, {processing_time_ms}ms)"
                )
                
                return DownloadResult(
                    success=True,
                    s3_key=s3_key,
                    s3_url=upload_result["url"],
                    file_size=file_size,
                    processing_time_ms=processing_time_ms,
                    content_type=upload_result.get("content_type", "application/pdf")
                )
                
        except Exception as e:
            processing_time_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)
            self._update_metrics(False, 0, processing_time_ms)
            
            logger.error(f"Document download failed: {e}")
            return DownloadResult(
                success=False,
                error_message=str(e),
                processing_time_ms=processing_time_ms
            )
            
        finally:
            # Cleanup temp file
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp file: {e}")
    
    async def _resolve_document_url(self, task: DownloadTask) -> Optional[str]:
        """Resolve document URL from task or Forth API."""
        # If URL is provided in task, use it
        if task.doc_url:
            logger.debug(f"🔗 Using provided URL: {task.doc_url}")
            return task.doc_url
        
        # Otherwise, fetch from Forth API
        if not self.forth_client:
            logger.error("❌ No document URL provided and Forth API not configured")
            return None
        
        try:
            document_info = await self.forth_client.get_document(
                contact_id=task.contact_id,
                doc_id=task.doc_id
            )
            
            if document_info and document_info.get("download_url"):
                return document_info["download_url"]
            
            logger.error(f"No download URL in Forth API response: {document_info}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get document URL from Forth API: {e}")
            return None
    
    async def _download_to_temp(self, url: str, filename: str) -> Optional[str]:
        """Download file to temporary location."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    follow_redirects=True,
                    timeout=self.config.download_timeout
                )
                
                if response.status_code != 200:
                    logger.error(f"Download failed with status {response.status_code}")
                    return None
                
                # Create temp file
                suffix = Path(filename).suffix or ".pdf"
                temp_file = tempfile.NamedTemporaryFile(
                    dir=self.config.temp_dir,
                    suffix=suffix,
                    delete=False
                )
                
                # Write content
                async with aiofiles.open(temp_file.name, 'wb') as f:
                    await f.write(response.content)
                
                logger.debug(f"Downloaded {len(response.content)} bytes to {temp_file.name}")
                return temp_file.name
                
        except asyncio.TimeoutError:
            logger.error(f"Download timeout after {self.config.download_timeout}s")
            return None
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None
    
    def _generate_s3_key(self, task: DownloadTask) -> str:
        """Generate S3 key for document."""
        # Use date partitioning for better organization
        date_prefix = datetime.now(UTC).strftime("%Y/%m/%d")
        
        # Clean filename
        filename = task.doc_name or f"{task.doc_id}.pdf"
        safe_filename = Path(filename).name
        
        # Generate key
        return f"{self.config.s3_prefix}/{date_prefix}/{task.contact_id}/{task.doc_id}/{safe_filename}"
    
    def _update_metrics(self, success: bool, file_size: int, processing_time_ms: int):
        """Update download metrics."""
        self.metrics["total_downloads"] += 1
        
        if success:
            self.metrics["successful_downloads"] += 1
            self.metrics["total_bytes"] += file_size
        else:
            self.metrics["failed_downloads"] += 1
        
        # Update average processing time
        total = self.metrics["total_downloads"]
        current_avg = self.metrics["average_download_time_ms"]
        self.metrics["average_download_time_ms"] = (
            (current_avg * (total - 1) + processing_time_ms) / total
        )
    
    async def health_check(self) -> Dict[str, Any]:
        """Check downloader health."""
        checks = {
            "s3": {"status": "unknown"},
            "forth_api": {"status": "unknown"}
        }
        
        # Check S3
        try:
            await self.s3_adapter.health_check()
            checks["s3"]["status"] = "healthy"
        except Exception as e:
            checks["s3"] = {"status": "unhealthy", "error": str(e)}
        
        # Check Forth API
        if self.forth_client:
            try:
                await self.forth_client.health_check()
                checks["forth_api"]["status"] = "healthy"
            except Exception as e:
                checks["forth_api"] = {"status": "unhealthy", "error": str(e)}
        else:
            checks["forth_api"]["status"] = "not_configured"
        
        # Overall status
        unhealthy = any(
            check.get("status") == "unhealthy" 
            for check in checks.values()
        )
        
        return {
            "status": "unhealthy" if unhealthy else "healthy",
            "checks": checks,
            "metrics": self.metrics
        }
