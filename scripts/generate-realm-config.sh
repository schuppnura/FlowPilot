#!/bin/bash
# Generate Keycloak realm configuration with secrets from .env

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

# Generate realm configuration
cat > infra/keycloak/realm-flowpilot.json << EOF
{
  "realm": "flowpilot",
  "enabled": true,
  "registrationAllowed": true,
  "loginWithEmailAllowed": false,
  "duplicateEmailsAllowed": true,
  "users": [
    {
      "username": "traveler1",
      "enabled": true,
      "firstName": "Demo",
      "credentials": [
        {
          "type": "password",
          "value": "$DEMO_USER_PASSWORD",
          "temporary": false
        }
      ]
    }
  ],
  "clients": [
    {
      "clientId": "flowpilot-desktop",
      "enabled": true,
      "protocol": "openid-connect",
      "publicClient": true,
      "standardFlowEnabled": true,
      "directAccessGrantsEnabled": false,
      "serviceAccountsEnabled": false,
      "redirectUris": [
        "flowpilot-demo://oauth/callback",
        "http://localhost:9999/callback"
      ],
      "webOrigins": [
        "http://localhost:9999"
      ],
      "attributes": {
        "pkce.code.challenge.method": "S256"
      }
    },
    {
      "clientId": "flowpilot-agent",
      "enabled": true,
      "protocol": "openid-connect",
      "publicClient": false,
      "serviceAccountsEnabled": true,
      "standardFlowEnabled": false,
      "directAccessGrantsEnabled": false,
      "secret": "$KEYCLOAK_CLIENT_SECRET"
    },
    {
      "clientId": "flowpilot-testing",
      "name": "FlowPilot Testing Script",
      "description": "OAuth client for user_based_testing.py script",
      "enabled": true,
      "protocol": "openid-connect",
      "publicClient": true,
      "standardFlowEnabled": true,
      "directAccessGrantsEnabled": false,
      "serviceAccountsEnabled": false,
      "redirectUris": [
        "http://localhost:8765/callback"
      ],
      "webOrigins": [
        "http://localhost:8765"
      ],
      "attributes": {
        "pkce.code.challenge.method": "S256"
      }
    }
  ]
}
EOF

echo "✅ Generated infra/keycloak/realm-flowpilot.json with secrets from .env"
