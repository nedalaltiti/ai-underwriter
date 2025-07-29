# shared/forth_shared/__init__.py
"""Forth Shared Library - Common utilities for AI underwriting services."""

__version__ = "1.0.0"
__author__ = "Nedal Altiti" 

from .models.queue import QueueMessage, MessageType
from .adapters.queue import QueueAdapter, SQSAdapter
from .adapters.storage import S3Adapter
from .config.base import BaseServiceConfig

__all__ = [
    "QueueMessage",
    "MessageType",
    "QueueAdapter",
    "SQSAdapter",
    "S3Adapter",
    "BaseServiceConfig",
]