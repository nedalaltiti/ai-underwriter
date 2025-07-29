# services/webhook-ingestion/Dockerfile
FROM python:3.11-slim

# Set build arguments for metadata
ARG BUILD_DATE
ARG VERSION=latest
ARG SERVICE_NAME=webhook-ingestion

# Add metadata labels
LABEL maintainer="AI Underwriter Team"
LABEL org.opencontainers.image.title="AI Underwriter Webhook Ingestion Service"
LABEL org.opencontainers.image.description="Production webhook ingestion service for document processing pipeline"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL org.opencontainers.image.source="https://bitbucket.org/wuduh/ai-underwriter"

WORKDIR /app

# Note: This Dockerfile should be built from the root directory:
# docker build -f services/webhook-ingestion/Dockerfile .

# Install system dependencies with security updates
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    ca-certificates \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user early for security
RUN useradd -m -u 1000 -s /bin/bash webhook \
    && mkdir -p /app/tmp /app/logs \
    && chown -R webhook:webhook /app

# Copy and install shared library first (for better caching)
COPY --chown=webhook:webhook libs /app/libs
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -e /app/libs

# Copy service package files
COPY --chown=webhook:webhook services/webhook-ingestion/pyproject.toml /app/
COPY --chown=webhook:webhook services/webhook-ingestion/src /app/src

# Install service dependencies
RUN pip install --no-cache-dir -e . \
    && pip install --no-cache-dir gunicorn[gthread] \
    && pip cache purge

# Switch to non-root user
USER webhook

# Set Python path and environment variables
ENV PYTHONPATH=/app:$PYTHONPATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONHASHSEED=random
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Production environment variables (override in deployment)
ENV WEBHOOK_ENVIRONMENT=production
ENV WEBHOOK_LOG_LEVEL=INFO
ENV WEBHOOK_HOST=0.0.0.0
ENV WEBHOOK_PORT=8000
ENV WEBHOOK_WORKERS=4
ENV WEBHOOK_MAX_REQUESTS=1000
ENV WEBHOOK_MAX_REQUESTS_JITTER=100
ENV WEBHOOK_TIMEOUT=30
ENV WEBHOOK_KEEPALIVE=5

# Create temporary directory for uploads (if needed)
RUN mkdir -p /app/tmp

# Health check with retry logic
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/live || exit 1

EXPOSE 8000

# Use Gunicorn for production with proper worker management
CMD gunicorn \
    --bind 0.0.0.0:8000 \
    --workers ${WEBHOOK_WORKERS} \
    --worker-class uvicorn.workers.UvicornWorker \
    --max-requests ${WEBHOOK_MAX_REQUESTS} \
    --max-requests-jitter ${WEBHOOK_MAX_REQUESTS_JITTER} \
    --timeout ${WEBHOOK_TIMEOUT} \
    --keepalive ${WEBHOOK_KEEPALIVE} \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    --preload \
    src.main:app