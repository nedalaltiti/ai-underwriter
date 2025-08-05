# services/document-downloader/src/api/routes.py
from typing import Dict, Any, Optional, List
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger

from api.dependencies import get_downloader, get_worker, get_config
from core.downloader import DocumentDownloader
from services.worker import DownloadWorker
from models.download import DownloadTask, DownloadResult, DownloadStatus
from libs.forth_shared.utils.tracing import generate_correlation_id


# Main API router with versioning
api_router = APIRouter(prefix="/api/v1", tags=["api"])


@api_router.post(
    "/downloads/manual/{contact_id}/{doc_id}",
    response_model=DownloadResult,
    summary="Manual document download",
    description="Manually trigger a document download (bypasses queue)"
)
async def manual_download(
    contact_id: str,
    doc_id: str,
    doc_name: str = Query(..., description="Document filename"),
    downloader: DocumentDownloader = Depends(get_downloader)
) -> DownloadResult:
    """
    Manually trigger document download (for testing/debugging).
    
    This endpoint bypasses the queue and directly downloads a document.
    """
    try:
        correlation_id = generate_correlation_id("manual")
        
        task = DownloadTask(
            contact_id=contact_id,
            doc_id=doc_id,
            doc_name=doc_name,
            correlation_id=correlation_id
        )
        
        logger.bind(
            contact_id=contact_id,
            doc_id=doc_id,
            correlation_id=correlation_id
        ).info("Manual download requested")
        
        result = await downloader.download_document(task)
        
        if not result.success:
            raise HTTPException(
                status_code=500,
                detail=f"Download failed: {result.error_message}"
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Manual download error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get(
    "/downloads/metrics",
    summary="Download metrics",
    description="Get download performance metrics"
)
async def get_metrics(
    downloader: DocumentDownloader = Depends(get_downloader),
    worker: DownloadWorker = Depends(get_worker)
) -> Dict[str, Any]:
    """Get service metrics."""
    return {
        "service": "document-downloader",
        "downloader_metrics": downloader.metrics,
        "worker": {
            "running": worker.running,
            "input_queue": worker.config.input_queue_name,
            "output_queue": worker.config.output_queue_name or "not_configured"
        },
        "timestamp": datetime.now(UTC).isoformat()
    }


@api_router.get(
    "/downloads/status",
    summary="Download status",
    description="Get current download worker status"
)
async def get_status(
    downloader: DocumentDownloader = Depends(get_downloader),
    config = Depends(get_config)
) -> Dict[str, Any]:
    """Get service status and configuration."""
    return {
        "service": config.service_name,
        "version": config.service_version,
        "environment": config.environment,
        "status": "running",
        "configuration": {
            "worker_concurrency": config.worker_concurrency,
            "download_timeout": config.download_timeout,
            "temp_dir": config.temp_dir,
            "s3_bucket": config.s3_bucket_name,
            "forth_api_configured": bool(config.forth_api_base_url)
        },
        "timestamp": datetime.now(UTC).isoformat()
    }
