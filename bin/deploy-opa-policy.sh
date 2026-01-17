#!/bin/bash
# deploy-opa-policy.sh
#
# Fail-safe deployment script for OPA policies to GCP Cloud Run
# Demonstrates policy governance with validation, versioning, and rollback capability
#
# Usage:
#   ./bin/deploy-opa-policy.sh [--skip-tests] [--auto-approve]
#
# Features:
# - Pre-deployment validation (syntax check, local OPA test)
# - Git-based versioning (commit hash tagging)
# - Automated regression testing
# - Zero-downtime deployment with traffic shifting
# - Automatic rollback on test failures
# - Audit trail logging

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ID="vision-course-476214"
REGION="us-central1"
SERVICE_NAME="flowpilot-opa"
POLICY_DIR="infra/opa/policies"
IMAGE_REPO="us-central1-docker.pkg.dev/${PROJECT_ID}/flowpilot/opa"
AUDIT_LOG="logs/opa-deployments.log"

# Parse arguments
SKIP_TESTS=false
AUTO_APPROVE=false
while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-tests)
      SKIP_TESTS=true
      shift
      ;;
    --auto-approve)
      AUTO_APPROVE=true
      shift
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--skip-tests] [--auto-approve]"
      exit 1
      ;;
  esac
done

# Helper functions
log_info() {
  echo -e "${BLUE}ℹ${NC} $1"
}

log_success() {
  echo -e "${GREEN}✓${NC} $1"
}

log_warning() {
  echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
  echo -e "${RED}✗${NC} $1"
}

audit_log() {
  mkdir -p "$(dirname "$AUDIT_LOG")"
  echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $1" >> "$AUDIT_LOG"
}

# Governance: Pre-deployment checks
governance_check() {
  log_info "Running governance checks..."
  
  # Check 1: Uncommitted changes (policy must be version controlled)
  if [[ -n $(git status --porcelain "$POLICY_DIR") ]]; then
    log_warning "Uncommitted changes detected in policy directory"
    git status --short "$POLICY_DIR"
    if [[ "$AUTO_APPROVE" == "false" ]]; then
      read -p "Continue anyway? (y/N) " -n 1 -r
      echo
      if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_error "Deployment aborted - commit your changes first"
        exit 1
      fi
    fi
  fi
  
  # Check 2: OPA syntax validation
  log_info "Validating Rego syntax..."
  if command -v opa >/dev/null 2>&1; then
    if opa check "$POLICY_DIR" --strict; then
      log_success "Syntax validation passed"
    else
      log_error "Syntax validation failed"
      exit 1
    fi
  else
    log_warning "OPA CLI not installed - skipping local syntax check"
  fi
  
  # Check 3: Policy tests (if they exist)
  if [[ -f "${POLICY_DIR}/travel/policy_test.rego" ]] && command -v opa >/dev/null 2>&1; then
    log_info "Running OPA unit tests..."
    if opa test "$POLICY_DIR" -v; then
      log_success "Unit tests passed"
    else
      log_error "Unit tests failed"
      exit 1
    fi
  fi
  
  log_success "Governance checks passed"
}

# Get current git commit hash for versioning
get_version_tag() {
  git rev-parse --short HEAD
}

# Build and push container image
build_and_push() {
  local version_tag=$1
  
  log_info "Building OPA container (version: ${version_tag})..."
  
  # Build with both version tag and 'latest' tag
  if gcloud builds submit \
    --config=cloudbuild-opa.yaml \
    --substitutions="_VERSION_TAG=${version_tag}" \
    --quiet 2>&1 | grep -E '(QUEUED|WORKING|SUCCESS|ERROR)'; then
    log_success "Build completed successfully"
  else
    log_error "Build failed"
    audit_log "FAILED: Build failed for version ${version_tag}"
    exit 1
  fi
  
  # Tag the image with version
  gcloud artifacts docker tags add \
    "${IMAGE_REPO}:latest" \
    "${IMAGE_REPO}:${version_tag}" \
    --quiet || true
  
  log_success "Image tagged: ${version_tag}"
}

# Deploy new revision (without routing traffic)
deploy_revision() {
  local version_tag=$1
  
  log_info "Deploying new revision (no traffic)..."
  
  if gcloud run deploy "$SERVICE_NAME" \
    --image="${IMAGE_REPO}:latest" \
    --region="$REGION" \
    --platform=managed \
    --allow-unauthenticated \
    --timeout=60 \
    --cpu=1 \
    --memory=512Mi \
    --no-traffic \
    --tag="v${version_tag}" \
    --quiet; then
    log_success "Revision deployed (no traffic)"
  else
    log_error "Deployment failed"
    audit_log "FAILED: Deployment failed for version ${version_tag}"
    exit 1
  fi
}

# Get the latest revision name
get_latest_revision() {
  gcloud run revisions list \
    --service="$SERVICE_NAME" \
    --region="$REGION" \
    --format="value(metadata.name)" \
    --limit=1
}

