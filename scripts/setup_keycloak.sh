#!/bin/bash
# Setup Keycloak after it starts - enables unmanaged attributes and verifies configuration

set -e

echo "Waiting for Keycloak to be ready..."
max_attempts=60
attempt=0

# Try keycloak service name first (for Docker), fallback to localhost (for manual runs)
KEYCLOAK_HOST="${KEYCLOAK_HOST:-keycloak}"
KEYCLOAK_PORT="${KEYCLOAK_PORT:-8443}"

while [ $attempt -lt $max_attempts ]; do
    if curl -k -s "https://${KEYCLOAK_HOST}:${KEYCLOAK_PORT}/realms/master" > /dev/null 2>&1; then
        echo "✓ Keycloak is ready at https://${KEYCLOAK_HOST}:${KEYCLOAK_PORT}"
        break
    fi
    attempt=$((attempt + 1))
    if [ $((attempt % 5)) -eq 0 ]; then
        echo "  Attempt $attempt/$max_attempts - waiting..."
    fi
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo "✗ Keycloak did not become ready in time"
    exit 1
fi

echo ""
echo "Step 1: Enabling unmanaged attributes..."
python3 scripts/enable_unmanaged_attributes.py

echo ""
echo "Step 2: Creating account-console client..."
python3 scripts/ensure_account_console_client.py || echo "  (account-console client may already exist)"

echo ""
echo "Step 3: Assigning realm default scopes..."
python3 scripts/assign_realm_default_scopes.py

echo ""
echo "Step 4: Assigning client scopes..."
python3 scripts/assign_client_scopes.py

echo ""
echo "Step 5: Removing profile scope to prevent PII leakage..."
python3 scripts/remove_profile_scope.py || echo "  (profile scope may already be removed)"

echo ""
echo "Step 6: Verifying Keycloak attributes..."
python3 scripts/verify_keycloak_attributes.py

echo ""
echo "Step 7: Verifying desktop client..."
python3 scripts/verify_desktop_client.py || echo "  (desktop client may need manual configuration)"

echo ""
echo "Step 8: Verifying agent client..."
python3 scripts/verify_agent_client.py || echo "  (agent client may need manual configuration)"

echo ""
echo "Step 9: Ensuring sub claim in access tokens..."
python3 scripts/ensure_sub_in_access_token.py || echo "  (sub mapper may need manual configuration)"

echo ""
echo "Step 10: Configuring persona attribute..."
python3 scripts/configure_persona_attribute.py || echo "  (persona attribute may need manual configuration)"

echo ""
echo "Step 11: Granting agent service account permissions..."
python3 scripts/grant_agent_permissions.py || echo "  (agent permissions may need manual configuration)"

echo ""
echo "✓ Keycloak setup complete!"
