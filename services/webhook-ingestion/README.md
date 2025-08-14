# Webhook Ingestion Service

## Overview
FastAPI-based microservice that receives webhooks from Forth CRM and routes them to the document processing pipeline via AWS SQS.

## Features
- 🔐 **Security**: Mandatory HMAC signature verification and rate limiting
- 📊 **Observability**: Structured logging, metrics, and health checks
- 🚀 **Performance**: Async processing with connection pooling
- 🏗️ **Production-Ready**: Docker, Kubernetes, and auto-scaling support

## Local Development

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- AWS credentials (for SQS access)

### Setup
```bash
# From the service directory
cd services/webhook-ingestion

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies (from root directory)
cd ../..
pip install -e libs/
pip install -e services/webhook-ingestion/

# Create .env file in service directory
cd services/webhook-ingestion
cp .env.example .env
# Edit .env with your configuration
```

### Running Locally

**Option 1: Using the development script (Recommended)**
```bash
# From root directory
cd services/webhook-ingestion
cp .env.example .env
# Edit .env with your actual values
./run-dev.sh
```

**Option 2: Manual setup**
```bash
# Load environment variables from .env file
cd services/webhook-ingestion
set -a && source .env && set +a

# Set Python path and run
cd src
export PYTHONPATH=/path/to/ai-underwriter:$PYTHONPATH
uvicorn main:app --reload --port 8001
```

### Running with Docker
```bash
# From root directory
docker-compose -f services/webhook-ingestion/docker-compose.yml up
```

## Configuration

### Environment Variables
All configuration uses the `WEBHOOK_` prefix:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `WEBHOOK_ENVIRONMENT` | Environment (development/production) | development | No |
| `WEBHOOK_LOG_LEVEL` | Log level | INFO | No |
| `WEBHOOK_AWS_REGION` | AWS region | us-west-1 | Yes |
| `WEBHOOK_UW_UPLOADED_DOCS_QUEUE` | SQS queue name | - | Yes |
| `WEBHOOK_UW_UPLOADED_DOCS_DLQ` | Dead letter queue name | - | Yes |
| `WEBHOOK_SECRET` | HMAC secret (min 32 chars) | - | Yes |
| `WEBHOOK_RATE_LIMIT_ENABLED` | Enable rate limiting | true | No |
| `WEBHOOK_RATE_LIMIT_REQUESTS` | Max requests per window | 100 | No |
| `WEBHOOK_RATE_LIMIT_PERIOD` | Rate limit window (seconds) | 60 | No |
| `WEBHOOK_CORS_ORIGINS` | Allowed CORS origins (comma-separated) | http://localhost:3000 | No |

## API Endpoints

### Webhook Endpoint
```bash
POST /webhook/forth
Content-Type: application/json
X-Forth-Signature: sha256=...

{
  "contact_id": "123456",
  "doc_id": "789012",
  "doc_name": "contract.pdf",
  "doc_type": "agreement"
}
```

### Health Checks
- `GET /api/v1/health` - Basic health check
- `GET /api/v1/health/detailed` - Comprehensive health check
- `GET /api/v1/health/live` - Kubernetes liveness probe
- `GET /api/v1/health/ready` - Kubernetes readiness probe
- `GET /api/v1/health/metrics` - Service metrics

## Deployment

### Building for Production
```bash
# From root directory
./services/webhook-ingestion/build.sh

# With version tag
VERSION=1.0.0 ./services/webhook-ingestion/build.sh

# Build and push to registry
PUSH=true DOCKER_REGISTRY=myregistry.com ./services/webhook-ingestion/build.sh
```

### Docker Deployment
The Dockerfile must be built from the **root directory** to include the shared `libs`:

```bash
# From root directory
docker build -f services/webhook-ingestion/Dockerfile -t webhook-ingestion .
```