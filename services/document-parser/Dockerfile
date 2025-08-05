# services/document-parser/Dockerfile
FROM python:3.11-slim

# Set build arguments for metadata
ARG BUILD_DATE
ARG VERSION=latest
ARG SERVICE_NAME=document-parser

# Add metadata labels
LABEL maintainer="AI Underwriter Team"
LABEL org.opencontainers.image.title="AI Underwriter Document Parser Service"
LABEL org.opencontainers.image.description="AI-powered document extraction and validation service using Gemini"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL org.opencontainers.image.source="https://bitbucket.org/wuduh/ai-underwriter"

WORKDIR /app

# Note: This Dockerfile should be built from the root directory:
# docker build -f services/document-parser/Dockerfile .

# Install system dependencies with security updates
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    ca-certificates \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user early for security
RUN useradd -m -u 1001 -s /bin/bash parser \
    && mkdir -p /app/tmp /app/logs /app/temp \
    && chown -R parser:parser /app

# Copy and install shared library first (for better caching)
COPY --chown=parser:parser libs /app/libs
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -e /app/libs

# Copy service package files
COPY --chown=parser:parser services/document-parser/pyproject.toml /app/
COPY --chown=parser:parser services/document-parser/src /app/src

# Install service dependencies
RUN pip install --no-cache-dir -e . \
    && pip install --no-cache-dir gunicorn[gthread] \
    && pip cache purge

# Switch to non-root user
USER parser

# Set Python path and environment variables
ENV PYTHONPATH=/app:$PYTHONPATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONHASHSEED=random
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Production environment variables (override in deployment)
ENV PARSER_ENVIRONMENT=production
ENV PARSER_LOG_LEVEL=INFO
ENV PARSER_HOST=0.0.0.0
ENV PARSER_PORT=8003
ENV PARSER_WORKERS=4
ENV PARSER_MAX_REQUESTS=1000
ENV PARSER_MAX_REQUESTS_JITTER=100
ENV PARSER_TIMEOUT=60
ENV PARSER_KEEPALIVE=5

# Parser-specific configurations
ENV PARSER_WORKER_CONCURRENCY=5
ENV PARSER_PROCESSING_TIMEOUT=600
ENV PARSER_MAX_FILE_SIZE_MB=100
ENV PARSER_MAX_RETRIES=3
ENV PARSER_RETRY_DELAY=60

# Gemini API configurations
ENV PARSER_GEMINI_MODEL=gemini-2.0-flash
ENV PARSER_GEMINI_TEMPERATURE=0.1
ENV PARSER_GEMINI_TIMEOUT=300

# Create temporary directory for processing
RUN mkdir -p /app/temp && chmod 755 /app/temp

# Health check with retry logic
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8003/api/v1/health/live || exit 1

EXPOSE 8003

# Use Gunicorn for production with proper worker management
CMD gunicorn \
    --bind 0.0.0.0:8003 \
    --workers ${PARSER_WORKERS} \
    --worker-class uvicorn.workers.UvicornWorker \
    --max-requests ${PARSER_MAX_REQUESTS} \
    --max-requests-jitter ${PARSER_MAX_REQUESTS_JITTER} \
    --timeout ${PARSER_TIMEOUT} \
    --keep-alive ${PARSER_KEEPALIVE} \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    --preload \
    src.main:app