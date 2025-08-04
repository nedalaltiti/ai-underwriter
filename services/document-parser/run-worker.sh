#!/bin/bash
# services/document-parser/run-worker.sh
# Script to run the document parser worker for background processing

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo -e "${GREEN}🔄 Starting document-parser worker...${NC}"

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

echo -e "${GREEN}⚙️  Worker Configuration:${NC}"
echo -e "${YELLOW}📊 Input Queue: ${PARSER_INPUT_QUEUE_NAME:-uw-downloaded-docs-dev-sqs.fifo}${NC}"
echo -e "${YELLOW}🔢 Concurrency: ${PARSER_WORKER_CONCURRENCY:-5}${NC}"
echo -e "${YELLOW}🤖 Gemini Model: ${PARSER_GEMINI_MODEL:-gemini-2.0-flash}${NC}"

echo -e "${GREEN}🚀 Starting background worker...${NC}"

# Run the worker
python -m services.worker