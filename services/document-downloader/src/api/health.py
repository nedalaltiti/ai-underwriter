# services/document-downloader/src/api/health.py
"""
Comprehensive health check module for document downloader service.

Provides detailed health checks including dependency validation,
performance metrics, and operational status.
"""

import asyncio
import time
from datetime import datetime, UTC
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from pydantic import BaseModel, Field, ConfigDict

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from loguru import logger

from api.dependencies import get_downloader, get_worker, get_config
from core.downloader import DocumentDownloader
from services.worker import DownloadWorker
from libs.forth_shared.utils.tracing import generate_correlation_id


class HealthStatus(str, Enum):
    """Health status enumeration."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class CheckStatus(str, Enum):
    """Individual check status enumeration."""
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"


@dataclass
class HealthCheck:
    """Individual health check result."""
    name: str
    status: CheckStatus
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    duration_ms: Optional[int] = None
    last_updated: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        result = asdict(self)
        return {k: v for k, v in result.items() if v is not None}


class HealthResponse(BaseModel):
    """Standardized health check response model."""
    
    model_config = ConfigDict(
        extra='forbid',
        json_schema_extra={
            "examples": [
                {
                    "status": "healthy",
                    "service": "document-downloader",
                    "version": "1.0.0",
                    "timestamp": "2025-01-25T10:30:00Z",
                    "uptime_seconds": 3600,
                    "checks": {
                        "worker": {
                            "status": "pass",
                            "message": "Worker running with 10 concurrent tasks",
                            "duration_ms": 5
                        }
                    },
                    "metrics": {
                        "total_downloads": 1000,
                        "success_rate_percent": 99.5
                    }
                }
            ]
        }
    )
    
    status: HealthStatus = Field(..., description="Overall service health status")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    timestamp: str = Field(..., description="Health check timestamp (ISO 8601)")
    uptime_seconds: int = Field(..., description="Service uptime in seconds")
    
    checks: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Individual health check results"
    )
    
    metrics: Optional[Dict[str, Any]] = Field(
        None,
        description="Service metrics and performance data"
    )
    
    environment: Optional[str] = Field(
        None,
        description="Deployment environment"
    )
    
    build_info: Optional[Dict[str, str]] = Field(
        None,
        description="Build and deployment information"
    )


class HealthChecker:
    """Comprehensive health checker with multiple validation levels."""
    
    def __init__(self, downloader: DocumentDownloader, worker: DownloadWorker, config, start_time: Optional[float] = None):
        self.downloader = downloader
        self.worker = worker
        self.config = config
        self.start_time = start_time or time.time()
        
    async def perform_comprehensive_health_check(
        self,
        include_detailed_checks: bool = True,
        timeout_seconds: int = 30
    ) -> HealthResponse:
        """
        Perform comprehensive health check with configurable depth.
        
        Args:
            include_detailed_checks: Whether to include detailed dependency checks
            timeout_seconds: Maximum time to spend on health checks
            
        Returns:
            Comprehensive health response
        """
        start_time = time.perf_counter()
        correlation_id = generate_correlation_id("health")
        
        logger.bind(
            correlation_id=correlation_id,
            detailed_checks=include_detailed_checks
        ).debug("Starting comprehensive health check")
        
        try:
            # Collect all health checks
            checks = {}
            overall_status = HealthStatus.HEALTHY
            
            # Core health checks (always performed)
            core_checks = await asyncio.gather(
                self._check_worker_health(),
                self._check_downloader_health(),
                self._check_configuration(),
                return_exceptions=True
            )
            
            # Process core check results
            check_names = ["worker", "downloader", "configuration"]
            for i, result in enumerate(core_checks):
                if isinstance(result, Exception):
                    checks[check_names[i]] = HealthCheck(
                        name=check_names[i],
                        status=CheckStatus.FAIL,
                        message=f"Check failed: {str(result)}"
                    ).to_dict()
                    overall_status = HealthStatus.UNHEALTHY
                else:
                    checks[check_names[i]] = result.to_dict()
                    if result.status == CheckStatus.FAIL:
                        overall_status = HealthStatus.UNHEALTHY
                    elif result.status == CheckStatus.WARN and overall_status == HealthStatus.HEALTHY:
                        overall_status = HealthStatus.DEGRADED
            
            # Detailed checks (if requested and time permits)
            if include_detailed_checks:
                detailed_checks = await asyncio.wait_for(
                    asyncio.gather(
                        self._check_queue_connectivity(),
                        self._check_s3_connectivity(),
                        self._check_forth_api_connectivity(),
                        self._check_performance_metrics(),
                        return_exceptions=True
                    ),
                    timeout=max(1, timeout_seconds - int(time.perf_counter() - start_time))
                )
                
                detailed_names = ["queue", "s3", "forth_api", "performance"]
                for i, result in enumerate(detailed_checks):
                    if isinstance(result, Exception):
                        checks[detailed_names[i]] = HealthCheck(
                            name=detailed_names[i],
                            status=CheckStatus.WARN,
                            message=f"Detailed check timeout/error: {str(result)}"
                        ).to_dict()
                        if overall_status == HealthStatus.HEALTHY:
                            overall_status = HealthStatus.DEGRADED
                    else:
                        checks[detailed_names[i]] = result.to_dict()
                        if result.status == CheckStatus.FAIL:
                            overall_status = HealthStatus.UNHEALTHY
                        elif result.status == CheckStatus.WARN and overall_status == HealthStatus.HEALTHY:
                            overall_status = HealthStatus.DEGRADED
            
            # Collect metrics
            metrics = await self._collect_service_metrics()
            
            # Build response
            response = HealthResponse(
                status=overall_status,
                service=self.config.service_name,
                version=self.config.service_version,
                timestamp=datetime.now(UTC).isoformat(),
                uptime_seconds=int(time.time() - self.start_time),
                checks=checks,
                metrics=metrics,
                environment=self.config.environment.value,
                build_info=self._get_build_info()
            )
            
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            
            logger.bind(
                correlation_id=correlation_id,
                overall_status=overall_status.value,
                duration_ms=duration_ms,
                checks_count=len(checks)
            ).info(f"Health check completed: {overall_status.value}")
            
            return response
            
        except asyncio.TimeoutError:
            logger.bind(correlation_id=correlation_id).warning("Health check timed out")
            return HealthResponse(
                status=HealthStatus.UNKNOWN,
                service=self.config.service_name,
                version=self.config.service_version,
                timestamp=datetime.now(UTC).isoformat(),
                uptime_seconds=int(time.time() - self.start_time),
                checks={"timeout": {"status": "fail", "message": "Health check timed out"}}
            )
        except Exception as e:
            logger.bind(correlation_id=correlation_id).error(f"Health check failed: {e}")
            return HealthResponse(
                status=HealthStatus.UNHEALTHY,
                service=self.config.service_name,
                version=self.config.service_version,
                timestamp=datetime.now(UTC).isoformat(),
                uptime_seconds=int(time.time() - self.start_time),
                checks={"error": {"status": "fail", "message": str(e)}}
            )
    
    async def _check_worker_health(self) -> HealthCheck:
        """Check download worker health."""
        start_time = time.perf_counter()
        
        try:
            if not self.worker:
                return HealthCheck(
                    name="worker",
                    status=CheckStatus.FAIL,
                    message="Download worker not initialized"
                )
            
            if not self.worker.running:
                return HealthCheck(
                    name="worker",
                    status=CheckStatus.FAIL,
                    message="Download worker not running"
                )
            
            # Get worker stats
            active_downloads = self.worker.active_downloads
            max_concurrency = self.config.worker_concurrency
            
            # Check if worker is overloaded
            if active_downloads >= max_concurrency:
                status = CheckStatus.WARN
                message = f"Worker at capacity: {active_downloads}/{max_concurrency} downloads"
            else:
                status = CheckStatus.PASS
                message = f"Worker healthy: {active_downloads}/{max_concurrency} downloads"
            
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="worker",
                status=status,
                message=message,
                duration_ms=duration_ms,
                details={
                    "active_downloads": active_downloads,
                    "max_concurrency": max_concurrency,
                    "capacity_percent": round((active_downloads / max_concurrency) * 100, 2)
                }
            )
            
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="worker",
                status=CheckStatus.FAIL,
                message=f"Worker check failed: {str(e)}",
                duration_ms=duration_ms
            )
    
    async def _check_downloader_health(self) -> HealthCheck:
        """Check document downloader health."""
        start_time = time.perf_counter()
        
        try:
            if not self.downloader:
                return HealthCheck(
                    name="downloader",
                    status=CheckStatus.FAIL,
                    message="Document downloader not initialized"
                )
            
            # Check downloader components
            issues = []
            if not hasattr(self.downloader, 'forth_api'):
                issues.append("Forth API client not initialized")
            if not hasattr(self.downloader, 's3_client'):
                issues.append("S3 client not initialized")
            
            if issues:
                return HealthCheck(
                    name="downloader",
                    status=CheckStatus.WARN,
                    message=f"Downloader issues: {', '.join(issues)}"
                )
            
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="downloader",
                status=CheckStatus.PASS,
                message="Document downloader healthy",
                duration_ms=duration_ms
            )
            
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="downloader",
                status=CheckStatus.FAIL,
                message=f"Downloader check failed: {str(e)}",
                duration_ms=duration_ms
            )
    
    async def _check_configuration(self) -> HealthCheck:
        """Check service configuration."""
        start_time = time.perf_counter()
        
        try:
            # Check critical configuration
            issues = []
            
            if not self.config.uw_uploaded_docs_queue:
                issues.append("input queue not configured")
            
            if not self.config.s3_bucket_name:
                issues.append("S3 bucket not configured")
            
            if not self.config.forth_api_base_url:
                issues.append("Forth API URL not configured")
            
            if not self.config.forth_api_key:
                issues.append("Forth API key not configured")
            
            if self.config.worker_concurrency <= 0:
                issues.append("invalid worker concurrency")
            
            status = CheckStatus.FAIL if issues else CheckStatus.PASS
            message = f"Configuration issues: {', '.join(issues)}" if issues else "Configuration valid"
            
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="configuration",
                status=status,
                message=message,
                duration_ms=duration_ms,
                details={
                    "worker_concurrency": self.config.worker_concurrency,
                    "download_timeout": self.config.download_timeout,
                    "max_retries": self.config.max_retries,
                    "metrics_enabled": self.config.enable_metrics,
                    "tracing_enabled": self.config.enable_tracing
                }
            )
            
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="configuration",
                status=CheckStatus.FAIL,
                message=f"Configuration check failed: {str(e)}",
                duration_ms=duration_ms
            )
    
    async def _check_queue_connectivity(self) -> HealthCheck:
        """Check SQS queue connectivity."""
        start_time = time.perf_counter()
        
        try:
            # This would normally test actual queue connectivity
            # For now, just validate configuration
            queue_name = self.config.uw_uploaded_docs_queue
            
            if not queue_name:
                return HealthCheck(
                    name="queue",
                    status=CheckStatus.FAIL,
                    message="Queue not configured"
                )
            
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="queue",
                status=CheckStatus.PASS,
                message="Queue configuration valid",
                duration_ms=duration_ms,
                details={
                    "input_queue": queue_name,
                    "output_queue": self.config.uw_downloaded_docs_queue,
                    "region": self.config.aws_region
                }
            )
            
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="queue",
                status=CheckStatus.FAIL,
                message=f"Queue check failed: {str(e)}",
                duration_ms=duration_ms
            )
    
    async def _check_s3_connectivity(self) -> HealthCheck:
        """Check S3 connectivity."""
        start_time = time.perf_counter()
        
        try:
            bucket_name = self.config.s3_bucket_name
            
            if not bucket_name:
                return HealthCheck(
                    name="s3",
                    status=CheckStatus.FAIL,
                    message="S3 bucket not configured"
                )
            
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="s3",
                status=CheckStatus.PASS,
                message="S3 configuration valid",
                duration_ms=duration_ms,
                details={
                    "bucket": bucket_name,
                    "region": self.config.aws_region
                }
            )
            
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="s3",
                status=CheckStatus.FAIL,
                message=f"S3 check failed: {str(e)}",
                duration_ms=duration_ms
            )
    
    async def _check_forth_api_connectivity(self) -> HealthCheck:
        """Check Forth API connectivity."""
        start_time = time.perf_counter()
        
        try:
            if not self.config.forth_api_base_url:
                return HealthCheck(
                    name="forth_api",
                    status=CheckStatus.FAIL,
                    message="Forth API URL not configured"
                )
            
            if not self.config.forth_api_key:
                return HealthCheck(
                    name="forth_api",
                    status=CheckStatus.FAIL,
                    message="Forth API credentials not configured"
                )
            
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="forth_api",
                status=CheckStatus.PASS,
                message="Forth API configuration valid",
                duration_ms=duration_ms,
                details={
                    "base_url": self.config.forth_api_base_url,
                    "timeout": self.config.forth_api_timeout
                }
            )
            
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="forth_api",
                status=CheckStatus.FAIL,
                message=f"Forth API check failed: {str(e)}",
                duration_ms=duration_ms
            )
    
    async def _check_performance_metrics(self) -> HealthCheck:
        """Check performance metrics and thresholds."""
        start_time = time.perf_counter()
        
        try:
            metrics = self.downloader.get_metrics()
            
            # Calculate success rate
            total_downloads = metrics.get("total_downloads", 0)
            successful_downloads = metrics.get("successful_downloads", 0)
            success_rate = (successful_downloads / max(total_downloads, 1)) * 100
            
            # Check thresholds
            issues = []
            if success_rate < 95.0 and total_downloads > 10:
                issues.append(f"low success rate: {success_rate:.1f}%")
            
            avg_download_time = metrics.get("average_download_time_ms", 0)
            if avg_download_time > 10000:  # 10 seconds
                issues.append(f"high avg download time: {avg_download_time:.0f}ms")
            
            # Determine status
            if issues:
                status = CheckStatus.WARN
                message = f"Performance issues: {', '.join(issues)}"
            else:
                status = CheckStatus.PASS
                message = "Performance metrics healthy"
            
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="performance",
                status=status,
                message=message,
                duration_ms=duration_ms,
                details={
                    "success_rate_percent": round(success_rate, 2),
                    "average_download_time_ms": round(avg_download_time, 2),
                    "total_downloads": total_downloads,
                    "active_downloads": self.worker.active_downloads
                }
            )
            
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="performance",
                status=CheckStatus.WARN,
                message=f"Performance check failed: {str(e)}",
                duration_ms=duration_ms
            )
    
    async def _collect_service_metrics(self) -> Dict[str, Any]:
        """Collect comprehensive service metrics."""
        try:
            downloader_metrics = self.downloader.get_metrics()
            
            # Add calculated metrics
            total_downloads = downloader_metrics.get("total_downloads", 0)
            successful_downloads = downloader_metrics.get("successful_downloads", 0)
            
            if total_downloads > 0:
                downloader_metrics["success_rate_percent"] = round((successful_downloads / total_downloads) * 100, 2)
                downloader_metrics["error_rate_percent"] = round(((total_downloads - successful_downloads) / total_downloads) * 100, 2)
            else:
                downloader_metrics["success_rate_percent"] = 0
                downloader_metrics["error_rate_percent"] = 0
            
            # Add worker metrics
            downloader_metrics["active_downloads"] = self.worker.active_downloads
            downloader_metrics["worker_capacity_percent"] = round(
                (self.worker.active_downloads / self.config.worker_concurrency) * 100, 2
            )
            
            # Add uptime
            downloader_metrics["uptime_seconds"] = int(time.time() - self.start_time)
            
            return downloader_metrics
            
        except Exception as e:
            logger.error(f"Failed to collect metrics: {e}")
            return {"error": "Failed to collect metrics"}
    
    def _get_build_info(self) -> Dict[str, str]:
        """Get build and deployment information."""
        import sys
        return {
            "service": self.config.service_name,
            "version": self.config.service_version,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "framework": "FastAPI"
        }


# FastAPI Router
router = APIRouter(prefix="/health", tags=["Health"])


@router.get(
    "",
    response_model=HealthResponse,
    summary="Basic health check",
    description="Returns basic service health status with minimal checks"
)
async def health_check(
    request: Request,
    downloader: DocumentDownloader = Depends(get_downloader),
    worker: DownloadWorker = Depends(get_worker),
    config = Depends(get_config)
) -> JSONResponse:
    """Basic health check endpoint."""
    start_time = getattr(request.app.state, 'start_time', time.time())
    checker = HealthChecker(downloader, worker, config, start_time)
    health_response = await checker.perform_comprehensive_health_check(
        include_detailed_checks=False,
        timeout_seconds=5
    )
    
    # Return appropriate HTTP status code
    status_code = status.HTTP_200_OK
    if health_response.status == HealthStatus.UNHEALTHY:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif health_response.status == HealthStatus.DEGRADED:
        status_code = status.HTTP_200_OK  # Still operational
    elif health_response.status == HealthStatus.UNKNOWN:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    
    return JSONResponse(
        content=health_response.model_dump(),
        status_code=status_code
    )


@router.get(
    "/detailed",
    response_model=HealthResponse,
    summary="Detailed health check",
    description="Returns comprehensive health status with all dependency checks"
)
async def detailed_health_check(
    request: Request,
    downloader: DocumentDownloader = Depends(get_downloader),
    worker: DownloadWorker = Depends(get_worker),
    config = Depends(get_config)
) -> JSONResponse:
    """Detailed health check endpoint with comprehensive validation."""
    start_time = getattr(request.app.state, 'start_time', time.time())
    checker = HealthChecker(downloader, worker, config, start_time)
    health_response = await checker.perform_comprehensive_health_check(
        include_detailed_checks=True,
        timeout_seconds=30
    )
    
    # Return appropriate HTTP status code
    status_code = status.HTTP_200_OK
    if health_response.status == HealthStatus.UNHEALTHY:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif health_response.status == HealthStatus.DEGRADED:
        status_code = status.HTTP_200_OK
    elif health_response.status == HealthStatus.UNKNOWN:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    
    return JSONResponse(
        content=health_response.model_dump(),
        status_code=status_code
    )


@router.get(
    "/live",
    summary="Liveness probe",
    description="Kubernetes liveness probe - checks if service is alive"
)
async def liveness_probe() -> Dict[str, str]:
    """
    Liveness probe for Kubernetes.
    
    This should only check if the service process is alive and responsive.
    It should NOT check external dependencies.
    """
    return {
        "status": "alive",
        "timestamp": datetime.now(UTC).isoformat()
    }


@router.get(
    "/ready",
    summary="Readiness probe",
    description="Kubernetes readiness probe - checks if service is ready to accept traffic"
)
async def readiness_probe(
    downloader: DocumentDownloader = Depends(get_downloader),
    worker: DownloadWorker = Depends(get_worker)
) -> JSONResponse:
    """
    Readiness probe for Kubernetes.
    
    This checks if the service is ready to accept traffic by validating
    that critical dependencies are available.
    """
    try:
        # Quick check of critical components
        if not downloader or not worker:
            return JSONResponse(
                content={"status": "not_ready", "reason": "critical components not initialized"},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        
        if not worker.running:
            return JSONResponse(
                content={"status": "not_ready", "reason": "worker not running"},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        
        return JSONResponse(
            content={
                "status": "ready",
                "timestamp": datetime.now(UTC).isoformat()
            },
            status_code=status.HTTP_200_OK
        )
        
    except Exception as e:
        return JSONResponse(
            content={"status": "not_ready", "reason": str(e)},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )


@router.get(
    "/metrics",
    summary="Service metrics",
    description="Returns service performance metrics"
)
async def get_metrics(
    downloader: DocumentDownloader = Depends(get_downloader),
    worker: DownloadWorker = Depends(get_worker)
) -> Dict[str, Any]:
    """Get service metrics endpoint."""
    try:
        metrics = downloader.get_metrics()
        metrics["active_downloads"] = worker.active_downloads
        metrics["worker_running"] = worker.running
        metrics["timestamp"] = datetime.now(UTC).isoformat()
        return metrics
    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        return {"error": "Failed to retrieve metrics", "timestamp": datetime.now(UTC).isoformat()}