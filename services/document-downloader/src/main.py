# services/document-downloader/src/main.py
import asyncio
import time
import gc
import multiprocessing
import warnings
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
from integrations.forth_auth import ForthAuthManager
from libs.forth_shared.utils.logging import setup_logging
from libs.forth_shared.utils.monitoring import setup_metrics
from libs.forth_shared.adapters.storage import S3Adapter
from typing import Optional

# Suppress multiprocessing semaphore leak warnings
warnings.filterwarnings("ignore", message=".*leaked semaphore objects.*", category=UserWarning)

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
    
    # Initialize Forth auth managers and API clients per source
    forth_clients = {}
    auth_managers = {}
    # Helper to init one source
    async def init_source(source_key: str, base_url: str, client_id: Optional[str], client_secret: Optional[str]):
        am = ForthAuthManager(
            config,
            base_url=base_url,
            client_id=client_id,
            client_secret=client_secret
        )
        await am.initialize()
        fc = ForthAPIClient(base_url=base_url, auth_manager=am, timeout=config.forth_api_timeout)
        await fc.initialize()
        auth_managers[source_key] = am
        forth_clients[source_key] = fc
        logger.info(f"Forth client initialized for {source_key}")

    shared_base = config.forth_api_base_url
    # CDR
    if shared_base and config.forth_cdr_client_id and config.forth_cdr_client_secret:
        await init_source("CDR", shared_base,
                          config.forth_cdr_client_id.get_secret_value(),
                          config.forth_cdr_client_secret.get_secret_value())

    # ASPIRE
    if shared_base and config.forth_aspire_client_id and config.forth_aspire_client_secret:
        await init_source("ASPIRE", shared_base,
                          config.forth_aspire_client_id.get_secret_value(),
                          config.forth_aspire_client_secret.get_secret_value())

    # RESYNC
    if shared_base and config.forth_resync_client_id and config.forth_resync_client_secret:
        await init_source("RESYNC", shared_base,
                          config.forth_resync_client_id.get_secret_value(),
                          config.forth_resync_client_secret.get_secret_value())
    
    # Initialize S3 adapter
    endpoint_url = None
    if hasattr(config, 'get_aws_endpoint_url') and callable(getattr(config, 'get_aws_endpoint_url')):
        endpoint_url = config.get_aws_endpoint_url()
    
    s3_adapter = S3Adapter(
        bucket_name=config.s3_bucket_name,
        region=config.aws_region,
        endpoint_url=endpoint_url
    )
    
    # Initialize downloader (pass map of clients)
    downloader = DocumentDownloader(config, forth_clients or None, s3_adapter)
    
    # Initialize worker
    worker = DownloadWorker(config, downloader)
    
    # Store in app state
    app.state.downloader = downloader
    app.state.worker = worker
    app.state.config = config
    app.state.auth_managers = auth_managers
    
    # Start worker in background
    worker_task = asyncio.create_task(worker.run())
    
    yield
    
    # Shutdown
    logger.info(f"🛑 Shutting down {config.service_name}")
    shutdown_event.set()
    
    # Stop worker
    await worker.stop()
    
    # Cancel and wait for worker task to complete
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    
    # Cleanup clients
    try:
        for fc in (forth_clients or {}).values():
            await fc.close()
    except Exception:
        pass
    try:
        for am in (auth_managers or {}).values():
            await am.close()
    except Exception:
        pass
    try:
        if hasattr(downloader, 'close'):
            await downloader.close()
    except Exception:
        pass
    
    # Give a moment for all async tasks to complete
    await asyncio.sleep(0.1)
    
    # Force garbage collection to clean up any remaining references
    gc.collect()
    
    # Additional cleanup for multiprocessing resources
    try:
        multiprocessing.active_children()  # This forces cleanup of zombie processes
        await asyncio.sleep(0.05)  # Brief pause for cleanup
    except Exception:
        pass
    
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

# Root endpoint to prevent 404s from load balancer/monitoring
@app.get("/")
async def root():
    """Root endpoint for basic service identification."""
    return {
        "service": config.service_name,
        "version": config.service_version,
        "status": "running",
        "health_check": "/api/v1/health/",
        "manual_download": "/api/v1/downloads/manual/{contact_id}/{doc_id}",
        "worker_status": "background_processing"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=config.is_development()
    )