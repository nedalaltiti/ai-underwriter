#!/bin/bash
# services/document-downloader/run-dev.sh
# Development script that loads .env file and runs the document-downloader service

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo -e "${GREEN}🚀 Starting document-downloader service in development mode...${NC}"

# Check if .env file exists
ENV_FILE="${SCRIPT_DIR}/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo -e "${RED}❌ .env file not found at: $ENV_FILE${NC}"
    echo -e "${YELLOW}💡 Create one by copying .env.example:${NC}"
    echo "   cp services/document-downloader/.env.example services/document-downloader/.env"
    echo "   # Edit the .env file with your actual values"
    exit 1
fi

echo -e "${YELLOW}📁 Loading environment variables from: $ENV_FILE${NC}"

# Load .env file and export variables
set -a  # automatically export all variables
source "$ENV_FILE"
set +a  # stop automatically exporting

# Set Python path
export PYTHONPATH="$ROOT_DIR:${PYTHONPATH:-}"

# Change to src directory
cd "${SCRIPT_DIR}/src"

echo -e "${GREEN}🌐 Starting uvicorn server...${NC}"
echo -e "${YELLOW}📍 Service will be available at: http://localhost:${DOCUMENT_PORT:-8002}${NC}"
echo -e "${YELLOW}🔍 Health check: http://localhost:${DOCUMENT_PORT:-8002}/api/v1/health${NC}"

# Run the service
uvicorn main:app \
    --reload \
    --host "${DOCUMENT_HOST:-0.0.0.0}" \
    --port "${DOCUMENT_PORT:-8002}" \
    --log-level info 