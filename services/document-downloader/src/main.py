# services/document-downloader/src/main.py
import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from config import DocumentConfig
from api.routes import api_router
from api.health import router as health_router
from core.downloader import DocumentDownloader
from services.worker import DownloadWorker
from integrations.forth_api import ForthAPIClient
from libs.forth_shared.utils.logging import setup_logging
from libs.forth_shared.utils.monitoring import setup_metrics
from libs.forth_shared.adapters.storage import S3Adapter


# Global shutdown event
shutdown_event = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info(f"🚀 Starting {config.service_name} v{config.service_version}")
    
    # Store start time for health checks
    app.state.start_time = time.time()
    
    # Create temp directory
    Path(config.temp_dir).mkdir(parents=True, exist_ok=True)
    
    # Initialize Forth API client
    forth_client = None
    if config.has_forth_api_credentials():
        forth_client = ForthAPIClient(
            base_url=config.forth_api_base_url,
            api_key=config.get_forth_api_key(),
            timeout=config.forth_api_timeout
        )
        await forth_client.initialize()
        logger.info("Forth API client initialized successfully")
    
    # Initialize S3 adapter
    endpoint_url = None
    if hasattr(config, 'get_aws_endpoint_url') and callable(getattr(config, 'get_aws_endpoint_url')):
        endpoint_url = config.get_aws_endpoint_url()
    
    s3_adapter = S3Adapter(
        bucket_name=config.s3_bucket_name,
        region=config.aws_region,
        endpoint_url=endpoint_url
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

# Add CORS middleware
if hasattr(config, 'cors_origins') and config.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Setup metrics if enabled
if config.enable_metrics:
    setup_metrics(app, service_name=config.service_name)

# Include routers
app.include_router(api_router)       # /api/v1/* endpoints
app.include_router(health_router, prefix="/api/v1")  # /api/v1/health/* endpoints


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=config.is_development()
    )