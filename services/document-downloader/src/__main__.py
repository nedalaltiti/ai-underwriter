# services/document-downloader/src/__main__.py
"""
Entry point for running the document downloader service as a module.

This allows running the service with:
    python -m services.document_downloader.src
"""

import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    # Import and run the main application
    from main import app
    import uvicorn
    from config import DocumentConfig
    
    config = DocumentConfig()
    
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        reload=config.is_development(),
        log_level=config.log_level.lower()
    )
