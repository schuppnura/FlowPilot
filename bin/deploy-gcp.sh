#!/bin/bash
# Deploy FlowPilot to GCP Cloud Run with Firebase and PostgreSQL
# This script builds Docker images with Firebase/PostgreSQL variants and deploys to Cloud Run

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "FlowPilot GCP Deployment"
echo "Environment: Firebase + PostgreSQL"
echo "=========================================="
echo ""

# Change to project root
cd "$PROJECT_ROOT"

# Validate environment
echo "📋 Validating environment..."
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI not found. Please install Google Cloud SDK."
    exit 1
fi

# Check if authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" &> /dev/null; then
    echo "❌ Not authenticated to gcloud. Run: gcloud auth login"
    exit 1
fi

echo "✅ Environment validated"
echo ""

# Validate environment configurations
echo "🔍 Validating Cloud Run environment configurations..."
if [ -f "scripts/validate-env-configs.sh" ]; then
    ./scripts/validate-env-configs.sh
else
    echo "⚠️  Skipping validation (script not found)"
fi
echo ""

# Verify Firebase/PostgreSQL module variants exist
echo "🔗 Verifying module variants (Firebase/PostgreSQL)..."
for module in profile_firebase security_firebase; do
    if [ ! -f "flowpilot-services/shared-libraries/${module}.py" ]; then
        echo "❌ Missing: flowpilot-services/shared-libraries/${module}.py"
        exit 1
    fi
done

if [ ! -f "flowpilot-services/delegation-api/graphdb_postgresql.py" ]; then
    echo "❌ Missing: flowpilot-services/delegation-api/graphdb_postgresql.py"
    exit 1
fi

echo "✅ All Firebase/PostgreSQL module variants found"
echo ""

# Build all service images using Cloud Build
echo "🏗️  Building service images with Cloud Build..."
echo ""

echo "Building domain-services-api..."
gcloud builds submit --config=cloudbuild-domain-services-api.yaml

echo "Building authz-api..."
gcloud builds submit --config=cloudbuild-authz-api.yaml

echo "Building delegation-api..."
gcloud builds submit --config=cloudbuild-delegation-api.yaml

echo "Building ai-agent-api..."
gcloud builds submit --config=cloudbuild-ai-agent-api.yaml

if [ -f "cloudbuild-persona-api.yaml" ]; then
    echo "Building persona-api..."
    gcloud builds submit --config=cloudbuild-persona-api.yaml
fi

echo "✅ All images built successfully"
echo ""

# Deploy all services to Cloud Run
echo "🚀 Deploying services to Cloud Run..."
echo ""

echo "Deploying domain-services-api..."
gcloud run deploy flowpilot-domain-services-api \
  --image=us-central1-docker.pkg.dev/vision-course-476214/flowpilot/flowpilot-domain-services-api:latest \
  --region=us-central1 \
  --platform=managed \
  --allow-unauthenticated \
  --ingress=all \
  --env-vars-file=cloud-run-envs/domain-services-api.yaml

echo "Deploying authz-api..."
gcloud run deploy flowpilot-authz-api \
  --image=us-central1-docker.pkg.dev/vision-course-476214/flowpilot/flowpilot-authz-api:latest \
  --region=us-central1 \
  --platform=managed \
  --allow-unauthenticated \
  --ingress=all \
  --env-vars-file=cloud-run-envs/authz-api.yaml

echo "Deploying delegation-api..."
gcloud run deploy flowpilot-delegation-api \
  --image=us-central1-docker.pkg.dev/vision-course-476214/flowpilot/flowpilot-delegation-api:latest \
  --region=us-central1 \
  --platform=managed \
  --allow-unauthenticated \
  --ingress=all \
  --env-vars-file=cloud-run-envs/delegation-api.yaml

echo "Deploying ai-agent-api..."
gcloud run deploy flowpilot-ai-agent-api \
  --image=us-central1-docker.pkg.dev/vision-course-476214/flowpilot/flowpilot-ai-agent-api:latest \
  --region=us-central1 \
  --platform=managed \
  --allow-unauthenticated \
  --ingress=all \
  --env-vars-file=cloud-run-envs/ai-agent-api.yaml

if [ -f "cloud-run-envs/persona-api.yaml" ]; then
    echo "Deploying persona-api..."
    gcloud run deploy flowpilot-persona-api \
      --image=us-central1-docker.pkg.dev/vision-course-476214/flowpilot/flowpilot-persona-api:latest \
      --region=us-central1 \
      --platform=managed \
      --allow-unauthenticated \
      --ingress=all \
      --port=8000 \
      --env-vars-file=cloud-run-envs/persona-api.yaml
fi

echo ""
echo "=========================================="
echo "✅ GCP Deployment Complete!"
echo "=========================================="
echo ""
echo "Service URLs:"
echo "  • Domain Services: https://flowpilot-domain-services-api-737191827545.us-central1.run.app"
echo "  • AuthZ API:       https://flowpilot-authz-api-737191827545.us-central1.run.app"
echo "  • Delegation API:  https://flowpilot-delegation-api-737191827545.us-central1.run.app"
echo "  • AI Agent API:    https://flowpilot-ai-agent-api-737191827545.us-central1.run.app"
echo "  • User Profile:    https://flowpilot-persona-api-737191827545.us-central1.run.app"
echo ""
echo "Environment: GCP (Firebase + PostgreSQL)"
echo ""
echo "Run regression tests:"
echo "  python3 flowpilot-testing/regression_test_firebase.py"
echo ""
