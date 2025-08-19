# services/document-parser/src/combined_main.py
"""Combined API + Worker main entry point."""

import asyncio
import threading
import warnings
from contextlib import asynccontextmanager

# Suppress Pydantic v2 deprecation warnings for cleaner logs
warnings.filterwarnings("ignore", message="Valid config keys have changed in V2")

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.health import router as health_router
from api.routes import router as api_router
from config import config
from services.worker import DocumentProcessor


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - starts worker alongside API."""
    
    # Start the worker in background
    worker = DocumentProcessor()
    worker_task = asyncio.create_task(worker.start())
    
    try:
        yield
    finally:
        # Cleanup: stop worker gracefully
        worker.stop()
        try:
            await asyncio.wait_for(worker_task, timeout=30.0)
        except asyncio.TimeoutError:
            worker_task.cancel()


def create_app() -> FastAPI:
    """Create and configure FastAPI application with embedded worker."""
    
    app = FastAPI(
        title="Document Parser Service (Combined)",
        description="AI-powered document extraction with embedded worker",
        version=config.service_version,
        lifespan=lifespan,  # This starts the worker
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json"
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(health_router, prefix="/api/v1/health", tags=["health"])
    app.include_router(api_router, prefix="/api/v1", tags=["api"])
    
    @app.get("/")
    async def root():
        return {
            "service": "document-parser-combined",
            "version": config.service_version,
            "environment": config.environment,
            "status": "running",
            "components": ["api", "worker"],
            "docs_url": "/docs"
        }
    
    return app


# Create the app
app = create_app()


def main():
    """Main entry point for combined service."""
    uvicorn.run(
        "combined_main:app",
        host=config.host,
        port=config.port,
        workers=1,  # Must be 1 for combined approach
        log_level=config.log_level.lower(),
        access_log=True,
        reload=False
    )


if __name__ == "__main__":
    main()
