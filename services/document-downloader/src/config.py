# services/document-downloader/src/config.py
import os
from enum import Enum
from typing import Optional, Literal
from pydantic import Field, field_validator, model_validator, SecretStr
from pydantic_settings import SettingsConfigDict
from libs.forth_shared.config.base import BaseServiceConfig


class Environment(str, Enum):
    """Environment types for deployment."""
    DEVELOPMENT = "development"
    PRODUCTION = "production"

    
class DocumentConfig(BaseServiceConfig):
    """Document downloader service configuration."""
    
    model_config = SettingsConfigDict(
        env_prefix="DOCUMENT_",
        env_file=".env",  # Production-ready: rely on environment variables
        env_file_encoding='utf-8'
    )
    
    # Core service configuration
    service_name: Literal["document-downloader"] = Field(default="document-downloader")
    service_version: str = Field(default="1.0.0")
    
    # Environment configuration
    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Deployment environment"
    )
    
    # Server configuration
    host: str = Field(
        default="0.0.0.0",
        description="Server host"
    )
    
    port: int = Field(
        default=8002,
        description="Server port"
    )
    
    # Queue configuration
    uw_uploaded_docs_queue: str = Field(
        ...,
        description="Queue for document upload tasks"
    )
    uw_downloaded_docs_queue: Optional[str] = Field(
        default=None,
        description="Queue for download completion notifications"
    )
    # S3 configuration
    s3_bucket_name: str = Field(
        default="contact-contracts-dev-s3-us-west-1",
        description="S3 bucket for document storage"
    )
    s3_prefix: str = Field(
        default="contracts",
        description="S3 key prefix"
    )
    
    # Forth API configuration
    forth_api_base_url: Optional[str] = Field(
        default="https://api.forthcrm.com/v1",
        description="Forth API base URL"
    )
    forth_api_key: Optional[SecretStr] = Field(
        default=None,
        description="Forth API key (sensitive)"
    )
    forth_api_key_id: Optional[SecretStr] = Field(
        default=None,
        description="Forth API key ID (sensitive)"
    )
    forth_api_timeout: int = Field(
        default=30,
        description="API timeout in seconds"
    )
    
    # Worker configuration
    worker_concurrency: int = Field(
        default=10,
        description="Max concurrent downloads"
    )
    download_timeout: int = Field(
        default=60,
        description="Download timeout in seconds"
    )
    max_file_size_mb: int = Field(
        default=500,
        description="Maximum file size in MB"
    )
    temp_dir: str = Field(
        default="/tmp/downloads",
        description="Temporary download directory"
    )
    
    # Retry configuration
    max_retries: int = Field(
        default=3,
        description="Maximum retry attempts"
    )
    retry_delay: int = Field(
        default=60,
        description="Retry delay in seconds"
    )
    
    # Logging configuration
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Log level"
    )
    
    # Observability
    enable_metrics: bool = Field(
        default=True,
        description="Expose Prometheus metrics"
    )
    enable_tracing: bool = Field(
        default=True,
        description="Enable OpenTelemetry tracing"
    )
    
    # Validation
    @field_validator('log_level', mode='before')
    @classmethod
    def normalize_log_level(cls, v: str) -> str:
        """Normalize log level to uppercase for case-insensitive input."""
        return v.upper() if isinstance(v, str) else v
    
    @model_validator(mode='after')
    def validate_production_requirements(self) -> 'DocumentConfig':
        """Apply production-specific validation."""
        if self.environment == Environment.PRODUCTION:
            # Ensure reasonable worker limits in production
            if self.worker_concurrency > 50:
                raise ValueError("Production worker concurrency too high (maximum 50)")
            
            # Validate file size limits
            if self.max_file_size_mb > 1000:  # 1GB
                raise ValueError("Production file size limit too high (maximum 1000MB)")
            
            # Ensure secure configuration
            if not self.has_forth_api_credentials():
                raise ValueError("Production requires Forth API credentials")
            
            if not str(self.forth_api_base_url).startswith("https://"):
                raise ValueError("Production requires HTTPS for Forth API")
        
        return self
    
    @property
    def input_queue_name(self) -> str:
        """Get the input queue name for compatibility."""
        return self.uw_uploaded_docs_queue
    
    @property
    def output_queue_name(self) -> Optional[str]:
        """Get the output queue name for compatibility."""
        return self.uw_downloaded_docs_queue
    
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == Environment.DEVELOPMENT

    def get_forth_api_key(self) -> Optional[str]:
        """Safely get the Forth API key value."""
        return self.forth_api_key.get_secret_value() if self.forth_api_key else None
    
    def get_forth_api_key_id(self) -> Optional[str]:
        """Safely get the Forth API key ID value."""
        return self.forth_api_key_id.get_secret_value() if self.forth_api_key_id else None
    
    def has_forth_api_credentials(self) -> bool:
        """Check if Forth API credentials are configured (without exposing values)."""
        return self.forth_api_key is not None and self.forth_api_base_url is not None
    
    def get_max_file_size_bytes(self) -> int:
        """Get maximum file size in bytes."""
        return self.max_file_size_mb * 1024 * 1024

    # Utility methods
    def is_production_ready(self) -> bool:
        """Check if configuration is production-ready."""
        return (
            self.environment == Environment.PRODUCTION
            and hasattr(self, 'cors_origins') and "*" not in getattr(self, 'cors_origins', [])
            and str(self.forth_api_base_url).startswith("https://")
            and self.has_forth_api_credentials()
        )