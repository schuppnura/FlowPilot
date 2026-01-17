#!/usr/bin/env python3
"""
Bootstrap Keycloak realm with clients and users.
Creates the flowpilot realm, clients, and basic configuration.
"""
import os
import sys
import requests
import urllib3

urllib3.disable_warnings()

# Configuration
KEYCLOAK_URL = "https://localhost:8443"
REALM_NAME = "flowpilot"
ADMIN_USERNAME = os.environ.get("KEYCLOAK_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("KEYCLOAK_ADMIN_PASSWORD")
AGENT_CLIENT_SECRET = os.environ.get("AGENT_CLIENT_SECRET", "dev-secret-change-in-production")

if not ADMIN_PASSWORD:
    print("Error: KEYCLOAK_ADMIN_PASSWORD environment variable not set")
    sys.exit(1)


def get_admin_token():
    """Get admin access token"""
    response = requests.post(
        f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD,
        },
        verify=False,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def create_realm(token):
    """Create flowpilot realm"""
    realm_config = {
        "realm": REALM_NAME,
        "enabled": True,
        "displayName": "FlowPilot",
        "sslRequired": "none",
        "registrationAllowed": False,
        "loginWithEmailAllowed": True,
        "duplicateEmailsAllowed": False,
        "resetPasswordAllowed": True,
        "editUsernameAllowed": False,
        "bruteForceProtected": True,
    }

    response = requests.post(
        f"{KEYCLOAK_URL}/admin/realms",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=realm_config,
        verify=False,
    )

    if response.status_code == 201:
        print(f"✓ Created realm: {REALM_NAME}")
        return True
    elif response.status_code == 409:
        print(f"ℹ️  Realm {REALM_NAME} already exists")
        return True
    else:
        print(f"✗ Failed to create realm: {response.status_code} - {response.text}")
        return False


def create_desktop_client(token):
    """Create flowpilot-desktop client (public client for desktop app)"""
    client_config = {
        "clientId": "flowpilot-desktop",
        "enabled": True,
        "publicClient": True,
        "directAccessGrantsEnabled": True,  # Enable direct access grants (Resource Owner Password Credentials)
        "standardFlowEnabled": True,  # Enable authorization code flow
        "implicitFlowEnabled": False,
        "redirectUris": ["http://localhost:*", "https://localhost:*"],
        "webOrigins": ["*"],
        "protocol": "openid-connect",
        "attributes": {
            "pkce.code.challenge.method": "S256",
        },
    }

    response = requests.post(
        f"{KEYCLOAK_URL}/admin/realms/{REALM_NAME}/clients",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=client_config,
        verify=False,
    )

    if response.status_code == 201:
        print("✓ Created flowpilot-desktop client")
        return True
    elif response.status_code == 409:
        print("ℹ️  flowpilot-desktop client already exists")
        return True
    else:
        print(f"✗ Failed to create desktop client: {response.status_code} - {response.text}")
        return False


def create_agent_client(token):
    """Create flowpilot-agent service account client"""
    client_config = {
        "clientId": "flowpilot-agent",
        "enabled": True,
        "publicClient": False,
        "serviceAccountsEnabled": True,  # Enable service account (client credentials flow)
        "directAccessGrantsEnabled": False,
        "standardFlowEnabled": False,
        "implicitFlowEnabled": False,
        "secret": AGENT_CLIENT_SECRET,
        "protocol": "openid-connect",
        "attributes": {
            "access.token.lifespan": "300",
        },
    }

    response = requests.post(
        f"{KEYCLOAK_URL}/admin/realms/{REALM_NAME}/clients",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=client_config,
        verify=False,
    )

    if response.status_code == 201:
        print(f"✓ Created flowpilot-agent client with secret: {AGENT_CLIENT_SECRET}")
        return True
    elif response.status_code == 409:
        print("ℹ️  flowpilot-agent client already exists")
        # Update the secret if it already exists
        clients = requests.get(
            f"{KEYCLOAK_URL}/admin/realms/{REALM_NAME}/clients",
            headers={"Authorization": f"Bearer {token}"},
            verify=False,
        ).json()
        agent_client = next((c for c in clients if c["clientId"] == "flowpilot-agent"), None)
        if agent_client:
            # Update client secret
            requests.put(
                f"{KEYCLOAK_URL}/admin/realms/{REALM_NAME}/clients/{agent_client['id']}/client-secret",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"type": "secret", "value": AGENT_CLIENT_SECRET},
                verify=False,
            )
            print(f"✓ Updated flowpilot-agent client secret")
        return True
    else:
        print(f"✗ Failed to create agent client: {response.status_code} - {response.text}")
        return False


def main():
    print("=" * 70)
    print("Keycloak Realm Bootstrap")
    print("=" * 70)
    print(f"Realm: {REALM_NAME}")
    print(f"Keycloak URL: {KEYCLOAK_URL}")
    print()

    try:
        # Get admin token
        print("Step 1: Authenticating as admin...")
        token = get_admin_token()
        print("✓ Admin authentication successful")
        print()

        # Create realm
        print("Step 2: Creating realm...")
        if not create_realm(token):
            sys.exit(1)
        print()

        # Create desktop client
        print("Step 3: Creating desktop client...")
        if not create_desktop_client(token):
            sys.exit(1)
        print()

        # Create agent client
        print("Step 4: Creating agent service account...")
        if not create_agent_client(token):
            sys.exit(1)
        print()

        print("=" * 70)
        print("✓ Keycloak realm bootstrap complete!")
        print("=" * 70)
        print()
        print("Next steps:")
        print("  1. Run: python3 scripts/seed_keycloak_users.py")
        print("  2. Restart services: docker compose restart")
        print("  3. Run tests: python3 flowpilot-testing/regression_test_keycloak.py")

    except requests.exceptions.RequestException as e:
        print(f"✗ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
