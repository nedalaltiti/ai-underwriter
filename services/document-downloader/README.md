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

### Kubernetes Deployment
1. Create ConfigMaps and Secrets:
```bash
kubectl create configmap aws-config --from-literal=region=us-west-1
kubectl create configmap queue-config \
  --from-literal=uploaded-docs-queue=uw-uploaded-docs-prod.fifo \
  --from-literal=downloaded-docs-queue=uw-downloaded-docs-prod.fifo

kubectl create configmap s3-config \
  --from-literal=bucket-name=your-s3-bucket

kubectl create configmap forth-api-config \
  --from-literal=base-url=https://api.forth.com

kubectl create secret generic forth-api-secrets \
  --from-literal=api-key=your-api-key \
  --from-literal=api-key-id=your-api-key-id

kubectl create secret generic aws-credentials \
  --from-literal=access-key-id=YOUR_KEY \
  --from-literal=secret-access-key=YOUR_SECRET
```

2. Deploy:
```bash
kubectl apply -f services/document-downloader/k8s-deployment.yaml
```

### Production Considerations

1. **Environment Variables**: In production, use Kubernetes ConfigMaps/Secrets or cloud provider secret management (AWS Secrets Manager, etc.)

2. **Shared Library**: The `libs/forth_shared` must be included in the Docker image. The Dockerfile handles this by copying from the root context.

3. **No .env Files**: Production deployments should NOT rely on .env files. All configuration must come from environment variables.

4. **Security**:
   - Run as non-root user (handled in Dockerfile)
   - Use temporary volumes for downloads
   - Enable network policies in Kubernetes
   - Use TLS for all external communication

5. **Monitoring**:
   - Export metrics to Prometheus
   - Send logs to centralized logging (ELK, CloudWatch)
   - Set up alerts for download failures and latency

6. **Storage**:
   - Use ephemeral storage for temporary downloads
   - Clean up downloaded files after processing
   - Monitor disk usage

## Troubleshooting

### Common Issues

1. **"Module not found: libs.forth_shared"**
   - Ensure you're installing from the root directory
   - Check PYTHONPATH includes the app directory

2. **"Failed to connect to SQS"**
   - Verify AWS credentials are set
   - Check the queue name ends with `.fifo` for FIFO queues
   - Ensure the AWS region is correct

3. **"Download failed: 403 Forbidden"**
   - Verify Forth API credentials are correct
   - Check API key has necessary permissions
   - Ensure API key ID matches the key

4. **"No space left on device"**
   - Check /tmp/downloads directory
   - Ensure cleanup is working properly
   - Monitor disk usage in production

5. **Container fails health check**
   - Check logs: `docker logs document-downloader`
   - Verify all required environment variables are set
   - Ensure the service can reach AWS services and Forth API

## Development Workflow

1. Make changes to the code
2. Run tests: `pytest tests/`
3. Build locally: `docker build -f services/document-downloader/Dockerfile .`
4. Test with docker-compose
5. Push changes and let CI/CD handle deployment

## Architecture Notes

- The service depends on `libs/forth_shared` for common functionality
- Uses AWS SQS FIFO queues for ordered message processing
- Implements circuit breaker pattern for external API calls
- Downloads are stored temporarily before uploading to S3
- Supports horizontal scaling with proper concurrency limits

## Performance Tuning

- Adjust `DOCUMENT_WORKER_CONCURRENCY` based on available resources
- Monitor memory usage and adjust container limits
- Use appropriate `DOCUMENT_DOWNLOAD_TIMEOUT` for large files
- Consider using AWS EFS for shared temporary storage in multi-node setups 