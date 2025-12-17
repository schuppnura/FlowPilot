#!/usr/bin/env bash
set -euo pipefail

# Purpose: Show a compact view of what is running and which ports are mapped.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

docker compose ps