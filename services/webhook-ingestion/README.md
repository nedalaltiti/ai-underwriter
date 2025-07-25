# Webhook Ingestion Service

## Overview
FastAPI-based microservice that receives webhooks from Forth CRM and routes them to the document processing pipeline via AWS SQS.

## Features
- 🔐 **Security**: Rate limiting and HMAC signature verification
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

### Kubernetes Deployment
1. Create ConfigMaps and Secrets:
```bash
kubectl create configmap aws-config --from-literal=region=us-west-1
kubectl create configmap queue-config \
  --from-literal=uploaded-docs-queue=uw-uploaded-docs-prod.fifo \
  --from-literal=uploaded-docs-dlq=uw-uploaded-docs-prod-dlq.fifo

kubectl create secret generic webhook-secrets \
  --from-literal=webhook-secret=your-secret-here

kubectl create secret generic aws-credentials \
  --from-literal=access-key-id=YOUR_KEY \
  --from-literal=secret-access-key=YOUR_SECRET
```

2. Deploy:
```bash
kubectl apply -f services/webhook-ingestion/k8s-deployment.yaml
```

### Production Considerations

1. **Environment Variables**: In production, use Kubernetes ConfigMaps/Secrets or cloud provider secret management (AWS Secrets Manager, etc.)

2. **Shared Library**: The `libs/forth_shared` must be included in the Docker image. The Dockerfile handles this by copying from the root context.

3. **No .env Files**: Production deployments should NOT rely on .env files. All configuration must come from environment variables.

4. **Security**:
   - Run as non-root user (handled in Dockerfile)
   - Use read-only root filesystem
   - Enable network policies in Kubernetes
   - Use TLS for all external communication

5. **Monitoring**:
   - Export metrics to Prometheus
   - Send logs to centralized logging (ELK, CloudWatch)
   - Set up alerts for error rates and latency

## Troubleshooting

### Common Issues

1. **"Module not found: libs.forth_shared"**
   - Ensure you're installing from the root directory
   - Check PYTHONPATH includes the app directory

2. **"Failed to connect to SQS"**
   - Verify AWS credentials are set
   - Check the queue name ends with `.fifo` for FIFO queues
   - Ensure the AWS region is correct

3. **"Invalid webhook signature"**
   - Verify the webhook secret matches between sender and service
   - Check signature header name (X-Forth-Signature, X-Hub-Signature-256, etc.)

4. **Container fails health check**
   - Check logs: `docker logs webhook-ingestion`
   - Verify all required environment variables are set
   - Ensure the service can reach AWS SQS

## Development Workflow

1. Make changes to the code
2. Run tests: `pytest tests/`
3. Build locally: `docker build -f services/webhook-ingestion/Dockerfile .`
4. Test with docker-compose
5. Push changes and let CI/CD handle deployment

## Architecture Notes

- The service depends on `libs/forth_shared` for common functionality
- Uses AWS SQS FIFO queues for ordered message processing
- Implements circuit breaker pattern for external dependencies
- Supports horizontal scaling with proper rate limiting 