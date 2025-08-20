# services/document-parser/Dockerfile
# Production-ready Dockerfile for document-parser service

# Build arguments for metadata and versioning
ARG BUILD_DATE
ARG VERSION=latest
ARG SERVICE_NAME=document-parser
ARG VCS_REF

# Base stage with common dependencies
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src:/app \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies with security updates
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libc6-dev \
    ca-certificates \
    && apt-get upgrade -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/* \
    && rm -rf /var/tmp/*

# Create non-root user with specific UID for security
RUN groupadd -r appuser --gid=1000 && \
    useradd -r -g appuser --uid=1000 --home-dir=/app --shell=/bin/bash appuser

# Dependencies stage
FROM base as dependencies

# Set work directory
WORKDIR /app

# Copy and install shared dependencies first (better caching)
COPY libs/pyproject.toml ./libs/
COPY libs/forth_shared ./libs/forth_shared/
WORKDIR /app/libs
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -e .

# Production stage
FROM dependencies as production

# Add metadata labels for container scanning and management
LABEL maintainer="GENAI Team <nedal.a@usclarity.com>" \
      org.opencontainers.image.title="Document Parser Service" \
      org.opencontainers.image.description="AI-powered document extraction and validation service" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.vendor="Forth CRM" \
      org.opencontainers.image.source="https://bitbucket.org/wuduh/ai-underwriter" \
      service.name="${SERVICE_NAME}" \
      service.version="${VERSION}"

# Copy application code and configuration
COPY --chown=appuser:appuser services/document-parser/src/ ./src/
COPY --chown=appuser:appuser services/document-parser/pyproject.toml ./
COPY --chown=appuser:appuser services/document-parser/README.md ./

# Install service-specific dependencies
RUN pip install --no-cache-dir -e .

# Create necessary directories with proper permissions
RUN mkdir -p /app/logs /app/tmp /tmp/document-parser && \
    chown -R appuser:appuser /app /tmp/document-parser && \
    chmod 755 /app/logs /app/tmp

# Switch to non-root user for security
USER appuser

# Expose port
EXPOSE 8003

# Health check that works in Kubernetes (uses container IP)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://127.0.0.1:8003/api/v1/health/live || exit 1

# Default command for API server (production-ready, no --reload)
CMD ["python3", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8003", "--workers", "1", "--access-log", "--log-level", "info"]