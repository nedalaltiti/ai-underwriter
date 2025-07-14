#!/bin/bash
# scripts/setup_webhook_dev.sh
# Setup script for webhook-ingestion service development

set -e

echo "🚀 Setting up webhook-ingestion service for development..."

# Navigate to project root
cd "$(dirname "$0")/.."

# Install shared library in editable mode
echo "📦 Installing shared library..."
pip install -e services/shared/

# Install main project dependencies
echo "📦 Installing project dependencies..."
pip install -e .

# Set Python path for development
export PYTHONPATH="${PYTHONPATH}:$(pwd)/services/webhook-ingestion/src:$(pwd)/services/shared"

echo "✅ Setup complete!"
echo ""
echo "To run the webhook service:"
echo "  cd services/webhook-ingestion"
echo "  python -m src.main"
echo ""
echo "Or from project root:"
echo "  python -m services.webhook-ingestion.src.main"
echo ""
echo "Environment variables will be loaded from configs/.env" 