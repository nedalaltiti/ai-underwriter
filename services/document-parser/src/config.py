# services/document-parser/src/config.py
"""Configuration management for document-parser service."""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, SecretStr
from pydantic_settings import BaseSettings


class GeminiConfig(BaseModel):
    """Configuration for Gemini API."""
    project_id: str = Field(default="gemini-deployment", env="PARSER_GEMINI_PROJECT_ID")
    region: str = Field(default="us-central1", env="PARSER_GEMINI_REGION")
    model_name: str = Field(default="gemini-2.0-flash", env="PARSER_GEMINI_MODEL")
    temperature: float = Field(default=0.1, ge=0.0, le=2.0, env="PARSER_GEMINI_TEMPERATURE")
    top_k: int = Field(default=40, ge=1, le=100, env="PARSER_GEMINI_TOP_K")
    top_p: float = Field(default=0.95, ge=0.0, le=1.0, env="PARSER_GEMINI_TOP_P")
    max_output_tokens: int = Field(default=8192, ge=1, env="PARSER_GEMINI_MAX_TOKENS")
    timeout: int = Field(default=300, gt=0, env="PARSER_GEMINI_TIMEOUT")


class ServiceConfig(BaseSettings):
    """Main service configuration."""
    
    # Core service configuration
    environment: str = Field(default="production", env="PARSER_ENVIRONMENT")
    service_name: str = Field(default="document-parser", env="PARSER_SERVICE_NAME")
    service_version: str = Field(default="1.0.0", env="PARSER_SERVICE_VERSION")
    log_level: str = Field(default="INFO", env="PARSER_LOG_LEVEL")
    
    # Server configuration
    host: str = Field(default="0.0.0.0", env="PARSER_HOST")
    port: int = Field(default=8003, ge=1, le=65535, env="PARSER_PORT")
    workers: int = Field(default=1, ge=1, le=32, env="PARSER_WORKERS")
    max_requests: int = Field(default=1000, ge=1, env="PARSER_MAX_REQUESTS")
    max_requests_jitter: int = Field(default=100, ge=0, env="PARSER_MAX_REQUESTS_JITTER")
    timeout: int = Field(default=60, gt=0, env="PARSER_TIMEOUT")
    keepalive: int = Field(default=5, ge=2, env="PARSER_KEEPALIVE")
    
    # AWS Configuration
    aws_region: str = Field(default="us-west-1", env="PARSER_AWS_REGION")
    aws_endpoint_url: Optional[str] = Field(None, env="PARSER_AWS_ENDPOINT_URL")
    
    # SQS Configuration
    input_queue_name: str = Field(default="uw-downloaded-docs-dev-sqs.fifo", env="PARSER_INPUT_QUEUE_NAME")
    output_queue_name: Optional[str] = Field(None, env="PARSER_OUTPUT_QUEUE_NAME")
    sqs_wait_time: int = Field(default=20, ge=0, le=20, env="PARSER_SQS_WAIT_TIME")
    sqs_max_messages: int = Field(default=1, ge=1, le=10, env="PARSER_SQS_MAX_MESSAGES")  # One document per worker
    sqs_visibility_timeout: int = Field(default=900, ge=60, le=43200, env="PARSER_SQS_VISIBILITY_TIMEOUT") 
    
    # S3 Configuration
    s3_bucket_name: str = Field(default="uw-contact-files-dev-s3-us-west-1", env="PARSER_S3_BUCKET_NAME")
    s3_prefix: str = Field(default="", env="PARSER_S3_PREFIX")
    
    # Database Configuration (PostgreSQL)
    database_url: str = Field(..., env="PARSER_DATABASE_URL")
    database_pool_size: int = Field(default=10, ge=1, le=50, env="PARSER_DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=20, ge=0, le=100, env="PARSER_DATABASE_MAX_OVERFLOW")
    database_timeout: int = Field(default=30, ge=5, le=300, env="PARSER_DATABASE_TIMEOUT")
    database_retry_attempts: int = Field(default=3, ge=1, le=10, env="PARSER_DATABASE_RETRY_ATTEMPTS")
    
    # Gemini Configuration
    gemini_service_account_json: SecretStr = Field(..., env="PARSER_GEMINI_SERVICE_ACCOUNT")
    gemini: GeminiConfig = Field(default_factory=GeminiConfig)
    
    # Processing Configuration
    max_retries: int = Field(default=3, ge=1, le=10, env="PARSER_MAX_RETRIES")
    retry_delay: int = Field(default=60, ge=1, le=300, env="PARSER_RETRY_DELAY")
    processing_timeout: int = Field(default=600, gt=0, le=1800, env="PARSER_PROCESSING_TIMEOUT")
    max_file_size_mb: int = Field(default=100, ge=1, le=500, env="PARSER_MAX_FILE_SIZE_MB")
    
    # Security Configuration
    enable_request_validation: bool = Field(default=True, env="PARSER_ENABLE_REQUEST_VALIDATION")
    enable_response_validation: bool = Field(default=True, env="PARSER_ENABLE_RESPONSE_VALIDATION")
    max_concurrent_requests: int = Field(default=100, ge=1, le=1000, env="PARSER_MAX_CONCURRENT_REQUESTS")
    
    # Worker Configuration  
    worker_concurrency: int = Field(default=1, ge=1, le=50, env="PARSER_WORKER_CONCURRENCY")
    worker_prefetch_count: int = Field(default=1, ge=1, le=10, env="PARSER_WORKER_PREFETCH_COUNT")
    worker_health_check_interval: int = Field(default=30, ge=10, le=300, env="PARSER_WORKER_HEALTH_CHECK_INTERVAL")
    
    # Observability
    enable_metrics: bool = Field(default=True, env="PARSER_ENABLE_METRICS")
    enable_tracing: bool = Field(default=True, env="PARSER_ENABLE_TRACING")
    trace_sample_rate: float = Field(default=0.1, ge=0.0, le=1.0, env="PARSER_TRACE_SAMPLE_RATE")
    metrics_port: int = Field(default=9090, ge=1024, le=65535, env="PARSER_METRICS_PORT")
    
    # Production Configuration
    graceful_shutdown_timeout: int = Field(default=30, ge=5, le=120, env="PARSER_GRACEFUL_SHUTDOWN_TIMEOUT")
    health_check_timeout: int = Field(default=10, ge=1, le=60, env="PARSER_HEALTH_CHECK_TIMEOUT")
    rate_limit_per_minute: int = Field(default=1000, ge=1, le=10000, env="PARSER_RATE_LIMIT_PER_MINUTE")
    
    @field_validator('log_level')
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Invalid log level. Must be one of: {valid_levels}')
        return v.upper()
    
    @field_validator('environment')  
    def validate_environment(cls, v):
        valid_envs = ['development', 'staging', 'production']
        if v.lower() not in valid_envs:
            raise ValueError(f'Invalid environment. Must be one of: {valid_envs}')
        return v.lower()
    
    def get_gemini_service_account_dict(self) -> Dict[str, Any]:
        """Get Gemini service account as dictionary."""
        import json
        return json.loads(self.gemini_service_account_json.get_secret_value())
    
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"
    
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8", 
        "case_sensitive": False,
        "extra": "ignore",  # Ignore extra fields from environment
        "validate_assignment": True,
        "use_enum_values": True
    }


# Load environment variables explicitly
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

# Create configuration manually with environment variables
import os

def create_config() -> ServiceConfig:
    """Create configuration from environment variables with validation."""
    database_url = os.getenv('PARSER_DATABASE_URL')
    gemini_service_account = os.getenv('PARSER_GEMINI_SERVICE_ACCOUNT')
    worker_concurrency = int(os.getenv('PARSER_WORKER_CONCURRENCY', '1'))
    processing_timeout = int(os.getenv('PARSER_PROCESSING_TIMEOUT', '600'))
    
    if not database_url:
        raise ValueError("PARSER_DATABASE_URL environment variable is required")
    
    if not gemini_service_account:
        raise ValueError("PARSER_GEMINI_SERVICE_ACCOUNT environment variable is required")
    
    return ServiceConfig(
        database_url=database_url,
        gemini_service_account_json=gemini_service_account,
        worker_concurrency=worker_concurrency,
        processing_timeout=processing_timeout
    )

# Global configuration instance
config = create_config()