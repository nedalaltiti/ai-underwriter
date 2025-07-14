#!/bin/bash
# scripts/rollback.sh - Rollback deployment script

set -euo pipefail

SERVICE=${1:-all}
NAMESPACE=${2:-forth-ai-underwriting}

log_info() {
    echo -e "\033[0;32m[INFO]\033[0m $1"
}

log_error() {
    echo -e "\033[0;31m[ERROR]\033[0m $1"
}

rollback_service() {
    local service=$1
    
    log_info "Rolling back $service..."
    
    # Get rollout history
    kubectl rollout history deployment/"$service" -n "$NAMESPACE"
    
    # Rollback to previous version
    if kubectl rollout undo deployment/"$service" -n "$NAMESPACE"; then
        log_info "Rollback initiated for $service"
        
        # Wait for rollback to complete
        kubectl rollout status deployment/"$service" -n "$NAMESPACE"
        log_info "Rollback completed for $service"
    else
        log_error "Rollback failed for $service"
        exit 1
    fi
}

# Main
if [[ "$SERVICE" == "all" ]]; then
    SERVICES=("webhook-ingestion" "document-downloader" "contract-parser")
    for svc in "${SERVICES[@]}"; do
        rollback_service "$svc"
    done
else
    rollback_service "$SERVICE"
fi

log_info "Rollback completed!"
