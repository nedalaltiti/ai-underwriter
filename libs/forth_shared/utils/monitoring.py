# shared/forth_shared/utils/monitoring.py
from typing import Dict, Any, Optional, Callable
from functools import wraps
import time
from contextlib import asynccontextmanager
from prometheus_client import Counter, Histogram, Gauge, Info
from loguru import logger
import opentelemetry
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor


# Prometheus metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['service', 'method', 'endpoint', 'status']
)

REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['service', 'method', 'endpoint']
)

QUEUE_MESSAGE_COUNT = Counter(
    'queue_messages_total',
    'Total queue messages processed',
    ['service', 'queue', 'message_type', 'status']
)

QUEUE_PROCESSING_DURATION = Histogram(
    'queue_processing_duration_seconds',
    'Queue message processing duration',
    ['service', 'queue', 'message_type']
)

ACTIVE_TASKS = Gauge(
    'active_tasks',
    'Number of active tasks',
    ['service', 'task_type']
)

LLM_TOKEN_USAGE = Counter(
    'llm_tokens_total',
    'Total LLM tokens used',
    ['service', 'provider', 'model', 'token_type']
)

SERVICE_INFO = Info(
    'service_info',
    'Service information'
)


class MetricsCollector:
    """Centralized metrics collection."""
    
    def __init__(self, service_name: str, version: str = "1.0.0"):
        self.service_name = service_name
        self.version = version
        
        # Set service info
        SERVICE_INFO.info({
            'service': service_name,
            'version': version,
        })
    
    def record_request(
        self,
        method: str,
        endpoint: str,
        status: int,
        duration: float
    ):
        """Record HTTP request metrics."""
        REQUEST_COUNT.labels(
            service=self.service_name,
            method=method,
            endpoint=endpoint,
            status=str(status)
        ).inc()
        
        REQUEST_DURATION.labels(
            service=self.service_name,
            method=method,
            endpoint=endpoint
        ).observe(duration)
    
    def record_queue_message(
        self,
        queue: str,
        message_type: str,
        status: str,
        duration: float
    ):
        """Record queue message processing metrics."""
        QUEUE_MESSAGE_COUNT.labels(
            service=self.service_name,
            queue=queue,
            message_type=message_type,
            status=status
        ).inc()
        
        QUEUE_PROCESSING_DURATION.labels(
            service=self.service_name,
            queue=queue,
            message_type=message_type
        ).observe(duration)
    
    @asynccontextmanager
    async def track_active_task(self, task_type: str):
        """Context manager to track active tasks."""
        ACTIVE_TASKS.labels(
            service=self.service_name,
            task_type=task_type
        ).inc()
        
        try:
            yield
        finally:
            ACTIVE_TASKS.labels(
                service=self.service_name,
                task_type=task_type
            ).dec()
    
    def record_llm_usage(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int
    ):
        """Record LLM token usage."""
        LLM_TOKEN_USAGE.labels(
            service=self.service_name,
            provider=provider,
            model=model,
            token_type="prompt"
        ).inc(prompt_tokens)
        
        LLM_TOKEN_USAGE.labels(
            service=self.service_name,
            provider=provider,
            model=model,
            token_type="completion"
        ).inc(completion_tokens)


def setup_metrics(app, service_name: str):
    """Setup Prometheus metrics for FastAPI app."""
    from prometheus_client import make_asgi_app
    
    # Create metrics app
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)
    
    # Initialize collector
    collector = MetricsCollector(service_name)
    app.state.metrics = collector
    
    # Add middleware to track requests
    @app.middleware("http")
    async def track_requests(request, call_next):
        start_time = time.time()
        
        response = await call_next(request)
        
        duration = time.time() - start_time
        collector.record_request(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code,
            duration=duration
        )
        
        return response


def setup_tracing(
    service_name: str,
    otlp_endpoint: Optional[str] = None,
    sample_rate: float = 1.0
):
    """Setup OpenTelemetry tracing."""
    if not otlp_endpoint:
        return
    
    # Set up the tracer provider
    provider = TracerProvider()
    processor = BatchSpanProcessor(
        OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    )
    provider.add_span_processor(processor)
    
    # Set the global tracer provider
    trace.set_tracer_provider(provider)
    
    # Get a tracer
    return trace.get_tracer(service_name)


def trace_async(span_name: Optional[str] = None):
    """Decorator for tracing async functions."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = trace.get_tracer(__name__)
            name = span_name or f"{func.__module__}.{func.__name__}"
            
            with tracer.start_as_current_span(name) as span:
                # Add attributes
                span.set_attribute("function", func.__name__)
                
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(trace.Status(trace.StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(
                        trace.Status(trace.StatusCode.ERROR, str(e))
                    )
                    span.record_exception(e)
                    raise
        
        return wrapper
    return decorator