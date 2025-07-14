# services/document-downloader/src/config.py
from typing import Optional, Literal
from pydantic import Field
from forth_shared.config.base import BaseServiceConfig


class DocumentConfig(BaseServiceConfig):
    """Document downloader service configuration."""
    
    service_name: Literal["document-downloader"] = Field(default="document-downloader")
    service_version: Literal["1.0.0"] = Field(default="1.0.0")
    
    # Override default port for document-downloader
    port: int = Field(default=8001, description="Server port", env="PORT")
    host: str = Field(default="0.0.0.0", description="Server host", env="HOST")
    
    # Queue configuration
    input_queue_name: str = Field(
        default="uw-contracts-parser-dev-sqs",
        description="Queue for download tasks",
        env="SQS_INPUT_QUEUE"
    )
    output_queue_name: Optional[str] = Field(
        default=None,
        description="Queue for parsing tasks (optional)",
        env="SQS_OUTPUT_QUEUE"
    )
    
    # S3 configuration
    s3_bucket_name: str = Field(
        default="contact-contracts-dev-s3-us-west-1",
        description="S3 bucket for document storage",
        env="AWS_S3_BUCKET_NAME"
    )
    s3_prefix: str = Field(
        default="contracts",
        description="S3 key prefix",
        env="S3_PREFIX"
    )
    
    # Forth API configuration
    forth_api_base_url: Optional[str] = Field(
        default="https://api.forthcrm.com/v1",
        description="Forth API base URL",
        env="FORTH_API_BASE_URL"
    )
    forth_api_key: Optional[str] = Field(
        default=None,
        description="Forth API key",
        env="FORTH_API_KEY"
    )
    forth_api_timeout: int = Field(
        default=30,
        description="API timeout in seconds",
        env="FORTH_API_TIMEOUT"
    )
    
    # Worker configuration
    worker_concurrency: int = Field(
        default=10,
        description="Max concurrent downloads",
        env="WORKER_CONCURRENCY"
    )
    download_timeout: int = Field(
        default=60,
        description="Download timeout in seconds",
        env="DOWNLOAD_TIMEOUT"
    )
    temp_dir: str = Field(
        default="/tmp/downloads",
        description="Temporary download directory",
        env="TEMP_DIR"
    )
    
    # Retry configuration
    max_retries: int = Field(
        default=3,
        description="Maximum retry attempts",
        env="MAX_RETRIES"
    )
    retry_delay: int = Field(
        default=60,
        description="Retry delay in seconds",
        env="RETRY_DELAY"
    )