# services/webhook-ingestion/src/config.py
import os
import re
from enum import Enum
from typing import List, Union, Literal
from pydantic import Field, field_validator, model_validator, SecretStr, AnyHttpUrl
from pydantic_settings import SettingsConfigDict
from libs.forth_shared.config.base import BaseServiceConfig

# Compiled regex for CORS validation (avoid recompiling on every init)
CORS_ORIGIN_PATTERN = re.compile(r'^https?://[A-Za-z0-9\-._]+(:\d+)?$')


class Environment(str, Enum):
    """Environment types for deployment."""
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class WebhookConfig(BaseServiceConfig):
    """Webhook ingestion service configuration.""" 
    
    model_config = SettingsConfigDict(
        env_prefix="WEBHOOK_",
        env_file=".env",  
        env_file_encoding='utf-8'
    )
    
    # Core service configuration
    service_name: Literal["webhook-ingestion"] = Field(default="webhook-ingestion")
    service_version: str = Field(default="1.0.0")
    
    # Environment configuration
    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Deployment environment",
        env="ENVIRONMENT"
    )
    
    # Logging configuration
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Log level"
    )
    
    # Queue configuration
    uw_uploaded_docs_queue: str = Field(
        ...,
        description="Queue for document download tasks",
        env="UW_UPLOADED_DOCS_QUEUE"
    )

    # Dead Letter Queue
    uw_uploaded_docs_dlq: str = Field(
        ...,
        description="Dead letter queue name",
        env="UW_UPLOADED_DOCS_DLQ" 
    )
    
    # Security Configuration
    webhook_cors_origins: str = Field(
        default="http://localhost:3000",
        description="CORS allowed origins (comma-separated)"
    )
    
    @property
    def cors_origins(self) -> List[str]:
        """Get CORS origins as a list."""
        if not self.webhook_cors_origins:
            return []
        return [origin.strip() for origin in self.webhook_cors_origins.split(",") if origin.strip()]
    
    webhook_secret: SecretStr = Field(
        ...,
        min_length=32,
        description="Webhook signature secret (≥32 characters) - REQUIRED for authentication"
    )
    
    @field_validator('webhook_secret')
    @classmethod
    def validate_webhook_secret(cls, v):
        """Ensure webhook secret is provided and meets minimum requirements."""
        if not v or len(v.get_secret_value()) < 32:
            raise ValueError("Webhook secret must be at least 32 characters long")
        return v
    
    # Rate Limiting
    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting"
    )
    
    rate_limit_requests: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Maximum requests per time window (ignored if rate_limit_enabled=False)"
    )
    
    rate_limit_period: int = Field(
        default=60,
        ge=1,
        le=3600,
        description="Rate limit time window in seconds (ignored if rate_limit_enabled=False)"
    )
    
    # Webhook endpoint configuration
    webhook_endpoint: str = Field(
        default="/webhook/forth-docs",
        description="Webhook endpoint path"
    )
    
    webhook_timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Webhook timeout in seconds"
    )
    
    # observability
    enable_metrics: bool = Field(
        default=True,
        description="Expose Prometheus metrics"
    )
    enable_tracing: bool = Field(
        default=True,
        description="Enable OpenTelemetry tracing"
    )
    trace_sample_rate: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="OpenTelemetry trace sample rate (ignored if enable_tracing=False)"
    )
    
    # Server configuration for uvicorn
    host: str = Field(
        default="0.0.0.0",
        description="Server host",
        env="HOST"
    )
    
    port: int = Field(
        default=8001,
        description="Server port", 
        env="PORT"
    )

    # Validation
    @field_validator('log_level', mode='before')
    @classmethod
    def normalize_log_level(cls, v: str) -> str:
        """Normalize log level to uppercase for case-insensitive input."""
        return v.upper() if isinstance(v, str) else v
    
    @field_validator('webhook_cors_origins', mode='before')
    @classmethod
    def validate_cors_origins_string(cls, v: str) -> str:
        """Validate CORS origins string format."""
        if not v:
            return v
            
        # Parse and validate each origin
        origins = [origin.strip() for origin in v.split(",") if origin.strip()]
        for origin in origins:
            if origin != "*" and not CORS_ORIGIN_PATTERN.match(origin):
                raise ValueError(f"Invalid CORS origin format: {origin}")
        
        return v


    # Environment-specific validation
    @model_validator(mode='after')
    def validate_production_requirements(self) -> 'WebhookConfig':
        """Apply production-specific validation."""
        if self.environment == Environment.PRODUCTION:
            # Check for wildcard CORS in production
            if "*" in self.cors_origins:
                raise ValueError("Wildcard CORS origin not allowed in production")
            
            # Ensure reasonable rate limits in production
            if self.rate_limit_requests < 10:
                raise ValueError("Production rate limit too low (minimum 10)")
        
        return self
    

    
    @property
    def output_queue_name(self) -> str:
        """Get the output queue name for compatibility with processor."""
        return self.uw_uploaded_docs_queue
    
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == Environment.DEVELOPMENT