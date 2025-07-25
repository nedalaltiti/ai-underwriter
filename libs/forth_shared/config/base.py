# shared/forth_shared/config/base.py
from typing import Optional, Dict, Any
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
import os


class BaseServiceConfig(BaseSettings):
    """Base configuration for all services."""
    
    # Service identification
    service_name: str = Field(..., description="Service name")
    service_version: str = Field(default="1.0.0", description="Service version")
    environment: str = Field(default="development", description="Environment", env="ENVIRONMENT")
    
    # Server settings
    host: str = Field(default="0.0.0.0", description="Server host", env="HOST")
    port: int = Field(default=8000, description="Server port", env="PORT")
    debug: bool = Field(default=False, description="Debug mode", env="DEBUG")
    
    # Logging
    log_level: str = Field(default="INFO", description="Log level", env="LOG_LEVEL")
    log_format: str = Field(default="json", description="Log format")
    
    # AWS settings
    aws_region: str = Field(default="us-west-1", description="AWS region", env="AWS_REGION")
    aws_access_key_id: Optional[str] = Field(default=None, description="AWS access key", env="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(default=None, description="AWS secret key", env="AWS_SECRET_ACCESS_KEY")
    use_aws_secrets: bool = Field(default=True, description="Use AWS Secrets Manager", env="USE_AWS_SECRETS")
    
    # AWS Secrets
    aws_db_secret_name: Optional[str] = Field(default=None, description="AWS DB secret name", env="AWS_DB_SECRET_NAME")
    aws_gemini_secret_name: Optional[str] = Field(default=None, description="AWS Gemini secret name", env="AWS_GEMINI_SECRET_NAME")
    
    # Observability
    enable_metrics: bool = Field(default=True, description="Enable metrics")
    enable_tracing: bool = Field(default=True, description="Enable tracing")
    
    class Config:
        case_sensitive = False
        
    def __init__(self, **data):
        # Allow environment variable overrides
        for key, value in data.items():
            env_key = f"{self.service_name.upper()}_{key.upper()}"
            env_value = os.getenv(env_key)
            if env_value is not None:
                data[key] = env_value
                
        super().__init__(**data)

    def get_aws_endpoint_url(self) -> Optional[str]:
        """Get AWS endpoint URL for LocalStack or other local development."""
        if self.is_development():
            # Check for LocalStack endpoint
            endpoint = os.getenv("AWS_ENDPOINT_URL") or os.getenv("LOCALSTACK_ENDPOINT")
            if endpoint:
                return endpoint
            # Default LocalStack endpoint
            if os.getenv("USE_LOCALSTACK", "false").lower() == "true":
                return "http://localhost:4566"
        return None
    
    @field_validator('environment')
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment value."""
        allowed = {'development', 'staging', 'production'}
        if v not in allowed:
            raise ValueError(f"Environment must be one of {allowed}")
        return v
    
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == 'production'
    
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.environment == 'development'
    