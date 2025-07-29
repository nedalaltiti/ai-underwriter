# shared/forth_shared/adapters/__init__.py
"""Adapters for external services and storage."""

from .queue import QueueAdapter, SQSAdapter
from .storage import S3Adapter, LocalStorageAdapter

__all__ = [
    "QueueAdapter",
    "SQSAdapter",
    "S3Adapter",
    "LocalStorageAdapter"
]