#!/bin/bash
# Script to create and store FlowPilot token signing keys in GCP Secret Manager
#
# This script:
# 1. Checks if signing keys already exist locally
# 2. Creates secrets in GCP Secret Manager
# 3. Uploads the signing keys to Secret Manager
#
# Usage:
#   ./scripts/create-token-signing-keys-gcp.sh

set -e

PROJECT_ID="vision-course-476214"
REGION="us-central1"

echo "==========================================="
echo "FlowPilot Token Signing Keys - GCP Setup"
echo "==========================================="
echo ""

# Check if keys exist locally
if [ ! -f "secrets/flowpilot-signing-key.pem" ]; then
    echo "❌ Error: Signing key not found at secrets/flowpilot-signing-key.pem"
    echo "   Please run this command first:"
    echo "   openssl genrsa -out secrets/flowpilot-signing-key.pem 2048"
    exit 1
fi

if [ ! -f "secrets/flowpilot-signing-key-pub.pem" ]; then
    echo "❌ Error: Public key not found at secrets/flowpilot-signing-key-pub.pem"
    echo "   Please run this command first:"
    echo "   openssl rsa -in secrets/flowpilot-signing-key.pem -pubout -out secrets/flowpilot-signing-key-pub.pem"
    exit 1
fi

echo "✓ Found signing keys locally"
echo ""

# Set project
echo "Setting GCP project: $PROJECT_ID"
gcloud config set project $PROJECT_ID
echo ""

# Create or update private key secret
echo "Creating/updating secret: flowpilot-token-signing-key"
if gcloud secrets describe flowpilot-token-signing-key --project=$PROJECT_ID >/dev/null 2>&1; then
    echo "  Secret already exists, adding new version..."
    gcloud secrets versions add flowpilot-token-signing-key \
        --data-file=secrets/flowpilot-signing-key.pem \
        --project=$PROJECT_ID
else
    echo "  Creating new secret..."
    gcloud secrets create flowpilot-token-signing-key \
        --data-file=secrets/flowpilot-signing-key.pem \
        --replication-policy=automatic \
        --project=$PROJECT_ID
fi
echo "✓ Private key stored in Secret Manager"
echo ""

# Create or update public key secret
echo "Creating/updating secret: flowpilot-token-signing-key-pub"
if gcloud secrets describe flowpilot-token-signing-key-pub --project=$PROJECT_ID >/dev/null 2>&1; then
    echo "  Secret already exists, adding new version..."
    gcloud secrets versions add flowpilot-token-signing-key-pub \
        --data-file=secrets/flowpilot-signing-key-pub.pem \
        --project=$PROJECT_ID
else
    echo "  Creating new secret..."
    gcloud secrets create flowpilot-token-signing-key-pub \
        --data-file=secrets/flowpilot-signing-key-pub.pem \
        --replication-policy=automatic \
        --project=$PROJECT_ID
fi
echo "✓ Public key stored in Secret Manager"
echo ""

echo "==========================================="
echo "✓ Setup Complete"
echo "==========================================="
echo ""
echo "Secrets created:"
echo "  - flowpilot-token-signing-key (private key)"
echo "  - flowpilot-token-signing-key-pub (public key)"
echo ""
echo "Next steps:"
echo "  1. Deploy authz-api: ./deploy-all-services.sh"
echo "  2. Deploy web app: cd flowpilot-web && firebase deploy --only hosting"
echo "  3. Test token exchange: curl https://flowpilot-authz-api-737191827545.us-central1.run.app/v1/token/exchange"
echo ""
