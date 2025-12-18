#!/usr/bin/env bash
set -euo pipefail

# Purpose: Bring the full stack up (build + run) in a repeatable way.
# Why: Docker newcomers benefit from one “happy path” command.
# Assumptions: Docker Desktop + Compose v2 installed; run from repo root or any subdir.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo ">>> Building OCI policy bundle..."
if command -v policy &> /dev/null; then
    policy build infra/***REMOVED***/cfg/bundle -t localhost/flowpilot-policy:latest
    policy save localhost/flowpilot-policy:latest -f infra/***REMOVED***/cfg/bundle/flowpilot-policy.tar.gz
    echo "✓ Policy bundle built successfully"
else
    echo "⚠ Warning: policy CLI not found. Using existing bundle."
    echo "   Install with: brew tap opcr-io/tap && brew install opcr-io/tap/policy"
fi

echo ">>> Starting HTTPS bundle server..."
pkill -f "https_bundle_server.py" 2>/dev/null || true
nohup python3 infra/***REMOVED***/cfg/https_bundle_server.py > /tmp/https-bundle-server.log 2>&1 &
sleep 2

docker compose up -d --build
docker compose ps

echo ""
echo ">>> Waiting for ***REMOVED*** to be ready..."
sleep 3

echo ">>> Initializing ***REMOVED*** manifest..."
"$REPO_ROOT/bin/***REMOVED***-init.sh"

echo ">>> Waiting for Keycloak to be ready..."
sleep 5

echo ">>> Provisioning users and agent..."
python3 "$REPO_ROOT/provision_current_user.py" || echo "Warning: User provisioning failed. Run 'python3 provision_current_user.py' manually."

cat <<'EOF'

Stack is up.

Key URLs (host):
- Keycloak:                http://localhost:8080 / https://localhost:8443
- ***REMOVED*** Console:           https://localhost:9080   (self-signed; your browser will warn)
- ***REMOVED*** Directory API:     http://localhost:9393
- Agent Runner API:        http://localhost:8004
- Services API:            http://localhost:8003
- AuthZ API:               http://localhost:8002
- HTTPS Bundle Server:     https://localhost:8888   (serves OCI policy bundles)

EOF
