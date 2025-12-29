#!/usr/bin/env python3
"""
Ensure the account-console client exists and is properly configured.
This script uses the Keycloak Admin API to create/update the client.
"""
import requests
import json
import sys
import os
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Get Keycloak host/port from environment (for Docker compatibility)
KEYCLOAK_HOST = os.getenv("KEYCLOAK_HOST", "localhost")
KEYCLOAK_PORT = os.getenv("KEYCLOAK_PORT", "8443")
KEYCLOAK_URL = f"https://{KEYCLOAK_HOST}:{KEYCLOAK_PORT}"
REALM = "flowpilot"

# Try to get admin credentials from environment or .env file
def load_env_file():
    """Load .env file if it exists"""
    env_vars = {}
    env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip().strip('"').strip("'")
    return env_vars

env_vars = load_env_file()
ADMIN_USER = os.getenv("KEYCLOAK_ADMIN_USERNAME") or env_vars.get("KEYCLOAK_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("KEYCLOAK_ADMIN_PASSWORD") or env_vars.get("KEYCLOAK_ADMIN_PASSWORD", "admin")

def get_admin_token():
    """Get admin access token"""
    token_url = f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token"
    data = {
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": ADMIN_USER,
        "password": ADMIN_PASSWORD,
    }
    resp = requests.post(token_url, data=data, verify=False, timeout=10)
    if resp.status_code != 200:
        print(f"❌ Failed to get admin token: {resp.status_code}")
        print(f"   Response: {resp.text[:200]}")
        return None
    return resp.json()["access_token"]

def get_account_console_client(headers):
    """Get account-console client if it exists"""
    clients_url = f"{KEYCLOAK_URL}/admin/realms/{REALM}/clients"
    resp = requests.get(clients_url, headers=headers, verify=False, timeout=10)
    if resp.status_code != 200:
        print(f"❌ Failed to get clients: {resp.status_code}")
        return None
    clients = resp.json()
    for client in clients:
        if client.get("clientId") == "account-console":
            return client
    return None

def create_or_update_account_console_client(headers, existing=None):
    """Create or update the account-console client"""
    account_client = {
        "clientId": "account-console",
        "name": "Account Console",
        "enabled": True,
        "publicClient": True,
        "standardFlowEnabled": True,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
        "fullScopeAllowed": True,
        "redirectUris": [
            "https://localhost:8443/realms/flowpilot/account/*",
            "http://localhost:8443/realms/flowpilot/account/*"
        ],
        "webOrigins": ["+"],
        "attributes": {
            "pkce.code.challenge.method": "S256"
        },
        "defaultClientScopes": [
            "web-origins",
            "acr",
            "roles",
            "profile",
            "openid"
        ]
    }
    
    if existing:
        # Update existing client
        client_id = existing["id"]
        update_url = f"{KEYCLOAK_URL}/admin/realms/{REALM}/clients/{client_id}"
        resp = requests.put(
            update_url,
            headers=headers,
            json=account_client,
            verify=False,
            timeout=10
        )
        if resp.status_code in [200, 204]:
            print("✅ Updated account-console client")
            return True
        else:
            print(f"❌ Failed to update client: {resp.status_code}")
            print(f"   Response: {resp.text[:200]}")
            return False
    else:
        # Create new client
        create_url = f"{KEYCLOAK_URL}/admin/realms/{REALM}/clients"
        resp = requests.post(
            create_url,
            headers=headers,
            json=account_client,
            verify=False,
            timeout=10
        )
        if resp.status_code == 201:
            print("✅ Created account-console client")
            return True
        elif resp.status_code == 409:
            print("ℹ️  Account-console client already exists")
            return True
        else:
            print(f"❌ Failed to create client: {resp.status_code}")
            print(f"   Response: {resp.text[:200]}")
            return False

def main():
    print("Ensuring account-console client is configured...")
    
    token = get_admin_token()
    if not token:
        print("❌ Could not authenticate with Keycloak")
        return 1
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    existing = get_account_console_client(headers)
    if existing:
        print(f"ℹ️  Found existing account-console client (enabled: {existing.get('enabled')})")
        if not existing.get("fullScopeAllowed"):
            print("   Updating client to enable fullScopeAllowed...")
            create_or_update_account_console_client(headers, existing)
    else:
        print("   Creating account-console client...")
        create_or_update_account_console_client(headers)
    
    # Verify
    existing = get_account_console_client(headers)
    if existing and existing.get("enabled") and existing.get("fullScopeAllowed"):
        print("✅ Account-console client is properly configured")
        print(f"   Client ID: {existing.get('clientId')}")
        print(f"   Full Scope Allowed: {existing.get('fullScopeAllowed')}")
        return 0
    else:
        print("❌ Account-console client is not properly configured")
        return 1

if __name__ == "__main__":
    sys.exit(main())

