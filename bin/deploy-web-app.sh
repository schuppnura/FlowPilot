#!/bin/bash
# Deploy FlowPilot Web App to Firebase Hosting

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# The web app is located in the parent directory of the bin folder
WEB_APP_DIR="$( dirname "${SCRIPT_DIR}" )/flowpilot-web"
SERVICE_ACCOUNT_KEY="${SCRIPT_DIR}/firebase-admin-key.json"

echo "🚀 Deploying FlowPilot Web App to Firebase Hosting"
echo ""

# Check if Firebase CLI is installed
if ! command -v firebase &> /dev/null; then
    echo "❌ Firebase CLI not found. Installing..."
    npm install -g firebase-tools
    echo "✅ Firebase CLI installed"
    echo ""
fi

# Check for service account key
if [ ! -f "${SERVICE_ACCOUNT_KEY}" ]; then
    echo "❌ Service account key not found at: ${SERVICE_ACCOUNT_KEY}"
    echo "Please ensure the firebase-admin-key.json file exists"
    exit 1
fi

echo "✅ Using service account authentication"
echo "📁 Service account: ${SERVICE_ACCOUNT_KEY}"
echo ""

# Authenticate gcloud with service account
echo "🔐 Activating service account..."
gcloud auth activate-service-account --key-file="${SERVICE_ACCOUNT_KEY}" --quiet

if [ $? -ne 0 ]; then
    echo "❌ Failed to activate service account"
    echo "Falling back to existing authentication..."
else
    echo "✅ Service account activated"
fi
echo ""

# Change to web app directory
cd "${WEB_APP_DIR}"
echo "📁 Working directory: $(pwd)"
echo ""

# Build the app
echo "📦 Building production bundle..."
npm run build

if [ ! -d "dist" ]; then
    echo "❌ Build failed: dist directory not found"
    exit 1
fi

echo "✅ Build complete"
echo ""

# Deploy to Firebase Hosting using service account
echo "🌐 Deploying to Firebase Hosting..."
firebase deploy --only hosting --project vision-course-476214

echo ""
echo "✅ Deployment complete!"
echo ""
echo "Your app should be available at:"
echo "  https://vision-course-476214.web.app"
echo "  https://vision-course-476214.firebaseapp.com"
echo ""
