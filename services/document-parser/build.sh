#!/bin/bash

# services/document-parser/build.sh
# Production build script for document-parser service

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SERVICE_NAME="document-parser"
IMAGE_NAME="ai-underwriter/document-parser"
VERSION="${VERSION:-$(date +%Y%m%d-%H%M%S)}"
BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
REGISTRY="${REGISTRY:-}"
PUSH="${PUSH:-false}"
SECURITY_SCAN="${SECURITY_SCAN:-false}"
CLEANUP="${CLEANUP:-true}"

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Validation functions
validate_environment() {
    log_info "Validating build environment..."
    
    # Check if Docker is running
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker is not running or not accessible"
        exit 1
    fi
    
    # Check if we're in the correct directory
    if [[ ! -f "Dockerfile" ]]; then
        log_error "Dockerfile not found. Please run from the document-parser directory"
        exit 1
    fi
    
    # Check if root directory structure exists
    if [[ ! -f "../../libs/pyproject.toml" ]]; then
        log_error "Shared libs not found. Please run from the correct directory structure"
        exit 1
    fi
    
    log_success "Environment validation passed"
}

# Build function
build_image() {
    log_info "Building Docker image..."
    log_info "Image: ${IMAGE_NAME}:${VERSION}"
    log_info "Build date: ${BUILD_DATE}"
    
    # Get root directory (two levels up from service directory)
    ROOT_DIR="$(cd ../.. && pwd)"
    
    # Build the image
    docker build \
        --file Dockerfile \
        --tag "${IMAGE_NAME}:${VERSION}" \
        --tag "${IMAGE_NAME}:latest" \
        --build-arg BUILD_DATE="${BUILD_DATE}" \
        --build-arg VERSION="${VERSION}" \
        --build-arg SERVICE_NAME="${SERVICE_NAME}" \
        --progress=plain \
        --pull \
        "${ROOT_DIR}"
    
    if [[ $? -eq 0 ]]; then
        log_success "Docker image built successfully"
    else
        log_error "Docker build failed"
        exit 1
    fi
}

# Security scan function
security_scan() {
    if [[ "${SECURITY_SCAN}" != "true" ]]; then
        return 0
    fi
    
    log_info "Running security scan..."
    
    # Check if trivy is available
    if command -v trivy >/dev/null 2>&1; then
        trivy image --severity HIGH,CRITICAL "${IMAGE_NAME}:${VERSION}"
        if [[ $? -ne 0 ]]; then
            log_warning "Security vulnerabilities found, but continuing..."
        fi
    else
        log_warning "Trivy not found, skipping security scan"
        log_info "Install trivy with: brew install trivy (macOS) or apt-get install trivy (Ubuntu)"
    fi
}

# Push function
push_image() {
    if [[ "${PUSH}" != "true" ]]; then
        return 0
    fi
    
    if [[ -z "${REGISTRY}" ]]; then
        log_warning "No registry specified, skipping push"
        return 0
    fi
    
    log_info "Pushing to registry: ${REGISTRY}"
    
    # Tag for registry
    REGISTRY_IMAGE="${REGISTRY}/${IMAGE_NAME}:${VERSION}"
    REGISTRY_LATEST="${REGISTRY}/${IMAGE_NAME}:latest"
    
    docker tag "${IMAGE_NAME}:${VERSION}" "${REGISTRY_IMAGE}"
    docker tag "${IMAGE_NAME}:latest" "${REGISTRY_LATEST}"
    
    # Push images
    docker push "${REGISTRY_IMAGE}"
    docker push "${REGISTRY_LATEST}"
    
    log_success "Images pushed to registry"
}

# Cleanup function
cleanup_build_cache() {
    if [[ "${CLEANUP}" != "true" ]]; then
        return 0
    fi
    
    log_info "Cleaning up build cache..."
    docker builder prune -f
    log_success "Build cache cleaned"
}

# Test function
test_image() {
    log_info "Testing built image..."
    
    # Test basic container startup
    log_info "Testing container startup..."
    CONTAINER_ID=$(docker run -d --rm \
        -e PARSER_ENVIRONMENT=test \
        -e PARSER_GEMINI_SERVICE_ACCOUNT='{"type":"service_account","project_id":"test"}' \
        -e PARSER_DATABASE_URL=postgresql://test:test@localhost/test \
        -p 18003:8003 \
        "${IMAGE_NAME}:${VERSION}")
    
    # Wait for container to start
    sleep 10
    
    # Test health endpoint
    if curl -f http://localhost:18003/api/v1/health/live >/dev/null 2>&1; then
        log_success "Health check passed"
    else
        log_error "Health check failed"
        docker logs "${CONTAINER_ID}"
        docker stop "${CONTAINER_ID}"
        exit 1
    fi
    
    # Stop test container
    docker stop "${CONTAINER_ID}"
    log_success "Image testing completed"
}

# Get image size
get_image_size() {
    local size=$(docker images "${IMAGE_NAME}:${VERSION}" --format "table {{.Size}}" | tail -n 1)
    log_info "Final image size: ${size}"
}

# Show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --version VERSION      Set image version (default: current timestamp)"
    echo "  --registry REGISTRY    Registry to push to"
    echo "  --push                 Push image to registry"
    echo "  --scan                 Run security scan"
    echo "  --no-cleanup          Skip cleanup of build cache"
    echo "  --no-test             Skip image testing"
    echo "  --help                Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  VERSION               Image version"
    echo "  REGISTRY              Docker registry"
    echo "  PUSH                  Push to registry (true/false)"
    echo "  SECURITY_SCAN         Run security scan (true/false)"
    echo "  CLEANUP               Cleanup build cache (true/false)"
}

# Parse command line arguments
RUN_TESTS=true

while [[ $# -gt 0 ]]; do
    case $1 in
        --version)
            VERSION="$2"
            shift 2
            ;;
        --registry)
            REGISTRY="$2"
            shift 2
            ;;
        --push)
            PUSH=true
            shift
            ;;
        --scan)
            SECURITY_SCAN=true
            shift
            ;;
        --no-cleanup)
            CLEANUP=false
            shift
            ;;
        --no-test)
            RUN_TESTS=false
            shift
            ;;
        --help)
            show_usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Main execution
main() {
    log_info "🚀 Starting build for ${SERVICE_NAME}"
    log_info "Version: ${VERSION}"
    log_info "Build date: ${BUILD_DATE}"
    log_info "Push: ${PUSH}"
    log_info "Security scan: ${SECURITY_SCAN}"
    
    validate_environment
    build_image
    
    if [[ "${RUN_TESTS}" == "true" ]]; then
        test_image
    fi
    
    security_scan
    push_image
    cleanup_build_cache
    get_image_size
    
    log_success "✅ Build completed successfully!"
    log_info "Image: ${IMAGE_NAME}:${VERSION}"
    
    if [[ "${PUSH}" == "true" && -n "${REGISTRY}" ]]; then
        log_info "Registry: ${REGISTRY}/${IMAGE_NAME}:${VERSION}"
    fi
}

# Run main function
main "$@"