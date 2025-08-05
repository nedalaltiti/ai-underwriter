# services/document-parser/src/api/health.py
"""Health check endpoints for document-parser service."""

from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from http import HTTPStatus
from pydantic import BaseModel

from api.dependencies import get_config, get_gemini_client, get_service_info
from config import ServiceConfig
from integrations.gemini import GeminiClient
from utils.logging import get_logger
from utils.metrics import metrics_tracker

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/health", tags=["health"])


class HealthStatus(BaseModel):
    """Health status response model."""
    status: str
    timestamp: datetime
    service: Dict[str, Any]
    dependencies: Dict[str, Dict[str, Any]]
    metrics: Dict[str, Any]


class LivenessStatus(BaseModel):
    """Liveness check response model."""
    status: str
    timestamp: datetime


class ReadinessStatus(BaseModel):
    """Readiness check response model."""
    status: str
    timestamp: datetime
    ready: bool
    dependencies: Dict[str, bool]


@router.get("/live", response_model=LivenessStatus)
async def liveness_check():
    """
    Liveness probe endpoint.
    Returns 200 if the service is running.
    """
    return LivenessStatus(
        status="alive",
        timestamp=datetime.now()
    )


@router.get("/ready", response_model=ReadinessStatus)
async def readiness_check(
    config: ServiceConfig = Depends(get_config),
    gemini_client: GeminiClient = Depends(get_gemini_client)
):
    """
    Readiness probe endpoint.
    Returns 200 if the service is ready to handle requests.
    """
    dependencies = {}
    
    # Check Gemini API
    try:
        gemini_healthy = gemini_client.health_check()
        dependencies["gemini_api"] = gemini_healthy
        logger.debug(f"Gemini health check: {'passed' if gemini_healthy else 'failed'}")
    except Exception as e:
        logger.error(f"Gemini health check failed: {e}")
        dependencies["gemini_api"] = False
    
    # Check database connection (if configured)
    try:
        # TODO: Add database health check when implemented
        dependencies["database"] = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        dependencies["database"] = False
    
    # Check AWS services (SQS, S3) - basic connectivity
    dependencies["aws_services"] = True  # TODO: Implement AWS health checks
    
    # Overall readiness
    ready = all(dependencies.values())
    
    return ReadinessStatus(
        status="ready" if ready else "not_ready",
        timestamp=datetime.now(),
        ready=ready,
        dependencies=dependencies
    )


@router.get("/", response_model=HealthStatus)
async def health_check(
    config: ServiceConfig = Depends(get_config),
    service_info: Dict[str, Any] = Depends(get_service_info),
    gemini_client: GeminiClient = Depends(get_gemini_client)
):
    """
    Comprehensive health check endpoint.
    Returns detailed health information about the service.
    """
    dependencies = {}
    
    # Check Gemini API
    try:
        gemini_healthy = gemini_client.health_check()
        dependencies["gemini_api"] = {
            "status": "healthy" if gemini_healthy else "unhealthy",
            "model": config.gemini.model_name,
            "project_id": config.gemini.project_id,
            "region": config.gemini.region
        }
    except Exception as e:
        dependencies["gemini_api"] = {
            "status": "error",
            "error": str(e)
        }
    
    # Check configuration
    dependencies["configuration"] = {
        "status": "healthy",
        "environment": config.environment,
        "log_level": config.log_level,
        "workers": config.workers
    }
    
    # Check AWS configuration
    dependencies["aws"] = {
        "status": "configured",
        "region": config.aws_region,
        "input_queue": config.input_queue_name,
        "s3_bucket": config.s3_bucket_name
    }
    
    # Get metrics
    current_metrics = metrics_tracker.get_stats()
    
    return HealthStatus(
        status="healthy",
        timestamp=datetime.now(),
        service=service_info,
        dependencies=dependencies,
        metrics=current_metrics
    )


@router.get("/metrics")
async def get_metrics():
    """
    Get service metrics.
    Returns current performance and usage metrics.
    """
    return {
        "timestamp": datetime.now(),
        "metrics": metrics_tracker.get_stats(),
        "recent_errors": [
            {
                "timestamp": error.timestamp,
                "error_type": error.error_type,
                "error_message": error.error_message
            }
            for error in metrics_tracker.get_recent_errors(5)
        ]
    }