# services/document-parser/src/__main__.py
"""Entry point for running the document-parser service."""

import sys
from pathlib import Path

# Add the src directory to Python path
src_path = Path(__file__).parent
sys.path.insert(0, str(src_path))

if __name__ == "__main__":
    from main import app
    import uvicorn
    from config import config
    
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        reload=config.is_development(),
        log_level=config.log_level.lower()
    )