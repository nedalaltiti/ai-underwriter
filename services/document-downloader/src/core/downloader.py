# services/document-downloader/src/core/downloader.py
import os
import asyncio
import tempfile
import stat
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, UTC
import aiofiles
import aiofiles.os
import httpx
from loguru import logger

from config import DocumentConfig
from models.download import DownloadTask, DownloadResult, DownloadStatus
from integrations.forth_api import ForthAPIClient
from libs.forth_shared.adapters.storage import S3Adapter
from utils.metadata import prepare_s3_metadata
from utils.file_operations import generate_s3_key, get_file_extension_from_filename
from core.exceptions import (
    FileSizeExceededError, 
    DownloadTimeoutError, 
    TempFileError
)


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
            "average_download_time_ms": 0,
            "retry_count": 0,
            "forth_api_errors": 0,
            "s3_upload_errors": 0,
            "download_errors": 0
        }
    
    async def download_document(self, task: DownloadTask) -> DownloadResult:
        """Download a document and upload to S3."""
        start_time = datetime.now(UTC)
        temp_file_path = None
        
        try:
            # Use semaphore to limit concurrent downloads
            async with self.download_semaphore:
                # Get document URL
                document_url = await self.get_document_url(task)
                if not document_url:
                    return DownloadResult(
                        success=False,
                        status=DownloadStatus.FAILED,
                        error_message="Could not resolve document URL"
                    )
                    
                # Download to temp file with streaming
                temp_file_path = await self._download_to_temp(
                    url=document_url,
                    filename=task.doc_name or f"{task.doc_id}.pdf"
                )
                
                # Get file info using async operations
                file_size = await aiofiles.os.path.getsize(temp_file_path)
                
                # Generate S3 key with new structure: date/contact_id/doc_id/filename
                s3_key = generate_s3_key(task, s3_prefix="")
                
                # Upload to S3 with sanitized metadata
                raw_metadata = {
                    "contact_id": task.contact_id,
                    "doc_id": task.doc_id,
                    "doc_type": task.doc_type or "",
                    "doc_name": task.doc_name or "",
                    "correlation_id": task.correlation_id or "",
                    "download_timestamp": datetime.now(UTC).isoformat()
                }
                
                upload_result = await self.s3_adapter.upload_file(
                    file_path=temp_file_path,
                    s3_key=s3_key,
                    metadata=prepare_s3_metadata(raw_metadata)
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
                    status=DownloadStatus.COMPLETED,
                    s3_key=s3_key,
                    s3_url=upload_result["url"],
                    file_size=file_size,
                    processing_time_ms=processing_time_ms,
                    content_type=upload_result.get("content_type", "application/pdf")
                )
                
        except FileSizeExceededError as e:
            processing_time_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)
            self._update_metrics(False, 0, processing_time_ms)
            self.metrics["download_errors"] += 1
            
            logger.error(f"File size exceeded: {e}")
            return DownloadResult(
                success=False,
                status=DownloadStatus.FAILED,
                error_message=f"File too large: {e}",
                processing_time_ms=processing_time_ms
            )
        except DownloadTimeoutError as e:
            processing_time_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)
            self._update_metrics(False, 0, processing_time_ms)
            self.metrics["download_errors"] += 1
            
            logger.error(f"Download timeout: {e}")
            return DownloadResult(
                success=False,
                status=DownloadStatus.FAILED,
                error_message=str(e),
                processing_time_ms=processing_time_ms
            )
        except TempFileError as e:
            processing_time_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)
            self._update_metrics(False, 0, processing_time_ms)
            self.metrics["download_errors"] += 1
            
            logger.error(f"Temp file error: {e}")
            return DownloadResult(
                success=False,
                status=DownloadStatus.FAILED,
                error_message=str(e),
                processing_time_ms=processing_time_ms
            )
        except Exception as e:
            processing_time_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)
            self._update_metrics(False, 0, processing_time_ms)
            
            logger.error(f"Document download failed: {e}")
            return DownloadResult(
                success=False,
                status=DownloadStatus.FAILED,
                error_message=str(e),
                processing_time_ms=processing_time_ms
            )
            
        finally:
            # Cleanup temp file using async operations
            if temp_file_path:
                try:
                    if await aiofiles.os.path.exists(temp_file_path):
                        await aiofiles.os.unlink(temp_file_path)
                        logger.debug(f"Cleaned up temp file: {temp_file_path}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp file: {e}")
    
    async def get_document_url(self, task: DownloadTask) -> Optional[str]:
        """Resolve document URL from task or Forth API."""
        # fetch from Forth API
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
    
    async def _download_to_temp(self, url: str, filename: str) -> str:
        """Download file to temporary location."""
        temp_file_path = None
        try:
            # Create secure temp file
            suffix = get_file_extension_from_filename(filename)
            temp_fd, temp_file_path = tempfile.mkstemp(
                dir=self.config.temp_dir,
                suffix=suffix,
                prefix="download_"
            )
            
            # Set secure permissions (owner read/write only)
            os.chmod(temp_file_path, stat.S_IRUSR | stat.S_IWUSR)
            os.close(temp_fd)  # Close the file descriptor, we'll use aiofiles
            
            max_size = self.config.get_max_file_size_bytes()
            
            timeout = httpx.Timeout(self.config.download_timeout)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, follow_redirects=True)
                
                if response.status_code != 200:
                    logger.error(f"Download failed with status {response.status_code}")
                    raise TempFileError(f"HTTP {response.status_code}: {response.text}")
                
                # Check file size before processing
                content_size = len(response.content)
                if content_size > max_size:
                    raise FileSizeExceededError(content_size, max_size)
                
                # Write entire content to temp file
                async with aiofiles.open(temp_file_path, 'wb') as f:
                    await f.write(response.content)
            
            logger.debug(f"Downloaded {content_size} bytes to {temp_file_path}")
            return temp_file_path
            
        except httpx.TimeoutException:
            logger.error(f"Download timeout after {self.config.download_timeout}s")
            raise DownloadTimeoutError(f"Download timeout after {self.config.download_timeout}s")
        except (FileSizeExceededError, DownloadTimeoutError, TempFileError):
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            logger.error(f"Download error: {e}")
            raise TempFileError(f"Download failed: {e}")
        finally:
            # Clean up temp file on error
            if temp_file_path and os.path.exists(temp_file_path):
                # Only clean up if we're raising an exception
                import sys
                if sys.exc_info()[0] is not None:
                    try:
                        os.unlink(temp_file_path)
                        logger.debug(f"Cleaned up temp file on error: {temp_file_path}")
                    except Exception as cleanup_error:
                        logger.warning(f"Failed to cleanup temp file on error: {cleanup_error}")
    

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
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        return self.metrics.copy()
