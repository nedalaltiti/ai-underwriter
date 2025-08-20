# services/document-parser/src/main.py
"""Main FastAPI application for document-parser service."""

import warnings
# Suppress Pydantic v2 deprecation warnings for cleaner logs
warnings.filterwarnings("ignore", message="Valid config keys have changed in V2")

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.health import router as health_router
from api.routes import router as api_router
from config import config
from utils.logging import setup_logging, get_logger

# Setup logging first
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.bind(
        service=config.service_name,
        version=config.service_version,
        environment=config.environment,
        gemini_model=config.gemini.model_name
    ).info("service.startup api=starting worker=starting")
    
    # Start the worker in background
    import asyncio
    from services.worker import DocumentWorker
    worker = DocumentWorker()
    worker_task = asyncio.create_task(worker.start())
    
    logger.bind(
        service=config.service_name,
        component="combined"
    ).info("service.ready api=true worker=true")
    
    try:
        yield
    finally:
        # Shutdown
        logger.bind(service=config.service_name).info("service.shutdown graceful=true")
        worker.stop()
        try:
            await asyncio.wait_for(worker_task, timeout=30.0)
            logger.bind(service=config.service_name).info("service.stopped worker=graceful api=graceful")
        except asyncio.TimeoutError:
            logger.bind(service=config.service_name).warning("service.stopped worker=timeout api=graceful")
            worker_task.cancel()


# Create FastAPI application
app = FastAPI(
    title="Document Parser Service",
    description="AI-powered document extraction and validation service for debt settlement contracts",
    version=config.service_version,
    lifespan=lifespan,
    docs_url="/docs" if config.is_development() else None,
    redoc_url="/redoc" if config.is_development() else None,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if config.is_development() else ["https://*.forthcrm.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Add routers
app.include_router(health_router)
app.include_router(api_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "document-parser",
        "version": config.service_version,
        "environment": config.environment,
        "status": "running",
        "docs_url": "/docs" if config.is_development() else "disabled"
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=config.is_development(),
        log_level=config.log_level.lower()
    )