# services/document-downloader/src/main.py
import asyncio
import signal
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from loguru import logger

from config import DocumentConfig
from api.routes import router as routes
from api.health import router as health
from core.downloader import DocumentDownloader
from services.worker import DownloadWorker
from integrations.forth_api import ForthAPIClient
from forth_shared.utils.logging import setup_logging
from forth_shared.adapters.storage import S3Adapter


# Global shutdown event
shutdown_event = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info(f"🚀 Starting {config.service_name} v{config.service_version}")
    
    # Create temp directory
    Path(config.temp_dir).mkdir(parents=True, exist_ok=True)
    
    # Initialize Forth API client
    forth_client = None
    if config.forth_api_base_url and config.forth_api_key:
        forth_client = ForthAPIClient(
            base_url=config.forth_api_base_url,
            api_key=config.forth_api_key,
            timeout=config.forth_api_timeout
        )
        await forth_client.initialize()
    
    # Initialize S3 adapter
    s3_adapter = S3Adapter(
        bucket_name=config.s3_bucket_name,
        region=config.aws_region,
        endpoint_url=config.get_aws_endpoint_url() if hasattr(config, 'get_aws_endpoint_url') else None
    )
    
    # Initialize downloader
    downloader = DocumentDownloader(config, forth_client, s3_adapter)
    
    # Initialize worker
    worker = DownloadWorker(config, downloader)
    
    # Store in app state
    app.state.downloader = downloader
    app.state.worker = worker
    app.state.config = config
    
    # Start worker in background
    worker_task = asyncio.create_task(worker.run())
    
    yield
    
    # Shutdown
    logger.info(f"🛑 Shutting down {config.service_name}")
    shutdown_event.set()
    
    # Stop worker
    await worker.stop()
    worker_task.cancel()
    
    # Cleanup
    if forth_client:
        await forth_client.close()
    
    # Clean temp directory
    temp_dir = Path(config.temp_dir)
    for file in temp_dir.glob("*"):
        try:
            file.unlink()
        except Exception as e:
            logger.warning(f"Failed to clean temp file {file}: {e}")


# Initialize configuration
config = DocumentConfig()

# Setup logging - use human-readable format for development
log_format = "human" if config.is_development() else "json"
setup_logging(
    service_name=config.service_name,
    log_level=config.log_level,
    log_format=log_format
)

# Create FastAPI app
app = FastAPI(
    title=f"{config.service_name} API",
    version=config.service_version,
    lifespan=lifespan
)

# Include routers
app.include_router(routes)
app.include_router(health)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=config.is_development()
    )