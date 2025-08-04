# services/document-parser/src/utils/metrics.py
"""Metrics tracking utilities."""

from datetime import datetime
from typing import Any, Dict, List
from dataclasses import dataclass

from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ProcessingMetric:
    """Individual processing metric."""
    timestamp: datetime
    success: bool
    latency_ms: int
    token_count: int
    document_id: str
    error_type: str = None


@dataclass
class ErrorMetric:
    """Error tracking metric."""
    timestamp: datetime
    error_type: str
    error_message: str
    context: Dict[str, Any]


class MetricsTracker:
    """Track extraction metrics for observability."""
    
    def __init__(self):
        self.processing_metrics: List[ProcessingMetric] = []
        self.error_metrics: List[ErrorMetric] = []
        self._start_time = datetime.now()
        
    def record_processing(
        self,
        success: bool,
        latency_ms: int,
        token_count: int,
        document_id: str,
        error_type: str = None
    ) -> None:
        """Record a processing event."""
        metric = ProcessingMetric(
            timestamp=datetime.now(),
            success=success,
            latency_ms=latency_ms,
            token_count=token_count,
            document_id=document_id,
            error_type=error_type
        )
        self.processing_metrics.append(metric)
        
        if len(self.processing_metrics) % 10 == 0:
            logger.info(f"Processed {len(self.processing_metrics)} documents so far")
    
    def record_error(self, error_type: str, error_message: str, context: Dict[str, Any]) -> None:
        """Record an error event."""
        metric = ErrorMetric(
            timestamp=datetime.now(),
            error_type=error_type,
            error_message=error_message,
            context=context
        )
        self.error_metrics.append(metric)
        logger.error(f"Error recorded: {error_type} - {error_message}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current metrics statistics."""
        if not self.processing_metrics:
            return {
                'total_processed': 0,
                'success_rate': 0.0,
                'avg_latency_ms': 0,
                'p95_latency_ms': 0,
                'total_errors': len(self.error_metrics),
                'uptime_seconds': (datetime.now() - self._start_time).total_seconds()
            }
        
        # Calculate success rate
        total_processed = len(self.processing_metrics)
        successful = sum(1 for m in self.processing_metrics if m.success)
        success_rate = successful / total_processed if total_processed > 0 else 0.0
        
        # Calculate latency stats
        latencies = [m.latency_ms for m in self.processing_metrics]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        
        # Calculate P95 latency
        if latencies:
            sorted_latencies = sorted(latencies)
            p95_index = int(len(sorted_latencies) * 0.95)
            p95_latency = sorted_latencies[p95_index] if p95_index < len(sorted_latencies) else sorted_latencies[-1]
        else:
            p95_latency = 0
        
        # Calculate token stats
        total_tokens = sum(m.token_count for m in self.processing_metrics)
        avg_tokens = total_tokens / total_processed if total_processed > 0 else 0
        
        return {
            'total_processed': total_processed,
            'successful': successful,
            'failed': total_processed - successful,
            'success_rate': success_rate,
            'avg_latency_ms': int(avg_latency),
            'p95_latency_ms': p95_latency,
            'total_tokens_used': total_tokens,
            'avg_tokens_per_doc': int(avg_tokens),
            'total_errors': len(self.error_metrics),
            'error_types': self._get_error_breakdown(),
            'uptime_seconds': (datetime.now() - self._start_time).total_seconds()
        }
    
    def _get_error_breakdown(self) -> Dict[str, int]:
        """Get breakdown of error types."""
        error_counts = {}
        for error in self.error_metrics:
            error_counts[error.error_type] = error_counts.get(error.error_type, 0) + 1
        return error_counts
    
    def get_recent_errors(self, limit: int = 10) -> List[ErrorMetric]:
        """Get recent error metrics."""
        return sorted(self.error_metrics, key=lambda x: x.timestamp, reverse=True)[:limit]
    
    def reset_metrics(self) -> None:
        """Reset all metrics (useful for testing)."""
        self.processing_metrics.clear()
        self.error_metrics.clear()
        self._start_time = datetime.now()
        logger.info("Metrics reset")


# Global metrics tracker instance
metrics_tracker = MetricsTracker()