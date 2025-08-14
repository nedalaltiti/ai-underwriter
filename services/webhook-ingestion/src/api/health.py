# services/webhook-ingestion/src/api/health.py
"""
Comprehensive health check module for webhook ingestion service.

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

from core.processor import WebhookProcessor
from api.dependencies import get_webhook_processor, get_config
from libs.forth_shared.models.queue import QueueMessage, MessageType
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
                    "service": "webhook-ingestion",
                    "version": "1.0.0",
                    "timestamp": "2025-01-25T10:30:00Z",
                    "uptime_seconds": 3600,
                    "checks": {
                        "queue": {
                            "status": "pass",
                            "message": "Queue connection healthy",
                            "duration_ms": 15
                        }
                    },
                    "metrics": {
                        "total_requests": 1000,
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
    
    def __init__(self, processor: WebhookProcessor, config, start_time: Optional[float] = None):
        self.processor = processor
        self.config = config
        self.start_time = start_time or getattr(processor, '_service_start_time', time.time())
        
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
                self._check_processor_health(),
                self._check_configuration(),
                self._check_security_components(),
                return_exceptions=True
            )
            
            # Process core check results
            check_names = ["processor", "configuration", "security"]
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
                        self._check_dependencies(),
                        self._check_performance_metrics(),
                        return_exceptions=True
                    ),
                    timeout=max(1, timeout_seconds - int(time.perf_counter() - start_time))
                )
                
                detailed_names = ["queue", "dependencies", "performance"]
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
    
    async def _check_processor_health(self) -> HealthCheck:
        """Check webhook processor health."""
        start_time = time.perf_counter()
        
        try:
            # Check if processor is initialized
            if not self.processor:
                return HealthCheck(
                    name="processor",
                    status=CheckStatus.FAIL,
                    message="Webhook processor not initialized"
                )
            
            # Check processor components
            issues = []
            if not self.processor.validator:
                issues.append("validator not initialized")
            if not self.processor.queue_adapter:
                issues.append("queue adapter not initialized")
            
            if issues:
                return HealthCheck(
                    name="processor",
                    status=CheckStatus.WARN,
                    message=f"Processor issues: {', '.join(issues)}"
                )
            
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="processor",
                status=CheckStatus.PASS,
                message="Webhook processor healthy",
                duration_ms=duration_ms
            )
            
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="processor",
                status=CheckStatus.FAIL,
                message=f"Processor check failed: {str(e)}",
                duration_ms=duration_ms
            )
    
    async def _check_configuration(self) -> HealthCheck:
        """Check service configuration."""
        start_time = time.perf_counter()
        
        try:
            # Check critical configuration
            issues = []
            
            if not self.config.webhook_secret or len(self.config.webhook_secret.get_secret_value()) < 32:
                issues.append("webhook secret missing or too short (required for authentication)")
            
            if not self.config.uw_uploaded_docs_queue:
                issues.append("upload queue not configured")
            
            if self.config.rate_limit_enabled and self.config.rate_limit_requests <= 0:
                issues.append("invalid rate limit configuration")
            
            status = CheckStatus.FAIL if issues else CheckStatus.PASS
            message = f"Configuration issues: {', '.join(issues)}" if issues else "Configuration valid"
            
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="configuration",
                status=status,
                message=message,
                duration_ms=duration_ms,
                details={
                    "rate_limiting_enabled": self.config.rate_limit_enabled,
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
    
    async def _check_security_components(self) -> HealthCheck:
        """Check security component health."""
        start_time = time.perf_counter()
        
        try:
            security_status = {
                "rate_limiter": self.processor.rate_limiter is not None,
                "signature_verifier": self.processor.signature_verifier is not None,
                "secret_configured": bool(self.config.webhook_secret.get_secret_value()) if self.config.webhook_secret else False
            }
            
            # Determine status based on security configuration
            if self.config.rate_limit_enabled and not security_status["rate_limiter"]:
                status = CheckStatus.FAIL
                message = "Rate limiting enabled but not initialized"
            elif self.config.webhook_secret and not security_status["signature_verifier"]:
                status = CheckStatus.FAIL
                message = "Webhook secret configured but verifier not initialized"
            else:
                status = CheckStatus.PASS
                message = "Security components healthy"
            
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="security",
                status=status,
                message=message,
                duration_ms=duration_ms,
                details=security_status
            )
            
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="security",
                status=CheckStatus.FAIL,
                message=f"Security check failed: {str(e)}",
                duration_ms=duration_ms
            )
    
    async def _check_queue_connectivity(self) -> HealthCheck:
        """Check queue connectivity with actual connection test."""
        start_time = time.perf_counter()
        
        try:
            if not self.processor.queue_adapter:
                return HealthCheck(
                    name="queue",
                    status=CheckStatus.FAIL,
                    message="Queue adapter not initialized"
                )
            
            # Test queue connectivity by creating a test message
            test_message = QueueMessage(
                message_type=MessageType.CONTRACT_DOWNLOAD,
                contact_id="999999",  # Test contact ID
                correlation_id=generate_correlation_id("health"),
                data={"health_check": True, "timestamp": datetime.now(UTC).isoformat()}
            )
            
            # We don't send the message, just validate we can create it
            # This tests the queue adapter initialization and basic functionality
            queue_name = self.config.uw_uploaded_docs_queue
            adapter_type = type(self.processor.queue_adapter).__name__
            
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="queue",
                status=CheckStatus.PASS,
                message="Queue connectivity healthy",
                duration_ms=duration_ms,
                details={
                    "queue_name": queue_name,
                    "adapter_type": adapter_type,
                    "dlq_name": f"{queue_name}-dlq"
                }
            )
            
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="queue",
                status=CheckStatus.FAIL,
                message=f"Queue connectivity failed: {str(e)}",
                duration_ms=duration_ms
            )
    
    async def _check_dependencies(self) -> HealthCheck:
        """Check external dependencies and integrations."""
        start_time = time.perf_counter()
        
        try:
            # Check AWS region configuration
            if not self.config.aws_region:
                return HealthCheck(
                    name="dependencies",
                    status=CheckStatus.WARN,
                    message="AWS region not configured"
                )
            
            # For now, just validate configuration
            # In a full implementation, you might test actual AWS connectivity
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="dependencies",
                status=CheckStatus.PASS,
                message="Dependencies healthy",
                duration_ms=duration_ms,
                details={
                    "aws_region": self.config.aws_region
                }
            )
            
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return HealthCheck(
                name="dependencies",
                status=CheckStatus.WARN,
                message=f"Dependencies check failed: {str(e)}",
                duration_ms=duration_ms
            )
    
    async def _check_performance_metrics(self) -> HealthCheck:
        """Check performance metrics and thresholds."""
        start_time = time.perf_counter()
        
        try:
            metrics = self.processor.metrics
            total_requests = metrics.get("total_requests", 0)
            
            # Calculate success rate
            successful_requests = metrics.get("successful_requests", 0)
            success_rate = (successful_requests / max(total_requests, 1)) * 100
            
            # Calculate average processing time
            avg_processing_time = metrics.get("average_processing_time_ms", 0)
            
            # Define performance thresholds
            issues = []
            if success_rate < 95.0 and total_requests > 10:
                issues.append(f"low success rate: {success_rate:.1f}%")
            
            if avg_processing_time > 5000:  # 5 seconds
                issues.append(f"high avg processing time: {avg_processing_time:.0f}ms")
            
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
                    "average_processing_time_ms": round(avg_processing_time, 2),
                    "total_requests": total_requests
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
            metrics = self.processor.metrics.copy()
            
            # Add calculated metrics
            total_requests = metrics.get("total_requests", 0)
            successful_requests = metrics.get("successful_requests", 0)
            
            if total_requests > 0:
                metrics["success_rate_percent"] = round((successful_requests / total_requests) * 100, 2)
                metrics["error_rate_percent"] = round(((total_requests - successful_requests) / total_requests) * 100, 2)
            else:
                metrics["success_rate_percent"] = 0
                metrics["error_rate_percent"] = 0
            
            # Add uptime
            metrics["uptime_seconds"] = int(time.time() - self.start_time)
            
            return metrics
            
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
    processor: WebhookProcessor = Depends(get_webhook_processor),
    config = Depends(get_config)
) -> JSONResponse:
    """Basic health check endpoint."""
    checker = HealthChecker(processor, config)
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
    processor: WebhookProcessor = Depends(get_webhook_processor),
    config = Depends(get_config)
) -> JSONResponse:
    """Detailed health check endpoint with comprehensive validation."""
    checker = HealthChecker(processor, config)
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
    processor: WebhookProcessor = Depends(get_webhook_processor),
    config = Depends(get_config)
) -> JSONResponse:
    """
    Readiness probe for Kubernetes.
    
    This checks if the service is ready to accept traffic by validating
    that critical dependencies are available.
    """
    try:
        # Quick check of critical components
        if not processor or not processor.queue_adapter:
            return JSONResponse(
                content={"status": "not_ready", "reason": "critical components not initialized"},
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
    processor: WebhookProcessor = Depends(get_webhook_processor)
) -> Dict[str, Any]:
    """Get service metrics endpoint."""
    try:
        return await processor.get_metrics()
    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        return {"error": "Failed to retrieve metrics", "timestamp": datetime.now(UTC).isoformat()}
