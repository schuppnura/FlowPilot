#!/usr/bin/env bash
set -euo pipefail

# Purpose: Initialize ***REMOVED*** with the Cumbaya manifest.
# Why: The manifest must be loaded before ***REMOVED*** can accept relations/objects.
# Assumptions: ***REMOVED*** container is running; manifest file exists at infra/***REMOVED***/cfg/cumbaya-manifest.yaml

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo ">>> Loading Cumbaya manifest into ***REMOVED***..."
docker compose exec ***REMOVED*** ./***REMOVED*** directory set manifest -P --no-check /app/cfg/cumbaya-manifest.yaml

echo ">>> Verifying manifest..."
docker compose exec ***REMOVED*** ./***REMOVED*** directory get manifest -P --no-check | head -n 15

echo ""
echo "✓ ***REMOVED*** manifest loaded successfully."
