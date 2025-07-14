# services/webhook-ingestion/src/config.py
from typing import List, Union, Literal
from pydantic import Field, field_validator
from forth_shared.config.base import BaseServiceConfig


class WebhookConfig(BaseServiceConfig):
    """Webhook ingestion service configuration."""
    
    service_name: Literal["webhook-ingestion"] = Field(default="webhook-ingestion")
    service_version: str = Field(default="1.0.0")
    
    # Queue configuration
    output_queue_name: str = Field(
        default="uw-contracts-parser-dev-sqs",
        description="Queue for document download tasks",
        env="SQS_MAIN_QUEUE"
    )
    
    # Security
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="CORS allowed origins",
        env="CORS_ORIGINS"
    )
    webhook_secret: str = Field(
        default="",
        description="Webhook signature secret",
        env="SECRET_KEY"
    )
    
    # Rate limiting
    rate_limit_enabled: bool = Field(default=True, env="WEBHOOK_RATE_LIMIT_ENABLED")
    rate_limit_requests: int = Field(default=100, env="WEBHOOK_RATE_LIMIT_REQUESTS")
    rate_limit_period: int = Field(default=60, env="WEBHOOK_RATE_LIMIT_PERIOD")
    
    # Forth API (for enrichment)
    forth_api_base_url: str = Field(
        default="https://api.forthcrm.com/v1", 
        description="Forth API URL",
        env="FORTH_API_BASE_URL"
    )
    forth_api_key: str = Field(
        default="", 
        description="Forth API key",
        env="FORTH_API_KEY"
    )
    forth_api_key_id: str = Field(
        default="", 
        description="Forth API key ID",
        env="FORTH_API_KEY_ID"
    )
    
    # S3 Configuration
    s3_bucket_name: str = Field(
        default="contact-contracts-dev-s3-us-west-1",
        description="S3 bucket for document storage",
        env="AWS_S3_BUCKET_NAME"
    )
    
    # Dead Letter Queue
    dlq_name: str = Field(
        default="uw-contracts-parser-dl-dev-sqs",
        description="Dead letter queue name",
        env="SQS_DLQ"
    )
    
    # Webhook endpoint configuration
    webhook_endpoint: str = Field(
        default="/webhook/forth-docs",
        description="Webhook endpoint path",
        env="WEBHOOK_ENDPOINT"
    )
    webhook_timeout: int = Field(
        default=30,
        description="Webhook timeout in seconds",
        env="WEBHOOK_TIMEOUT"
    )
    
    @field_validator('cors_origins', mode='before')
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        """Parse CORS origins from environment variable or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v or ["http://localhost:3000", "http://localhost:8000"]