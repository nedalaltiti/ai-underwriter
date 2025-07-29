# Document Downloader Service

## Overview
FastAPI-based microservice that downloads documents from Forth api based on messages received from the webhook-ingestion service via AWS SQS.

## Features
- 📥 **Async Downloads**: High-performance concurrent document downloads
- 🔄 **Retry Logic**: Automatic retries with exponential backoff
- 📊 **Observability**: Structured logging, metrics, and health checks
- 🏗️ **Production-Ready**: Docker, Kubernetes, and auto-scaling support

## Local Development

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- AWS credentials (for SQS and S3 access)

### Setup
```bash
# From the service directory
cd services/document-downloader

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies (from root directory)
cd ../..
pip install -e libs/
pip install -e services/document-downloader/

# Create .env file in service directory
cd services/document-downloader
cp .env.example .env
# Edit .env with your configuration
```

### Running Locally

**Option 1: Using the development script (Recommended)**
```bash
# From root directory
cd services/document-downloader
cp .env.example .env
# Edit .env with your actual values
./run-dev.sh
```

**Option 2: Manual setup**
```bash
# Load environment variables from .env file
cd services/document-downloader
set -a && source .env && set +a

# Set Python path and run
cd src
export PYTHONPATH=/path/to/ai-underwriter:$PYTHONPATH
uvicorn main:app --reload --port 8002
```

### Running with Docker
```bash
# From root directory
docker-compose -f services/document-downloader/docker-compose.yml up
```

## Configuration

### Environment Variables
All configuration uses the `DOCUMENT_` prefix:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DOCUMENT_ENVIRONMENT` | Environment (development/production) | development | No |
| `DOCUMENT_LOG_LEVEL` | Log level | INFO | No |
| `DOCUMENT_AWS_REGION` | AWS region | us-west-1 | Yes |
| `DOCUMENT_UW_UPLOADED_DOCS_QUEUE` | Input SQS queue name | - | Yes |
| `DOCUMENT_UW_DOWNLOADED_DOCS` | Output SQS queue name | - | No |
| `DOCUMENT_S3_BUCKET_NAME` | S3 bucket for document storage | - | Yes |
| `DOCUMENT_FORTH_API_BASE_URL` | Forth API base URL | - | Yes |
| `DOCUMENT_FORTH_API_KEY` | Forth API key | - | Yes |
| `DOCUMENT_FORTH_API_KEY_ID` | Forth API key ID | - | Yes |
| `DOCUMENT_FORTH_API_TIMEOUT` | API timeout (seconds) | 30 | No |
| `DOCUMENT_WORKER_CONCURRENCY` | Max concurrent downloads | 10 | No |
| `DOCUMENT_DOWNLOAD_TIMEOUT` | Download timeout (seconds) | 60 | No |
| `DOCUMENT_TEMP_DIR` | Temporary download directory | /tmp/downloads | No |
| `DOCUMENT_MAX_RETRIES` | Maximum retry attempts | 3 | No |
| `DOCUMENT_RETRY_DELAY` | Retry delay (seconds) | 60 | No |

## API Endpoints

### Health Checks
- `GET /api/v1/health` - Basic health check
- `GET /api/v1/health/detailed` - Comprehensive health check
- `GET /api/v1/health/live` - Kubernetes liveness probe
- `GET /api/v1/health/ready` - Kubernetes readiness probe
- `GET /api/v1/health/metrics` - Service metrics

### Download Management
- `GET /api/v1/downloads/status` - Current download status
- `GET /api/v1/downloads/metrics` - Download metrics

## Deployment

### Building for Production
```bash
# From root directory
./services/document-downloader/build.sh

# With version tag
VERSION=1.0.0 ./services/document-downloader/build.sh

# Build and push to registry
PUSH=true DOCKER_REGISTRY=myregistry.com ./services/document-downloader/build.sh
```

### Docker Deployment
The Dockerfile must be built from the **root directory** to include the shared `libs`:

```bash
# From root directory
docker build -f services/document-downloader/Dockerfile -t document-downloader .
```