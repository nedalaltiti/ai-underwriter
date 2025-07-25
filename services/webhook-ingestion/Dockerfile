# services/webhook-ingestion/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Note: This Dockerfile should be built from the root directory:
# docker build -f services/webhook-ingestion/Dockerfile .

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install shared library first (for better caching)
COPY libs /app/libs
RUN pip install --no-cache-dir -e /app/libs

# Copy service package files
COPY services/webhook-ingestion/pyproject.toml /app/
COPY services/webhook-ingestion/src /app/src

# Install service dependencies
RUN pip install --no-cache-dir -e .

# Create non-root user for security
RUN useradd -m -u 1000 webhook && chown -R webhook:webhook /app
USER webhook

# Set Python path and environment
ENV PYTHONPATH=/app:$PYTHONPATH
ENV PYTHONUNBUFFERED=1

# Production environment variables (these should be overridden in deployment)
ENV WEBHOOK_ENVIRONMENT=production
ENV WEBHOOK_LOG_LEVEL=INFO
ENV WEBHOOK_HOST=0.0.0.0
ENV WEBHOOK_PORT=8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/api/v1/health')"

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]