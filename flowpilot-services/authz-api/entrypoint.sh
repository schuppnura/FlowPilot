#!/bin/sh
set -e

OPA_ADDR="${OPA_ADDR:-127.0.0.1:8181}"
OPA_POLICY_DIR="${OPA_POLICY_DIR:-/policies}"

# Run OPA in the background (watch policies for changes)
opa run --server --addr "${OPA_ADDR}" --watch "${OPA_POLICY_DIR}" &

# Start your API
exec python /app/main.py