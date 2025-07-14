# services/document-downloader/src/api/dependencies.py
from fastapi import Request

from core.downloader import DocumentDownloader
from services.worker import DownloadWorker


def get_downloader(request: Request) -> DocumentDownloader:
    """Get downloader instance from app state."""
    return request.app.state.downloader


def get_worker(request: Request) -> DownloadWorker:
    """Get worker instance from app state."""
    return request.app.state.worker


def get_config(request: Request):
    """Get configuration from app state."""
    return request.app.state.config
