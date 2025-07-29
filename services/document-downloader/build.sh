#!/bin/bash

# services/document-downloader/build.sh
# Production build script for document-downloader service

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SERVICE_NAME="document-downloader"
IMAGE_NAME="ai-underwriter/document-downloader"
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
    
    # Check if we're in the right directory
    if [[ ! -f "Dockerfile" ]]; then
        log_error "Dockerfile not found. Please run this script from services/document-downloader/"
        exit 1
    fi
    
    # Check if required files exist
    local required_files=(
        "../../libs/forth_shared"
        "pyproject.toml"
        "src/main.py"
    )
    
    for file in "${required_files[@]}"; do
        if [[ ! -e "$file" ]]; then
            log_error "Required file/directory not found: $file"
            exit 1
        fi
    done
    
    log_success "Environment validation passed"
}

# Build function
build_image() {
    log_info "Building Docker image..."
    
    local build_args=(
        "--build-arg" "BUILD_DATE=${BUILD_DATE}"
        "--build-arg" "VERSION=${VERSION}"
        "--build-arg" "SERVICE_NAME=${SERVICE_NAME}"
        "--tag" "${IMAGE_NAME}:${VERSION}"
        "--tag" "${IMAGE_NAME}:latest"
        "--file" "Dockerfile"
        "../.."  # Build context is root directory
    )
    
    if ! docker build "${build_args[@]}"; then
        log_error "Docker build failed"
        exit 1
    fi
    
    log_success "Docker image built successfully"
    log_info "Image tags:"
    log_info "  - ${IMAGE_NAME}:${VERSION}"
    log_info "  - ${IMAGE_NAME}:latest"
}

# Security scan function
security_scan() {
    if [[ "$SECURITY_SCAN" == "true" ]]; then
        log_info "Running security scan with Trivy..."
        
        if command -v trivy >/dev/null 2>&1; then
            trivy image --severity HIGH,CRITICAL "${IMAGE_NAME}:${VERSION}"
        else
            log_warning "Trivy not found, skipping security scan"
            log_info "Install Trivy: https://aquasecurity.github.io/trivy/"
        fi
    fi
}

# Push function
push_image() {
    if [[ "$PUSH" == "true" ]]; then
        if [[ -n "$REGISTRY" ]]; then
            log_info "Tagging image for registry: $REGISTRY"
            docker tag "${IMAGE_NAME}:${VERSION}" "${REGISTRY}/${IMAGE_NAME}:${VERSION}"
            docker tag "${IMAGE_NAME}:latest" "${REGISTRY}/${IMAGE_NAME}:latest"
            
            log_info "Pushing to registry..."
            docker push "${REGISTRY}/${IMAGE_NAME}:${VERSION}"
            docker push "${REGISTRY}/${IMAGE_NAME}:latest"
            
            log_success "Images pushed to registry"
        else
            log_warning "REGISTRY not set, skipping push"
        fi
    fi
}

# Cleanup function
cleanup_build() {
    if [[ "$CLEANUP" == "true" ]]; then
        log_info "Cleaning up dangling images..."
        docker image prune -f >/dev/null 2>&1 || true
        log_success "Cleanup completed"
    fi
}

# Build summary
build_summary() {
    log_info "Build Summary:"
    echo "  Service: $SERVICE_NAME"
    echo "  Version: $VERSION"
    echo "  Build Date: $BUILD_DATE"
    echo "  Image: ${IMAGE_NAME}:${VERSION}"
    
    if [[ -n "$REGISTRY" && "$PUSH" == "true" ]]; then
        echo "  Registry: ${REGISTRY}/${IMAGE_NAME}:${VERSION}"
    fi
    
    # Show image size
    local image_size
    image_size=$(docker images "${IMAGE_NAME}:${VERSION}" --format "{{.Size}}")
    echo "  Image Size: $image_size"
    
    log_success "Document downloader service built successfully!"
}

# Main execution
main() {
    log_info "Starting build for $SERVICE_NAME service"
    log_info "Version: $VERSION"
    log_info "Build Date: $BUILD_DATE"
    
    validate_environment
    build_image
    security_scan
    push_image
    cleanup_build
    build_summary
}

# Script execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi 