# services/document-parser/src/api/dependencies.py
"""FastAPI dependencies for document-parser service."""

from functools import lru_cache
from typing import Dict, Any

from config import ServiceConfig
from core.processor import DocumentProcessor
from core.validator import UnderwritingValidator
from integrations.gemini import GeminiClient


@lru_cache()
def get_config() -> ServiceConfig:
    """Get service configuration."""
    from config import config
    return config


@lru_cache()
def get_gemini_client() -> GeminiClient:
    """Get Gemini client instance."""
    config = get_config()
    service_account_info = config.get_gemini_service_account_dict()
    return GeminiClient(service_account_info)


@lru_cache()
def get_document_processor() -> DocumentProcessor:
    """Get document processor instance."""
    gemini_client = get_gemini_client()
    return DocumentProcessor(gemini_client)


@lru_cache()
def get_underwriting_validator() -> UnderwritingValidator:
    """Get underwriting validator instance."""
    return UnderwritingValidator()


def get_service_info() -> Dict[str, Any]:
    """Get service information."""
    config = get_config()
    return {
        "service_name": config.service_name,
        "version": config.service_version,
        "environment": config.environment
    }