# Document Parser Service

AI-powered document extraction and validation service for debt settlement contracts using Google Gemini.

## Overview

The Document Parser Service is responsible for:

- **Document Processing**: Extract structured data from PDF documents using Gemini AI
- **Data Validation**: Validate extracted data against underwriting rules
- **Queue Processing**: Process documents from SQS queues automatically
- **API Endpoints**: Provide REST API for document processing requests

## Features

- 🤖 **AI-Powered Extraction**: Uses Google Gemini 2.0 Flash for accurate data extraction
- 📊 **Structured Validation**: Comprehensive validation against underwriting rules
- 🔄 **Retry Logic**: Robust error handling with exponential backoff
- 📈 **Observability**: Built-in metrics, tracing, and health checks
- 🐳 **Production Ready**: Docker containerized with security hardening
- ⚡ **High Performance**: Async processing with configurable concurrency

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   SQS Queue     │───▶│  Document       │───▶│  Validation     │
│  (Input)        │    │  Processor      │    │  Engine         │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │                        │
                              ▼                        ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │  Gemini API     │    │  Database       │
                       │                 │    │  (Results)      │
                       └─────────────────┘    └─────────────────┘
```

## Quick Start

### Development Setup

1. **Create environment file**:
   ```bash
   cp .env.example .env
   # Edit .env with your actual values
   ```

2. **Run in development mode**:
   ```bash
   ./run-dev.sh
   ```

3. **Access the service**:
   - API: http://localhost:8003
   - Health: http://localhost:8003/api/v1/health
   - Docs: http://localhost:8003/docs

### Production Deployment

1. **Build Docker image**:
   ```bash
   ./build.sh --version v1.0.0
   ```

2. **Deploy with Docker Compose**:
   ```bash
   docker-compose -f docker-compose.prod.yml up -d
   ```

## API Endpoints

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/parse` | Process and extract document data |
| `POST` | `/api/v1/validate` | Validate extracted document |
| `GET` | `/api/v1/tasks/{id}` | Get task status |

### Health & Monitoring

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health/live` | Liveness probe |
| `GET` | `/api/v1/health/ready` | Readiness probe |
| `GET` | `/api/v1/health` | Comprehensive health check |
| `GET` | `/api/v1/health/metrics` | Service metrics |

## Configuration

### Required Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `PARSER_GEMINI_SERVICE_ACCOUNT` | Gemini service account JSON | - | Yes |
| `PARSER_DATABASE_URL` | PostgreSQL connection URL | - | Yes |
| `AWS_ACCESS_KEY_ID` | AWS access key | - | Yes |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | - | Yes |

### Core Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `PARSER_ENVIRONMENT` | Environment (development/production) | `development` |
| `PARSER_LOG_LEVEL` | Log level | `INFO` |
| `PARSER_PORT` | Service port | `8003` |
| `PARSER_WORKERS` | Gunicorn workers | `4` |

### Gemini Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `PARSER_GEMINI_MODEL` | Gemini model name | `gemini-2.0-flash` |
| `PARSER_GEMINI_TEMPERATURE` | Model temperature | `0.1` |
| `PARSER_GEMINI_TIMEOUT` | API timeout (seconds) | `300` |

### Processing Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `PARSER_WORKER_CONCURRENCY` | Worker concurrency | `5` |
| `PARSER_MAX_FILE_SIZE_MB` | Max file size (MB) | `100` |
| `PARSER_PROCESSING_TIMEOUT` | Processing timeout (seconds) | `600` |
| `PARSER_MAX_RETRIES` | Max retry attempts | `3` |

## Usage Examples

### Process Document via API

```bash
curl -X POST http://localhost:8003/api/v1/parse \
  -H "Content-Type: application/json" \
  -d '{
    "document_url": "https://example.com/document.pdf",
    "contact_id": "contact_12345",
    "doc_id": "doc_67890"
  }'
```

### Check Health

```bash
curl http://localhost:8003/api/v1/health/live
```

### View Metrics

```bash
curl http://localhost:8003/api/v1/health/metrics
```

## Data Models

### Extracted Document Structure

```json
{
  "client_info": {
    "name": "John Doe",
    "ssn": "XXX-XX-1234",
    "dob": "1980-01-01",
    "email": "john@example.com",
    "phone": "555-123-4567",
    "address": { ... }
  },
  "financial_analysis": {
    "monthly_income": 5000.00,
    "monthly_expenses": 3500.00,
    "net_income": 1500.00,
    "total_enrolled_debt": 25000.00,
    ...
  },
  "creditors": [ ... ],
  "validation_results": [ ... ]
}
```

### Validation Results

```json
{
  "field": "budget_surplus",
  "passed": true,
  "reason": "Budget surplus: $250.00",
  "severity": "critical",
  "category": "financial"
}
```

## Validation Rules

The service validates documents against comprehensive underwriting rules:

### Financial Validations
- ✅ Positive budget surplus
- ✅ Minimum payment amount ($250)
- ✅ Debt-to-income ratio limits
- ✅ Minimum 50% unsecured debt

### Legal Validations
- ✅ Different sender/signer IP addresses
- ✅ First payment timing (2-45 days)
- ✅ SSN consistency across documents

### Compliance Validations
- ✅ High-risk creditor screening
- ✅ State assignment verification
- ✅ Program duration limits

## Development

### Running Tests

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html
```

### Code Quality

```bash
# Format code
black src/
isort src/

# Lint code
flake8 src/
mypy src/
```

### Local Development Stack

```bash
# Start PostgreSQL and LocalStack
docker-compose up -d postgres localstack

# Run service
./run-dev.sh
```

## Monitoring & Observability

### Health Checks

The service provides multiple health check endpoints:

- **Liveness** (`/health/live`): Basic service availability
- **Readiness** (`/health/ready`): Dependency health
- **Full Health** (`/health`): Comprehensive status

### Metrics

Built-in metrics tracking:

- Processing success/failure rates
- Processing latencies (average, P95)
- Token usage statistics
- Error rates by type

### Logging

Structured JSON logging with:

- Request/response tracking
- Processing pipeline stages
- Error details with context
- Performance metrics

## Security

### Container Security

- Non-root user execution
- Minimal base image (Python slim)
- Security capabilities hardening
- Read-only filesystem where possible

### Data Security

- Secure credential management via environment variables
- TLS encryption for external API calls
- Input validation and sanitization
- No sensitive data in logs

## Troubleshooting

### Common Issues

1. **Gemini API Errors**
   ```bash
   # Check credentials
   curl http://localhost:8003/api/v1/health/ready
   
   # Verify service account JSON format
   echo $PARSER_GEMINI_SERVICE_ACCOUNT | jq .
   ```

2. **Database Connection Issues**
   ```bash
   # Test database connectivity
   psql $PARSER_DATABASE_URL -c "SELECT 1"
   ```

3. **SQS Queue Issues**
   ```bash
   # List available queues
   aws sqs list-queues --region us-west-1
   ```

### Debug Mode

Run with debug logging:

```bash
PARSER_LOG_LEVEL=DEBUG ./run-dev.sh
```

### Performance Tuning

Adjust concurrency based on load:

```bash
# High throughput
PARSER_WORKER_CONCURRENCY=10 PARSER_WORKERS=8 ./run-dev.sh

# Low latency
PARSER_GEMINI_TEMPERATURE=0.0 PARSER_WORKERS=2 ./run-dev.sh
```