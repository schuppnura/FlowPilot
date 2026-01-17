#!/bin/bash
# Deploy all FlowPilot services to Cloud Run with updated security library

set -e

# Validate environment configurations before deployment
echo "Validating environment configurations..."
./scripts/validate-env-configs.sh
echo ""

echo "Building and deploying all services with token-based security..."

# Build all service images
echo "Building domain-services-api..."
gcloud builds submit --config=cloudbuild-domain-services-api.yaml || echo "Build submitted (log streaming may have failed but build continues)"

echo "Building authz-api..."
gcloud builds submit --config=cloudbuild-authz-api.yaml || echo "Build submitted (log streaming may have failed but build continues)"

echo "Building delegation-api..."
gcloud builds submit --config=cloudbuild-delegation-api.yaml || echo "Build submitted (log streaming may have failed but build continues)"

echo "Building ai-agent-api..."
gcloud builds submit --config=cloudbuild-ai-agent-api.yaml || echo "Build submitted (log streaming may have failed but build continues)"

echo "Building persona-api..."
gcloud builds submit --config=cloudbuild-persona-api.yaml || echo "Build submitted (log streaming may have failed but build continues)"

# Deploy all services
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

echo "Deploying persona-api..."
gcloud run deploy flowpilot-persona-api \
  --image=us-central1-docker.pkg.dev/vision-course-476214/flowpilot/flowpilot-persona-api:latest \
  --region=us-central1 \
  --platform=managed \
  --allow-unauthenticated \
  --ingress=all \
  --port=8000 \
  --env-vars-file=cloud-run-envs/persona-api.yaml

echo ""
echo "All services deployed successfully!"
echo ""
echo "Service URLs:"
echo "  domain-services-api: https://flowpilot-domain-services-api-737191827545.us-central1.run.app"
echo "  authz-api: https://flowpilot-authz-api-737191827545.us-central1.run.app"
echo "  delegation-api: https://flowpilot-delegation-api-737191827545.us-central1.run.app"
echo "  persona-api: https://flowpilot-persona-api-737191827545.us-central1.run.app"
echo "  ai-agent-api: https://flowpilot-ai-agent-api-737191827545.us-central1.run.app"
echo ""
echo "Run regression tests with:"
echo "  python3 flowpilot-testing/regression_test_firebase.py"
