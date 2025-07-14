# services/document-downloader/src/api/routes.py
import json
from typing import Dict, Any, Optional
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from api.dependencies import get_downloader, get_worker, get_config
from core.downloader import DocumentDownloader
from services.worker import DownloadWorker
from models.download import DownloadTask, DownloadResult


router = APIRouter(prefix="/api/v1", tags=["downloader"])


@router.post("/download/{contact_id}/{doc_id}")
async def manual_download(
    contact_id: str,
    doc_id: str,
    doc_name: Optional[str] = Query(None, description="Document filename"),
    doc_url: Optional[str] = Query(None, description="Direct document URL"),
    downloader: DocumentDownloader = Depends(get_downloader)
) -> DownloadResult:
    """
    Manually trigger document download (for testing/debugging).
    
    This endpoint bypasses the queue and directly downloads a document.
    """
    try:
        task = DownloadTask(
            contact_id=contact_id,
            doc_id=doc_id,
            doc_name=doc_name,
            doc_url=doc_url,
            correlation_id=f"manual-{datetime.now(UTC).timestamp()}"
        )
        
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


@router.get("/metrics")
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


@router.get("/status")
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


@router.get("/debug/queue")
async def debug_queue_messages(
    worker: DownloadWorker = Depends(get_worker)
) -> Dict[str, Any]:
    """Debug endpoint to inspect queue message format."""
    try:
        # Peek at messages without deleting them
        messages = await worker.input_queue.receive_messages(max_messages=3)
        
        message_samples = []
        for msg in messages:
            try:
                body = json.loads(msg["Body"])
                message_samples.append({
                    "message_id": msg.get("MessageId"),
                    "body_keys": list(body.keys()),
                    "body_sample": body if len(str(body)) < 1000 else "Too large to display",
                    "attributes": msg.get("Attributes", {})
                })
            except Exception as e:
                message_samples.append({
                    "error": f"Failed to parse: {e}",
                    "raw_body": msg.get("Body", "")[:500]  # First 500 chars
                })
        
        return {
            "queue_name": worker.input_queue.queue_name,
            "message_count": len(messages),
            "samples": message_samples,
            "timestamp": datetime.now(UTC).isoformat()
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "queue_name": worker.input_queue.queue_name,
            "timestamp": datetime.now(UTC).isoformat()
        }