#!/bin/bash
# Generate Keycloak realm configuration with secrets from .env
# Uses the template file and replaces placeholders with actual values

set -e

# Load environment variables from .env
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
else
    echo "Error: .env file not found. Copy .env.example to .env first."
    exit 1
fi

# Validate required variables
if [ -z "$KEYCLOAK_CLIENT_SECRET" ] || [ -z "$DEMO_USER_PASSWORD" ]; then
    echo "Error: Required environment variables not set in .env"
    exit 1
fi

# Check if template exists
TEMPLATE_FILE="infra/keycloak/realm-flowpilot.json.template"
if [ ! -f "$TEMPLATE_FILE" ]; then
    echo "Error: Template file not found: $TEMPLATE_FILE"
    exit 1
fi

# Generate realm configuration from template by replacing placeholders
sed -e "s|DEMO_USER_PASSWORD_HERE|$DEMO_USER_PASSWORD|g" \
    -e "s|KEYCLOAK_CLIENT_SECRET_HERE|$KEYCLOAK_CLIENT_SECRET|g" \
    "$TEMPLATE_FILE" > infra/keycloak/realm-flowpilot.json

echo "✅ Generated infra/keycloak/realm-flowpilot.json from template with secrets from .env"
