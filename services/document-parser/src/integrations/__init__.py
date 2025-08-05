# services/document-parser/src/integrations/__init__.py
"""Integration modules for external services."""

from .gemini import GeminiClient
from .s3 import S3Client

__all__ = [
    "GeminiClient",
    "S3Client",
]