# Get current active revision (receiving traffic)
get_active_revision() {
  gcloud run services describe "$SERVICE_NAME" \
    --region="$REGION" \
    --format="value(status.traffic[0].revisionName)"
}

# Shift traffic to new revision
shift_traffic() {
  local new_revision=$1
  local percentage=${2:-100}
  
  log_info "Shifting ${percentage}% traffic to ${new_revision}..."
  
  if gcloud run services update-traffic "$SERVICE_NAME" \
    --region="$REGION" \
    --to-revisions="${new_revision}=${percentage}" \
    --quiet; then
    log_success "Traffic shifted to ${new_revision}"
  else
    log_error "Traffic shift failed"
    return 1
  fi
}

# Run regression tests
run_regression_tests() {
  log_info "Running regression tests against deployed service..."
  
  if python3 flowpilot-testing/regression_test_firebase.py; then
    log_success "All regression tests passed"
    return 0
  else
    log_error "Regression tests failed"
    return 1
  fi
}

# Rollback to previous revision
rollback() {
  local previous_revision=$1
  
  log_warning "Rolling back to ${previous_revision}..."
  audit_log "ROLLBACK: Rolling back to ${previous_revision}"
  
  if shift_traffic "$previous_revision" 100; then
    log_success "Rollback successful"
    audit_log "ROLLBACK_SUCCESS: Restored ${previous_revision}"
  else
    log_error "Rollback failed - manual intervention required!"
    audit_log "ROLLBACK_FAILED: Manual intervention needed"
    exit 1
  fi
}

# Main deployment flow
main() {
  echo ""
  echo "═══════════════════════════════════════════════════════════"
  echo "  OPA Policy Deployment with Governance"
  echo "═══════════════════════════════════════════════════════════"
  echo ""
  
  # Step 1: Governance checks
  governance_check
  
  # Step 2: Get version information
  VERSION_TAG=$(get_version_tag)
  PREVIOUS_REVISION=$(get_active_revision)
  
  log_info "Current active revision: ${PREVIOUS_REVISION}"
  log_info "New version tag: ${VERSION_TAG}"
  
  # Step 3: User confirmation
  if [[ "$AUTO_APPROVE" == "false" ]]; then
    echo ""
    read -p "Proceed with deployment? (y/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
      log_warning "Deployment cancelled by user"
      exit 0
    fi
  fi
  
  echo ""
  audit_log "DEPLOY_START: Deploying version ${VERSION_TAG}"
  
  # Step 4: Build and push
  build_and_push "$VERSION_TAG"
  
  # Step 5: Deploy new revision (no traffic)
  deploy_revision "$VERSION_TAG"
  NEW_REVISION=$(get_latest_revision)
  log_info "New revision: ${NEW_REVISION}"
  
  # Step 6: Shift traffic to new revision
  if ! shift_traffic "$NEW_REVISION" 100; then
    log_error "Failed to shift traffic"
    audit_log "FAILED: Traffic shift failed for ${NEW_REVISION}"
    exit 1
  fi
  
  # Step 7: Run regression tests
  if [[ "$SKIP_TESTS" == "false" ]]; then
    echo ""
    log_info "Waiting 5 seconds for service to stabilize..."
    sleep 5
    
    if ! run_regression_tests; then
      log_error "Tests failed - initiating rollback"
      audit_log "TEST_FAILURE: Regression tests failed for ${NEW_REVISION}"
      rollback "$PREVIOUS_REVISION"
      exit 1
    fi
  else
    log_warning "Skipping regression tests (--skip-tests flag set)"
  fi
  
  # Step 8: Success
  echo ""
  echo "═══════════════════════════════════════════════════════════"
  log_success "Deployment successful!"
  echo "═══════════════════════════════════════════════════════════"
  echo ""
  echo "Version:          ${VERSION_TAG}"
  echo "Revision:         ${NEW_REVISION}"
  echo "Previous:         ${PREVIOUS_REVISION}"
  echo "Service URL:      https://${SERVICE_NAME}-${PROJECT_ID//-/}.${REGION}.run.app"
  echo ""
  echo "Tagged URL:       https://v${VERSION_TAG}---${SERVICE_NAME}-${PROJECT_ID//-/}.${REGION}.run.app"
  echo ""
  
  audit_log "DEPLOY_SUCCESS: Version ${VERSION_TAG} deployed as ${NEW_REVISION}"
  
  # Governance: Show audit trail
  if [[ -f "$AUDIT_LOG" ]]; then
    echo "Recent deployment history (last 5):"
    tail -n 5 "$AUDIT_LOG" | sed 's/^/  /'
    echo ""
  fi
  
  # Governance: Rollback instructions
  echo "To rollback if needed:"
  echo "  gcloud run services update-traffic ${SERVICE_NAME} \\"
  echo "    --region=${REGION} \\"
  echo "    --to-revisions=${PREVIOUS_REVISION}=100"
  echo ""
}

# Run main function
main "$@"
