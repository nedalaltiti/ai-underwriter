#!/bin/bash
# services/webhook-ingestion/build.sh

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SERVICE_NAME="webhook-ingestion"
REGISTRY="${DOCKER_REGISTRY:-docker.io}"
NAMESPACE="${DOCKER_NAMESPACE:-ai-underwriter}"
VERSION="${VERSION:-latest}"

echo -e "${GREEN}Building ${SERVICE_NAME} service...${NC}"

# Ensure we're in the root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${ROOT_DIR}"

# Build the Docker image
echo -e "${YELLOW}Building Docker image...${NC}"
docker build \
    -f "services/${SERVICE_NAME}/Dockerfile" \
    -t "${NAMESPACE}/${SERVICE_NAME}:${VERSION}" \
    -t "${NAMESPACE}/${SERVICE_NAME}:latest" \
    --build-arg BUILD_DATE="$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
    --build-arg VERSION="${VERSION}" \
    .

# Tag for registry
if [ "${REGISTRY}" != "docker.io" ]; then
    echo -e "${YELLOW}Tagging for registry ${REGISTRY}...${NC}"
    docker tag "${NAMESPACE}/${SERVICE_NAME}:${VERSION}" "${REGISTRY}/${NAMESPACE}/${SERVICE_NAME}:${VERSION}"
    docker tag "${NAMESPACE}/${SERVICE_NAME}:latest" "${REGISTRY}/${NAMESPACE}/${SERVICE_NAME}:latest"
fi

# Push to registry if requested
if [ "${PUSH:-false}" = "true" ]; then
    echo -e "${YELLOW}Pushing to registry...${NC}"
    if [ "${REGISTRY}" != "docker.io" ]; then
        docker push "${REGISTRY}/${NAMESPACE}/${SERVICE_NAME}:${VERSION}"
        docker push "${REGISTRY}/${NAMESPACE}/${SERVICE_NAME}:latest"
    else
        docker push "${NAMESPACE}/${SERVICE_NAME}:${VERSION}"
        docker push "${NAMESPACE}/${SERVICE_NAME}:latest"
    fi
fi

echo -e "${GREEN}✅ Build complete!${NC}"

# Output image details
echo -e "${GREEN}Image: ${NAMESPACE}/${SERVICE_NAME}:${VERSION}${NC}"
docker images | grep "${SERVICE_NAME}" | head -n 2 