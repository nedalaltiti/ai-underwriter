#!/bin/bash
# scripts/deploy.sh - Main deployment script

set -euo pipefail

# Configuration
ENVIRONMENT=${1:-staging}
VERSION=${2:-latest}
NAMESPACE="forth-ai-underwriting"
ROLLOUT_TIMEOUT="10m"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

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

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check required tools
    for tool in kubectl aws docker; do
        if ! command -v $tool &> /dev/null; then
            log_error "$tool is not installed"
            exit 1
        fi
    done
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured"
        exit 1
    fi
    
    # Check kubectl context
    CURRENT_CONTEXT=$(kubectl config current-context)
    log_info "Current kubectl context: $CURRENT_CONTEXT"
    
    if [[ "$ENVIRONMENT" == "production" ]] && [[ ! "$CURRENT_CONTEXT" =~ "production" ]]; then
        log_error "Wrong kubectl context for production deployment"
        exit 1
    fi
}

validate_deployment() {
    local deployment=$1
    local namespace=$2
    
    log_info "Validating deployment: $deployment"
    
    # Check if deployment exists
    if ! kubectl get deployment "$deployment" -n "$namespace" &> /dev/null; then
        log_error "Deployment $deployment not found in namespace $namespace"
        return 1
    fi
    
    # Check replicas
    DESIRED=$(kubectl get deployment "$deployment" -n "$namespace" -o jsonpath='{.spec.replicas}')
    AVAILABLE=$(kubectl get deployment "$deployment" -n "$namespace" -o jsonpath='{.status.availableReplicas}')
    
    if [[ "$AVAILABLE" -lt "$DESIRED" ]]; then
        log_warn "Deployment $deployment: $AVAILABLE/$DESIRED replicas available"
        return 1
    fi
    
    log_info "Deployment $deployment is healthy"
    return 0
}

deploy_service() {
    local service=$1
    local image=$2
    
    log_info "Deploying $service with image $image"
    
    # Update deployment
    kubectl set image deployment/"$service" "$service"="$image" -n "$NAMESPACE"
    
    # Wait for rollout
    if kubectl rollout status deployment/"$service" -n "$NAMESPACE" --timeout="$ROLLOUT_TIMEOUT"; then
        log_info "$service deployment successful"
    else
        log_error "$service deployment failed"
        kubectl rollout undo deployment/"$service" -n "$NAMESPACE"
        exit 1
    fi
}

run_smoke_tests() {
    log_info "Running smoke tests..."
    
    # Get service endpoints
    WEBHOOK_URL=$(kubectl get service webhook-ingestion -n "$NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
    
    # Test webhook endpoint
    if curl -f -X GET "http://$WEBHOOK_URL/health" &> /dev/null; then
        log_info "Webhook service health check passed"
    else
        log_error "Webhook service health check failed"
        return 1
    fi
    
    # Test parser endpoint
    PARSER_URL=$(kubectl get service contract-parser -n "$NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
    
    if curl -f -X GET "http://$PARSER_URL/health" &> /dev/null; then
        log_info "Parser service health check passed"
    else
        log_error "Parser service health check failed"
        return 1
    fi
    
    return 0
}

# Main deployment flow
main() {
    log_info "Starting deployment to $ENVIRONMENT with version $VERSION"
    
    # Checks
    check_prerequisites
    
    # Set namespace based on environment
    if [[ "$ENVIRONMENT" == "staging" ]]; then
        NAMESPACE="forth-ai-underwriting-staging"
    fi
    
    # Get ECR registry
    ECR_REGISTRY=$(aws ecr describe-registry --query 'registryId' --output text).dkr.ecr.${AWS_REGION}.amazonaws.com
    
    # Deploy services
    SERVICES=("webhook-ingestion" "document-downloader" "contract-parser")
    
    for service in "${SERVICES[@]}"; do
        IMAGE="$ECR_REGISTRY/forth-ai/$service:$VERSION"
        deploy_service "$service" "$IMAGE"
    done
    
    # Validate deployments
    log_info "Validating all deployments..."
    sleep 30  # Wait for pods to stabilize
    
    for service in "${SERVICES[@]}"; do
        if ! validate_deployment "$service" "$NAMESPACE"; then
            log_error "Deployment validation failed"
            exit 1
        fi
    done
    
    # Run smoke tests
    if [[ "$ENVIRONMENT" == "production" ]]; then
        if ! run_smoke_tests; then
            log_error "Smoke tests failed"
            exit 1
        fi
    fi
    
    log_info "Deployment completed successfully!"
}

# Production safety check
if [[ "$ENVIRONMENT" == "production" ]]; then
    log_warn "⚠️  PRODUCTION DEPLOYMENT ⚠️"
    read -p "Are you sure you want to deploy to production? (yes/no): " confirm
    if [[ "$confirm" != "yes" ]]; then
        log_info "Deployment cancelled"
        exit 0
    fi
fi

# Run deployment
main