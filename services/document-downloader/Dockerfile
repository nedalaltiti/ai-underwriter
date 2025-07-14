# services/document-downloader/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy shared library and install
COPY services/shared /app/shared
RUN pip install -e /app/shared

# Copy and install service dependencies
COPY services/document-downloader/pyproject.toml .
RUN pip install --no-cache-dir -e .

# Copy service code
COPY services/document-downloader/src /app/src

# Create temp directory
RUN mkdir -p /tmp/downloads

# Set environment variables
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8001/health || exit 1

# Run the service
CMD ["python", "src/main.py"]