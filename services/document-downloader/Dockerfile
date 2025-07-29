# services/document-downloader/Dockerfile
FROM python:3.11-slim

# Set build arguments for metadata
ARG BUILD_DATE
ARG VERSION=latest
ARG SERVICE_NAME=document-downloader

# Add metadata labels
LABEL maintainer="AI Underwriter Team"
LABEL org.opencontainers.image.title="AI Underwriter Document Downloader Service"
LABEL org.opencontainers.image.description="Production document downloader service for processing documents from Forth CRM"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL org.opencontainers.image.source="https://bitbucket.org/wuduh/ai-underwriter"

WORKDIR /app

# Note: This Dockerfile should be built from the root directory:
# docker build -f services/document-downloader/Dockerfile .

# Install system dependencies with security updates
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    ca-certificates \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user early for security
RUN useradd -m -u 1001 -s /bin/bash downloader \
    && mkdir -p /app/tmp /app/logs /app/downloads \
    && chown -R downloader:downloader /app

# Copy and install shared library first (for better caching)
COPY --chown=downloader:downloader libs /app/libs
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -e /app/libs

# Copy service package files
COPY --chown=downloader:downloader services/document-downloader/pyproject.toml /app/
COPY --chown=downloader:downloader services/document-downloader/src /app/src

# Install service dependencies
RUN pip install --no-cache-dir -e . \
    && pip install --no-cache-dir gunicorn[gthread] \
    && pip cache purge

# Switch to non-root user
USER downloader

# Set Python path and environment variables
ENV PYTHONPATH=/app:$PYTHONPATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONHASHSEED=random
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Production environment variables (override in deployment)
ENV DOCUMENT_ENVIRONMENT=production
ENV DOCUMENT_LOG_LEVEL=INFO
ENV DOCUMENT_HOST=0.0.0.0
ENV DOCUMENT_PORT=8002
ENV DOCUMENT_WORKERS=4
ENV DOCUMENT_MAX_REQUESTS=1000
ENV DOCUMENT_MAX_REQUESTS_JITTER=100
ENV DOCUMENT_TIMEOUT=60
ENV DOCUMENT_KEEPALIVE=5

# Document-specific configurations
ENV DOCUMENT_WORKER_CONCURRENCY=10
ENV DOCUMENT_DOWNLOAD_TIMEOUT=60
ENV DOCUMENT_MAX_FILE_SIZE_MB=500
ENV DOCUMENT_TEMP_DIR=/app/downloads
ENV DOCUMENT_MAX_RETRIES=3
ENV DOCUMENT_RETRY_DELAY=60

# Create temporary directory for downloads
RUN mkdir -p /app/downloads && chmod 755 /app/downloads

# Health check with retry logic
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8002/api/v1/health/live || exit 1

EXPOSE 8002

# Use Gunicorn for production with proper worker management
CMD gunicorn \
    --bind 0.0.0.0:8002 \
    --workers ${DOCUMENT_WORKERS} \
    --worker-class uvicorn.workers.UvicornWorker \
    --max-requests ${DOCUMENT_MAX_REQUESTS} \
    --max-requests-jitter ${DOCUMENT_MAX_REQUESTS_JITTER} \
    --timeout ${DOCUMENT_TIMEOUT} \
    --keep-alive ${DOCUMENT_KEEPALIVE} \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    --preload \
    src.main:app