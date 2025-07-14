# services/webhook-ingestion/src/__main__.py
"""
Entry point for running the webhook ingestion service as a module.

This allows running the service with:
    python -m services.webhook_ingestion.src
"""

import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    # Import and run the main application
    from main import app
    import uvicorn
    from config import WebhookConfig
    
    config = WebhookConfig()
    
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        reload=config.is_development(),
        log_level=config.log_level.lower()
    )
