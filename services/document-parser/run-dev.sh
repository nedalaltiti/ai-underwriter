#!/bin/bash
# services/document-parser/run-dev.sh
# Development script that loads .env file and runs the document-parser service

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo -e "${GREEN}🚀 Starting document-parser service in development mode...${NC}"

# Check if .env file exists
ENV_FILE="${SCRIPT_DIR}/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo -e "${RED}❌ .env file not found at: $ENV_FILE${NC}"
    echo -e "${YELLOW}💡 Create one by copying .env.example:${NC}"
    echo "   cp services/document-parser/.env.example services/document-parser/.env"
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
echo -e "${YELLOW}📍 Service will be available at: http://localhost:${PARSER_PORT:-8003}${NC}"
echo -e "${YELLOW}🔍 Health check: http://localhost:${PARSER_PORT:-8003}/api/v1/health${NC}"
echo -e "${YELLOW}📚 API docs: http://localhost:${PARSER_PORT:-8003}/docs${NC}"

# Run the service
uvicorn main:app \
    --reload \
    --host "${PARSER_HOST:-0.0.0.0}" \
    --port "${PARSER_PORT:-8003}" \
    --log-level info