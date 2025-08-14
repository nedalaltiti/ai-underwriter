# services/document-parser/Dockerfile
# Production-ready Dockerfile for document-parser service

FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set work directory
WORKDIR /app

# First install shared dependencies
COPY libs /app/libs
WORKDIR /app/libs
RUN pip install --no-cache-dir --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -e .

# Then install document-parser specific dependencies
WORKDIR /app
COPY services/document-parser/pyproject.toml services/document-parser/README.md ./
RUN mkdir -p src
RUN pip install --no-cache-dir -e .

# Copy application code
COPY services/document-parser/src/ ./src/
COPY services/document-parser/run-dev.sh services/document-parser/run-worker.sh ./

# Create logs directory
RUN mkdir -p logs && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8003/api/v1/health/live || exit 1

# Default command (can be overridden)
CMD ["python3", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8003"]