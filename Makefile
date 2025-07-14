# Makefile - Common development commands
.PHONY: help setup dev test clean deploy

# Default target
help:
	@echo "Available commands:"
	@echo "  make setup    - Set up development environment"
	@echo "  make dev      - Start local development stack"
	@echo "  make test     - Run all tests"
	@echo "  make clean    - Clean up resources"
	@echo "  make deploy   - Deploy to production"

# Setup development environment
setup:
	@echo "Setting up development environment..."
	# Install shared library
	cd shared && pip install -e .
	# Install service dependencies
	@for service in webhook-ingestion document-downloader contract-parser; do \
		echo "Installing $$service dependencies..."; \
		cd services/$$service && pip install -r requirements.txt; \
		cd ../..; \
	done
	# Copy environment template
	cp configs/.env.example configs/.env
	@echo "Setup complete! Edit configs/.env with your settings."

# Start development stack
dev:
	docker-compose up -d
	@echo "Services starting..."
	@echo "Webhook Service: http://localhost:8001"
	@echo "Document Service: http://localhost:8002"
	@echo "Parser Service: http://localhost:8003"
	@echo "LocalStack: http://localhost:4566"

# Run tests
test:
	@echo "Running tests..."
	# Run shared library tests
	cd shared && pytest tests/
	# Run service tests
	@for service in webhook-ingestion document-downloader contract-parser; do \
		echo "Testing $$service..."; \
		cd services/$$service && pytest tests/; \
		cd ../..; \
	done

# Integration tests
test-integration:
	@echo "Running integration tests..."
	python scripts/test_integration.py

# Clean up
clean:
	docker-compose down -v
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Deploy to production
deploy:
	@echo "Deploying to production..."
	./scripts/deploy.sh

# Database migrations
db-migrate:
	cd services/contract-parser && alembic upgrade head

# Generate API documentation
docs:
	@echo "Generating API documentation..."
	@for service in webhook-ingestion document-downloader contract-parser; do \
		echo "Generating docs for $$service..."; \
		cd services/$$service && python -m mkdocs build; \
		cd ../..; \
	done