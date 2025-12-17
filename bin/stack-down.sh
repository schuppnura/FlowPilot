#!/usr/bin/env bash
set -euo pipefail

# Purpose: Stop the stack without deleting volumes.
# Why: Fast stop/start cycles during development.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

docker compose down