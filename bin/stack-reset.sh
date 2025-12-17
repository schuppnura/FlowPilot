#!/usr/bin/env bash
set -euo pipefail

# Purpose: Hard reset: stop stack and delete named/anonymous volumes.
# Why: Useful if Keycloak/***REMOVED*** data becomes inconsistent during experiments.
# Side effects: Deletes persisted data for Keycloak and ***REMOVED*** (if volumes are used).

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

docker compose down -v --remove-orphans