# services/document-downloader/src/api/dependencies.py
from fastapi import Request
from typing import Optional

from core.downloader import DocumentDownloader
from services.worker import DownloadWorker
from integrations.forth_auth import ForthAuthManager
from config import DocumentConfig


def get_downloader(request: Request) -> DocumentDownloader:
    """Get downloader instance from app state."""
    return request.app.state.downloader


def get_worker(request: Request) -> DownloadWorker:
    """Get worker instance from app state."""
    return request.app.state.worker


def get_config(request: Request) -> DocumentConfig:
    """Get configuration from app state."""
    return request.app.state.config


def get_auth_manager(request: Request) -> Optional[ForthAuthManager]:
    """Get auth manager instance from app state."""
    return getattr(request.app.state, 'auth_manager', None)
