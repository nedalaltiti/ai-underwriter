# services/webhook-ingestion/src/api/dependencies.py
from fastapi import Request


from core.processor import WebhookProcessor


def get_webhook_processor(request: Request) -> WebhookProcessor:
    """
    Get webhook processor instance from app state.
    
    This is a FastAPI dependency that retrieves the processor
    instance that was initialized during app startup.
    """
    return request.app.state.processor


def get_config(request: Request):
    """
    Get configuration from app state.
    
    This allows routes to access configuration if needed.
    """
    return request.app.state.config
