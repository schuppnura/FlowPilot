#!/bin/bash
# Validate that all service environment config files have required variables
# This prevents deployment failures due to missing HTTP configuration

set -e

REQUIRED_VARS=(
    "HTTP_DEFAULT_TIMEOUT"
    "HTTP_VERIFY_TLS"
)

CONFIG_DIR="cloud-run-envs"
ERRORS=0

echo "Validating environment configuration files..."
echo ""

for config_file in "$CONFIG_DIR"/*.yaml; do
    service_name=$(basename "$config_file" .yaml)
    for var in "${REQUIRED_VARS[@]}"; do
        if ! grep -q "^${var}:" "$config_file"; then
            echo "  ✗ ERROR: Missing $var in $config_file"
            ERRORS=$((ERRORS + 1))
        fi
    done
done

if [ $ERRORS -gt 0 ]; then
    echo "❌ Validation failed with $ERRORS error(s)"
    echo ""
    echo "Required variables for all services:"
    for var in "${REQUIRED_VARS[@]}"; do
        echo "  - $var"
    done
    echo ""
    echo "Add missing variables to the appropriate config files in $CONFIG_DIR/"
    exit 1
fi

echo "All environment configurations are valid!"
exit 0
