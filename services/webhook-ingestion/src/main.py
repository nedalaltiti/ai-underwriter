# services/webhook-ingestion/src/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from config import WebhookConfig
from api.routes import api_router, webhook_router
from api.dependencies import get_webhook_processor
from core.processor import WebhookProcessor
from libs.forth_shared.utils.logging import setup_logging
from libs.forth_shared.utils.monitoring import setup_metrics

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info(f"🚀 Starting {config.service_name} v{config.service_version}")
    
    # Initialize processor
    processor = WebhookProcessor(config)
    await processor.initialize()
    
    # Store in app state
    app.state.processor = processor
    app.state.config = config
    
    yield
    
    # Shutdown
    logger.info(f"🛑 Shutting down {config.service_name}")
    await processor.shutdown()


# Initialize configuration
config = WebhookConfig()

# Setup logging 
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
app.include_router(api_router)      # /api/v1/* endpoints
app.include_router(webhook_router)  # /webhook/* endpoints

# Root endpoint to prevent 404s from load balancer/monitoring
@app.get("/")
async def root():
    """Root endpoint for basic service identification."""
    return {
        "service": config.service_name,
        "version": config.service_version,
        "status": "running",
        "health_check": "/api/v1/health/",
        "webhook_endpoint": "/webhook/forth"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=config.is_development()
    )