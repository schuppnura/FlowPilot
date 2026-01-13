#!/bin/bash
# Initialize Keycloak after it starts - runs setup scripts automatically

set -e

echo "=========================================="
echo "Keycloak Initialization Script"
echo "=========================================="

# Wait for Keycloak to be ready
echo "Waiting for Keycloak to be ready..."
max_attempts=60
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if curl -k -s https://localhost:8443/realms/master > /dev/null 2>&1; then
        echo "✓ Keycloak is ready"
        break
    fi
    attempt=$((attempt + 1))
    if [ $((attempt % 5)) -eq 0 ]; then
        echo "  Attempt $attempt/$max_attempts - waiting..."
    fi
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo "✗ Keycloak did not become ready in time"
    exit 1
fi

# Additional wait to ensure Keycloak is fully initialized
sleep 5

# Change to project root (assuming script is in infra/keycloak)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# Run setup script
echo ""
echo "Running Keycloak setup..."
python3 scripts/setup_keycloak.sh

echo ""
echo "=========================================="
echo "✓ Keycloak initialization complete!"
echo "=========================================="


