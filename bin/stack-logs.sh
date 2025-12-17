#!/usr/bin/env bash
set -euo pipefail

# Purpose: Tail logs for the whole stack or a specific service.
# Usage:
#   ./bin/stack-logs.sh
#   ./bin/stack-logs.sh authz-api

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ $# -gt 0 ]]; then
  docker compose logs -f --tail=200 "$1"
else
  docker compose logs -f --tail=200
fi