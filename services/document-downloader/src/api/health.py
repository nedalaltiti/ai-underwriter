# services/document-downloader/src/api/health.py
from typing import Dict, Any
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_downloader, get_worker
from core.downloader import DocumentDownloader
from services.worker import DownloadWorker


router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check(
    downloader: DocumentDownloader = Depends(get_downloader)
) -> Dict[str, Any]:
    """Basic health check endpoint."""
    health_status = await downloader.health_check()
    
    if health_status["status"] == "unhealthy":
        raise HTTPException(status_code=503, detail=health_status)
    
    return {
        **health_status,
        "service": "document-downloader",
        "timestamp": datetime.now(UTC).isoformat()
    }


@router.get("/ready")
async def readiness_check(
    downloader: DocumentDownloader = Depends(get_downloader),
    worker: DownloadWorker = Depends(get_worker)
) -> Dict[str, Any]:
    """Readiness check for Kubernetes."""
    # Check if worker is running
    if not worker.running:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "reason": "Worker not running"}
        )
    
    # Check dependencies
    health_status = await downloader.health_check()
    
    if health_status["status"] == "unhealthy":
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": health_status["checks"]}
        )
    
    return {
        "status": "ready",
        "timestamp": datetime.now(UTC).isoformat()
    }


@router.get("/live")
async def liveness_check() -> Dict[str, Any]:
    """Liveness check for Kubernetes."""
    return {
        "status": "alive",
        "timestamp": datetime.now(UTC).isoformat()
    }