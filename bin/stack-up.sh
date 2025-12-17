#!/usr/bin/env bash
set -euo pipefail

# Purpose: Bring the full stack up (build + run) in a repeatable way.
# Why: Docker newcomers benefit from one “happy path” command.
# Assumptions: Docker Desktop + Compose v2 installed; run from repo root or any subdir.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

docker compose up -d --build
docker compose ps

echo ""
echo ">>> Waiting for ***REMOVED*** to be ready..."
sleep 3

echo ">>> Initializing ***REMOVED*** manifest..."
"$REPO_ROOT/bin/***REMOVED***-init.sh"

cat <<'EOF'

Stack is up.

Key URLs (host):
- Keycloak:          http://localhost:8080
- ***REMOVED*** Console:     https://localhost:9080   (self-signed; your browser will warn)
- Agent Runner API:  http://localhost:8004
- Cumbaya API:       http://localhost:8003
- AuthZ API:         http://localhost:8002
- Profile API:       http://localhost:8001

EOF
