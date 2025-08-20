# services/document-parser/src/main.py
"""Main FastAPI application for document-parser service."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from api.health import router as health_router
from api.routes import router as api_router
from config import config
from libs.forth_shared.utils.logging import setup_logging

# Setup logging first
setup_logging(
    service_name=config.service_name,
    log_level=config.log_level,
    log_format="human" if config.is_development() else "json"
)


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
    
    worker = None
    worker_task = None
    
    try:
        from services.worker import DocumentWorker
        worker = DocumentWorker()
        
        # Start worker in background task
        import asyncio
        worker_task = asyncio.create_task(worker.start())
        
        await asyncio.sleep(5 if config.is_production() else 2)
        
        logger.bind(
            service=config.service_name,
            module="main"
        ).info("service.ready api=true worker=true")
        
    except Exception as e:
        logger.bind(
            service=config.service_name,
            error=type(e).__name__
        ).error("worker.startup_failed")
        if not config.is_production():
            raise
        logger.bind(service=config.service_name).warning("service.ready api=true worker=false")
    
    try:
        yield
    finally:
        # Graceful shutdown
        logger.bind(service=config.service_name).info("service.shutdown graceful=true")
        
        if worker:
            worker.stop()
            
        if worker_task:
            try:
                await asyncio.wait_for(worker_task, timeout=config.graceful_shutdown_timeout)
                logger.bind(service=config.service_name).info("service.stopped worker=graceful api=graceful")
            except asyncio.TimeoutError:
                logger.bind(service=config.service_name).warning("service.stopped worker=timeout api=graceful")
                worker_task.cancel()
                try:
                    await worker_task
                except asyncio.CancelledError:
                    pass


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