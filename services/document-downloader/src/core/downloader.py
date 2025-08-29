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
    TempFileError,
    DocumentNotFoundError,
    DocumentExcludedError
)


class DocumentDownloader:
    """Core document download logic."""
    
    def __init__(
        self,
        config: DocumentConfig,
        forth_client: Optional[ForthAPIClient] | Optional[Dict[str, ForthAPIClient]],
        s3_adapter: S3Adapter
    ):
        self.config = config
        # Support single client or map of clients per source
        if isinstance(forth_client, dict):
            self.forth_clients: Dict[str, ForthAPIClient] = forth_client
        else:
            self.forth_clients: Dict[str, ForthAPIClient] = {}
            if forth_client:
                self.forth_clients["DEFAULT"] = forth_client
        self.s3_adapter = s3_adapter
        self.download_semaphore = asyncio.Semaphore(config.worker_concurrency)
        # Reuse a single HTTP client for document downloads (keep-alive, HTTP/2)
        self._http_client: Optional[httpx.AsyncClient] = httpx.AsyncClient(
            timeout=httpx.Timeout(self.config.download_timeout),
            http2=True,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
        )
        
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
                # Get document URL and details from API
                try:
                    document_url, doc_type = await self.get_document_url_and_details(task)
                    if not document_url:
                        # This should not happen if exceptions are raised properly
                        return DownloadResult(
                            success=False,
                            status=DownloadStatus.FAILED,
                            error_message="Could not resolve document URL",
                            error_code="URL_RESOLUTION_FAILED"
                        )
                except DocumentNotFoundError:
                    return DownloadResult(
                        success=False,
                        status=DownloadStatus.NOT_FOUND,
                        error_message=f"Document not found in Forth API: {task.contact_id}/{task.doc_id}",
                        error_code="DOCUMENT_NOT_FOUND",
                        api_status_code=404
                    )
                except DocumentExcludedError as e:
                    return DownloadResult(
                        success=True,
                        status=DownloadStatus.SKIPPED,
                        error_message=str(e),
                        error_code="DOCUMENT_EXCLUDED"
                    )
                
                # Update task with retrieved doc_type if available
                if doc_type and hasattr(task, 'doc_type'):
                    original_doc_type = task.doc_type
                    task.doc_type = doc_type
                    logger.debug(
                        f"forth.doc_type_update contact_id={task.contact_id} doc_id={task.doc_id} from={original_doc_type} to={doc_type}"
                    )
                    
                # Generate S3 key early (used for idempotency check)
                s3_key = generate_s3_key(task, s3_prefix="")

                # Idempotency: if file already exists in S3, skip re-download
                try:
                    if await self.s3_adapter.file_exists(s3_key):
                        processing_time_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)
                        self._update_metrics(True, 0, processing_time_ms)
                        logger.info(
                            f"download.duplicate_skipped contact={task.contact_id} doc={task.doc_id} s3_key=\"{s3_key}\""
                        )
                        return DownloadResult(
                            success=True,
                            status=DownloadStatus.COMPLETED,
                            s3_key=s3_key,
                            s3_url=f"s3://{getattr(self.s3_adapter, 'bucket_name', '')}/{s3_key}",
                            file_size=0,
                            processing_time_ms=processing_time_ms,
                        )
                except Exception:
                    # If existence check fails, proceed with normal download path
                    pass

                # Download to temp file with streaming
                temp_file_path = await self._download_to_temp(
                    url=document_url,
                    filename=task.doc_name
                )
                
                # Get file info using async operations
                file_size = await aiofiles.os.path.getsize(temp_file_path)
                                
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
    
    async def get_document_url_and_details(self, task: DownloadTask) -> tuple[str, Optional[str]]:
        """
        Resolve document URL and get document type from Forth API using single call.
        
        Returns:
            tuple: (download_url, doc_type)
            
        Raises:
            DocumentNotFoundError: When document is not found in Forth API
            DocumentExcludedError: When document is excluded based on doc_type
            Exception: For other API or processing errors
        """
        # Select appropriate Forth client based on webhook source
        client = self._select_forth_client(getattr(task, 'webhook_source', None))
        if not client:
            logger.error("No Forth API client available for this source")
            raise Exception("Forth API client not configured")
        
        try:
            # Get both document info and doc_type in single API call
            document_info = await client.get_document(
                contact_id=task.contact_id,
                doc_id=task.doc_id
            )
            
            if not document_info:
                logger.bind(
                    contact_id=task.contact_id,
                    doc_id=task.doc_id
                ).warning("📄 Document not found in Forth API")
                raise DocumentNotFoundError(f"Document not found: {task.contact_id}/{task.doc_id}")
            
            download_url = document_info.get("download_url")
            doc_type = document_info.get("doc_type")
            file_name = document_info.get("file_name")  # Use file_name from API response
            
            # Update task with filename from API (ignore webhook filename)
            if file_name:
                task.doc_name = file_name
            else:
                task.doc_name = f"{task.doc_id}.pdf"  # Simple fallback
            
            # Check for excluded document types
            excluded_doc_types = [
                "3", "5", "8", "9", "10", "13", "14", "18", "29", "1781",
                "13109", "14172", "20620", "21989", "22743", "23074", 
                "23263", "23303", "23454", "23675"
            ]
            if doc_type and str(doc_type) in excluded_doc_types:
                logger.bind(
                    contact_id=task.contact_id,
                    doc_id=task.doc_id,
                    doc_type=doc_type
                ).info(f"download.excluded doc_type={doc_type}")
                raise DocumentExcludedError(f"Document excluded - doc_type: {doc_type}")
            
            if not download_url:
                logger.bind(
                    contact_id=task.contact_id,
                    doc_id=task.doc_id,
                    doc_type=doc_type
                ).error("📄 No download URL found in document info")
                raise Exception(f"No download URL found for document: {task.contact_id}/{task.doc_id}")
            
            logger.debug(
                f"forth.document_info contact_id={task.contact_id} doc_id={task.doc_id} doc_type={doc_type} file_name=\"{file_name}\""
            )
            
            return download_url, doc_type
            
        except (DocumentNotFoundError, DocumentExcludedError):
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            logger.bind(
                contact_id=task.contact_id,
                doc_id=task.doc_id
            ).error(f"Failed to get document info from Forth API: {e}")
            raise
    
    async def get_document_url(self, task: DownloadTask) -> Optional[str]:
        """Resolve document URL from task or Forth API (legacy method)."""
        url, _ = await self.get_document_url_and_details(task)
        return url
    
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
            if not self._http_client:
                self._http_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(self.config.download_timeout),
                    http2=True,
                    limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
                )

            # Stream download to avoid buffering entire file and to reuse keep-alive
            async with self._http_client.stream("GET", url, follow_redirects=True) as response:
                if response.status_code != 200:
                    logger.error(f"Download failed with status {response.status_code}")
                    raise TempFileError(f"HTTP {response.status_code}: Download failed")

                bytes_written = 0
                async with aiofiles.open(temp_file_path, 'wb') as f:
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 128):
                        if not chunk:
                            continue
                        bytes_written += len(chunk)
                        if bytes_written > max_size:
                            raise FileSizeExceededError(bytes_written, max_size)
                        await f.write(chunk)

            logger.debug(f"Downloaded {bytes_written} bytes to {temp_file_path}")
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

    async def close(self) -> None:
        """Close any HTTP resources held by the downloader."""
        try:
            if self._http_client:
                await self._http_client.aclose()
        except Exception:
            pass
    

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
        
        # Check Forth API (simple: any available client)
        if self.forth_clients:
            try:
                # Prefer DEFAULT if present; otherwise any one
                client = self.forth_clients.get("DEFAULT") or next(iter(self.forth_clients.values()))
                await client.health_check()
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

    def _select_forth_client(self, source: Optional[str]) -> Optional[ForthAPIClient]:
        """Pick a Forth client based on webhook source with sensible fallback."""
        if not self.forth_clients:
            return None
        if source and source in self.forth_clients:
            return self.forth_clients[source]
        # Try uppercase key if source provided in different case
        if source and source.upper() in self.forth_clients:
            return self.forth_clients[source.upper()]
        # Fallback to DEFAULT
        if "DEFAULT" in self.forth_clients:
            return self.forth_clients["DEFAULT"]
        # Fallback to any
        return next(iter(self.forth_clients.values()), None)
