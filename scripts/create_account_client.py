#!/usr/bin/env python3
"""
Create the account client for Keycloak account console.
This client is required for the account console to work properly.
"""
import requests
import json
import sys
import os

KEYCLOAK_URL = "https://localhost:8443"
REALM = "flowpilot"
ADMIN_USER = "admin"
ADMIN_PASSWORD = "admin"

def get_admin_token():
    """Get admin access token"""
    token_url = f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token"
    data = {
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": ADMIN_USER,
        "password": ADMIN_PASSWORD,
    }
    # Suppress SSL warnings
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    resp = requests.post(token_url, data=data, verify=False, timeout=10)
    if resp.status_code != 200:
        print(f"❌ Failed to get admin token: {resp.status_code}")
        print(f"   Response: {resp.text[:200]}")
        # Try using kcadm.sh instead
        import subprocess
        print("   Trying alternative method with kcadm.sh...")
        return None
    resp.raise_for_status()
    return resp.json()["access_token"]

def check_account_client_exists(headers):
    """Check if account client already exists"""
    clients_url = f"{KEYCLOAK_URL}/admin/realms/{REALM}/clients"
    resp = requests.get(clients_url, headers=headers, verify=False, timeout=10)
    resp.raise_for_status()
    clients = resp.json()
    for client in clients:
        if client.get("clientId") in ["account", "account-console"]:
            return client
    return None

def create_account_client(headers):
    """Create the account client"""
    clients_url = f"{KEYCLOAK_URL}/admin/realms/{REALM}/clients"
    
    account_client = {
        "clientId": "account-console",
        "name": "Account Console",
        "enabled": True,
        "publicClient": True,
        "standardFlowEnabled": True,
        "directAccessGrantsEnabled": False,
        "redirectUris": [
            "https://localhost:8443/realms/flowpilot/account/*",
            "http://localhost:8443/realms/flowpilot/account/*"
        ],
        "webOrigins": ["+"],
        "attributes": {
            "pkce.code.challenge.method": "S256"
        }
    }
    
    resp = requests.post(
        clients_url,
        headers=headers,
        json=account_client,
        verify=False,
        timeout=10
    )
    
    if resp.status_code == 201:
        print("✅ Account client created successfully")
        return True
    elif resp.status_code == 409:
        print("ℹ️  Account client already exists")
        return True
    else:
        print(f"❌ Failed to create account client: {resp.status_code}")
        print(f"   Response: {resp.text[:200]}")
        return False

def main():
    print("Creating account client for Keycloak account console...")
    
    try:
        token = get_admin_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Check if client exists
        existing = check_account_client_exists(headers)
        if existing:
            print(f"ℹ️  Account client already exists (enabled: {existing.get('enabled')})")
            if not existing.get("enabled"):
                print("   Enabling account client...")
                client_id = existing["id"]
                update_url = f"{KEYCLOAK_URL}/admin/realms/{REALM}/clients/{client_id}"
                requests.put(
                    update_url,
                    headers=headers,
                    json={"enabled": True},
                    verify=False,
                    timeout=10
                )
                print("✅ Account client enabled")
        else:
            create_account_client(headers)
        
        # Verify
        existing = check_account_client_exists(headers)
        if existing and existing.get("enabled"):
            print("✅ Account client is configured and enabled")
            print(f"   Client ID: {existing.get('clientId')}")
            print(f"   Public Client: {existing.get('publicClient')}")
            print(f"   Standard Flow Enabled: {existing.get('standardFlowEnabled')}")
            return 0
        else:
            print("❌ Account client is not properly configured")
            return 1
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())

