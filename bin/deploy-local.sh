#!/bin/bash
# Deploy FlowPilot locally with Keycloak and SQLite
# This script builds Docker images with Keycloak/SQLite variants and deploys using docker-compose

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "FlowPilot Local Deployment"
echo "Environment: Keycloak + SQLite"
echo "=========================================="
echo ""

# Change to project root
cd "$PROJECT_ROOT"

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found"
    echo "Please create .env file with required secrets"
    exit 1
fi

# Validate environment
echo "📋 Validating environment..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Please install Docker Desktop."
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose not found. Please install Docker Compose."
    exit 1
fi

echo "✅ Environment validated"
echo ""

# Create module symlinks for local deployment
echo "🔗 Setting up module variants (Keycloak/SQLite)..."

# We'll use build args in Dockerfiles, but let's verify the variants exist
for module in profile_keycloak security_keycloak; do
    if [ ! -f "flowpilot-services/shared-libraries/${module}.py" ]; then
        echo "❌ Missing: flowpilot-services/shared-libraries/${module}.py"
        exit 1
    fi
done

if [ ! -f "flowpilot-services/delegation-api/graphdb_sqlite.py" ]; then
    echo "❌ Missing: flowpilot-services/delegation-api/graphdb_sqlite.py"
    exit 1
fi

echo "✅ All Keycloak/SQLite module variants found"
echo ""

# Stop any running services
echo "🛑 Stopping any running services..."
docker compose down --remove-orphans 2>/dev/null || true
echo ""

# Build images with Keycloak/SQLite variants
echo "🏗️  Building Docker images (this may take a few minutes)..."
docker compose build \
    --build-arg DEPLOYMENT_ENV=keycloak \
    flowpilot-authz-api \
    flowpilot-delegation-api \
    flowpilot-domain-services-api \
    flowpilot-ai-agent-api

echo "✅ Images built successfully"
echo ""

# Start the stack
echo "🚀 Starting FlowPilot local stack..."
docker compose up -d

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check service health
echo ""
echo "🏥 Checking service health..."
SERVICES=(
    "keycloak:8080"
    "opa:8181"
    "flowpilot-authz-api:8002"
    "flowpilot-domain-services-api:8003"
    "flowpilot-ai-agent-api:8004"
    "flowpilot-delegation-api:8005"
)

for service in "${SERVICES[@]}"; do
    name="${service%%:*}"
    port="${service##*:}"
    
    if curl -sf "http://localhost:$port/health" > /dev/null 2>&1 || \
       curl -sf -k "https://localhost:$port" > /dev/null 2>&1; then
        echo "✅ $name (port $port)"
    else
        echo "⚠️  $name (port $port) - may still be starting..."
    fi
done

echo ""
echo "=========================================="
echo "✅ Local Deployment Complete!"
echo "=========================================="
echo ""
echo "Services running:"
echo "  • Keycloak:        https://localhost:8443"
echo "  • OPA:             http://localhost:8181"
echo "  • AuthZ API:       http://localhost:8002"
echo "  • Domain Services: http://localhost:8003"
echo "  • AI Agent API:    http://localhost:8004"
echo "  • Delegation API:  http://localhost:8005"
echo ""
echo "Environment: Local (Keycloak + SQLite)"
echo ""
echo "Useful commands:"
echo "  • View logs:    docker compose logs -f"
echo "  • Stop stack:   docker compose down"
echo "  • Restart:      docker compose restart <service>"
echo ""
