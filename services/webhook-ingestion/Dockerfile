# services/webhook-ingestion/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install shared library
COPY ../shared /app/shared
RUN pip install -e /app/shared

# Install main project dependencies  
COPY ../../pyproject.toml /app/pyproject.toml
RUN pip install -e .

# Copy service code
COPY src /app/src

CMD ["python", "src/main.py"]