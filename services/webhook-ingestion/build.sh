#!/bin/bash
# services/webhook-ingestion/build.sh
# Production-ready build script for webhook-ingestion service

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SERVICE_NAME="webhook-ingestion"
REGISTRY="${DOCKER_REGISTRY:-docker.io}"
NAMESPACE="${DOCKER_NAMESPACE:-ai-underwriter}"
VERSION="${VERSION:-$(git rev-parse --short HEAD 2>/dev/null || echo 'latest')}"
BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Validation
validate_environment() {
    log_step "Validating build environment..."
    
    # Check if Docker is running
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker is not running. Please start Docker and try again."
        exit 1
    fi
    
    # Check if we're in the correct directory
    if [[ ! -f "libs/forth_shared/__init__.py" ]] || [[ ! -f "services/${SERVICE_NAME}/Dockerfile" ]]; then
        log_error "Build must be run from the project root directory"
        log_error "Expected structure:"
        log_error "  - libs/forth_shared/"
        log_error "  - services/${SERVICE_NAME}/"
        exit 1
    fi
    
    # Check if required files exist
    local required_files=(
        "libs/forth_shared/__init__.py"
        "services/${SERVICE_NAME}/Dockerfile"
        "services/${SERVICE_NAME}/pyproject.toml"
        "services/${SERVICE_NAME}/src/main.py"
    )
    
    for file in "${required_files[@]}"; do
        if [[ ! -f "$file" ]]; then
            log_error "Required file not found: $file"
            exit 1
        fi
    done
    
    log_info "Environment validation passed ✓"
}

# Build function
build_image() {
    log_step "Building ${SERVICE_NAME} Docker image..."
    
    local image_name="${NAMESPACE}/${SERVICE_NAME}"
    local full_tag="${image_name}:${VERSION}"
    local latest_tag="${image_name}:latest"
    
    log_info "Image: ${full_tag}"
    log_info "Build date: ${BUILD_DATE}"
    log_info "Git commit: $(git rev-parse HEAD 2>/dev/null || echo 'unknown')"
    
    # Build with proper context and args
    docker build \
        -f "services/${SERVICE_NAME}/Dockerfile" \
        -t "${full_tag}" \
        -t "${latest_tag}" \
        --build-arg BUILD_DATE="${BUILD_DATE}" \
        --build-arg VERSION="${VERSION}" \
        --build-arg SERVICE_NAME="${SERVICE_NAME}" \
        --label "build.version=${VERSION}" \
        --label "build.date=${BUILD_DATE}" \
        --label "build.commit=$(git rev-parse HEAD 2>/dev/null || echo 'unknown')" \
        .
    
    log_info "Build completed successfully ✓"
    
    # Tag for registry if different from docker.io
    if [[ "${REGISTRY}" != "docker.io" ]]; then
        log_step "Tagging for registry ${REGISTRY}..."
        docker tag "${full_tag}" "${REGISTRY}/${full_tag}"
        docker tag "${latest_tag}" "${REGISTRY}/${latest_tag}"
    fi
}

# Push function
push_image() {
    if [[ "${PUSH:-false}" != "true" ]]; then
        log_warn "Skipping push (set PUSH=true to enable)"
        return
    fi
    
    log_step "Pushing to registry..."
    
    local image_name="${NAMESPACE}/${SERVICE_NAME}"
    local full_tag="${image_name}:${VERSION}"
    local latest_tag="${image_name}:latest"
    
    if [[ "${REGISTRY}" != "docker.io" ]]; then
        docker push "${REGISTRY}/${full_tag}"
        docker push "${REGISTRY}/${latest_tag}"
    else
        docker push "${full_tag}"
        docker push "${latest_tag}"
    fi
    
    log_info "Push completed successfully ✓"
}

# Security scan
security_scan() {
    if [[ "${SECURITY_SCAN:-false}" != "true" ]]; then
        log_warn "Skipping security scan (set SECURITY_SCAN=true to enable)"
        return
    fi
    
    log_step "Running security scan..."
    
    local image_name="${NAMESPACE}/${SERVICE_NAME}:${VERSION}"
    
    # Try different security scanning tools
    if command -v trivy >/dev/null 2>&1; then
        trivy image --exit-code 1 --severity HIGH,CRITICAL "${image_name}"
    elif command -v docker >/dev/null 2>&1 && docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest image --exit-code 1 --severity HIGH,CRITICAL "${image_name}" 2>/dev/null; then
        log_info "Security scan completed with Trivy"
    else
        log_warn "No security scanner available (install trivy for security scanning)"
    fi
}

# Cleanup function
cleanup() {
    if [[ "${CLEANUP:-false}" == "true" ]]; then
        log_step "Cleaning up dangling images..."
        docker image prune -f
        log_info "Cleanup completed ✓"
    fi
}

# Main execution
main() {
    log_info "Starting build for ${SERVICE_NAME} service..."
    log_info "Registry: ${REGISTRY}"
    log_info "Namespace: ${NAMESPACE}"
    log_info "Version: ${VERSION}"
    
    validate_environment
    build_image
    security_scan
    push_image
    cleanup
    
    # Output final image information
    log_step "Build Summary"
    echo -e "${GREEN}✅ Build complete!${NC}"
    echo -e "${GREEN}📦 Image: ${NAMESPACE}/${SERVICE_NAME}:${VERSION}${NC}"
    
    # Show image details
    docker images "${NAMESPACE}/${SERVICE_NAME}" | head -n 3
    
    # Show image size and layers
    docker history "${NAMESPACE}/${SERVICE_NAME}:${VERSION}" --format "table {{.CreatedBy}}\t{{.Size}}" | head -n 10
}

# Help function
show_help() {
    cat << EOF
${GREEN}${SERVICE_NAME} Build Script${NC}

${YELLOW}Usage:${NC}
  ./build.sh [options]

${YELLOW}Environment Variables:${NC}
  VERSION              Image version tag (default: git short hash or 'latest')
  DOCKER_REGISTRY      Docker registry URL (default: docker.io)
  DOCKER_NAMESPACE     Docker namespace (default: ai-underwriter)
  PUSH                 Push to registry (default: false)
  SECURITY_SCAN        Run security scan (default: false)
  CLEANUP              Clean up dangling images (default: false)

${YELLOW}Examples:${NC}
  # Basic build
  ./build.sh

  # Build and push to registry
  VERSION=v1.0.0 PUSH=true ./build.sh

  # Build with security scan
  SECURITY_SCAN=true ./build.sh

  # Build for production with all features
  VERSION=v1.0.0 PUSH=true SECURITY_SCAN=true CLEANUP=true ./build.sh

${YELLOW}Requirements:${NC}
  - Docker must be running
  - Must be run from project root directory
  - Required files: libs/forth_shared/, services/${SERVICE_NAME}/

EOF
}

# Handle command line arguments
case "${1:-}" in
    -h|--help)
        show_help
        exit 0
        ;;
    *)
        main "$@"
        ;;
esac 