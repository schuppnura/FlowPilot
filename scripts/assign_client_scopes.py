#!/usr/bin/env python3
"""
Assign client scopes to the flowpilot-desktop client.
This ensures the autobook scope is available for the OAuth flow.
"""
import requests
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
ADMIN_PASS = os.getenv("KEYCLOAK_ADMIN_PASSWORD") or env_vars.get("KEYCLOAK_ADMIN_PASSWORD", "admin")

def get_admin_token():
    """Get admin access token"""
    resp = requests.post(
        f'{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token',
        data={
            'client_id': 'admin-cli',
            'username': ADMIN_USER,
            'password': ADMIN_PASS,
            'grant_type': 'password'
        },
        verify=False,
        timeout=10
    )
    if resp.status_code != 200:
        print(f"✗ Authentication failed: {resp.status_code}")
        print(f"   Response: {resp.text[:200]}")
        raise RuntimeError(f"Failed to authenticate: {resp.status_code}")
    
    token_data = resp.json()
    if 'access_token' not in token_data:
        raise RuntimeError(f"Token response missing access_token: {token_data}")
    
    return token_data['access_token']

def get_client_id(headers, client_id_str):
    """Get client UUID by clientId string"""
    resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/clients',
        headers=headers,
        params={'clientId': client_id_str},
        verify=False,
        timeout=10
    )
    resp.raise_for_status()
    clients = resp.json()
    if clients:
        return clients[0]['id']
    return None

def get_client_scope_id(headers, scope_name):
    """Get client scope UUID by name"""
    resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes',
        headers=headers,
        verify=False,
        timeout=10
    )
    resp.raise_for_status()
    scopes = resp.json()
    for scope in scopes:
        if scope['name'] == scope_name:
            return scope['id']
    return None

def get_client_default_scopes(headers, client_uuid):
    """Get default client scopes for a client"""
    resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/clients/{client_uuid}/default-client-scopes',
        headers=headers,
        verify=False,
        timeout=10
    )
    resp.raise_for_status()
    return [s['id'] for s in resp.json()]

def assign_default_scope(headers, client_uuid, scope_id):
    """Assign a scope as default for a client"""
    resp = requests.put(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/clients/{client_uuid}/default-client-scopes/{scope_id}',
        headers=headers,
        verify=False,
        timeout=10
    )
    if resp.status_code == 204:
        return True
    elif resp.status_code == 404:
        return False
    resp.raise_for_status()
    return True

def main():
    print("Assigning client scopes to flowpilot-desktop client...")
    
    try:
        token = get_admin_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # Get flowpilot-desktop client UUID
        client_uuid = get_client_id(headers, "flowpilot-desktop")
        if not client_uuid:
            print("✗ flowpilot-desktop client not found")
            return 1
        print(f"✓ Found flowpilot-desktop client (id={client_uuid})")
        
        # Get all required scopes - these should match the realm template
        required_scope_names = ["autobook", "web-origins", "acr", "roles", "profile"]
        
        # Check current default scopes
        current_scopes = get_client_default_scopes(headers, client_uuid)
        current_scope_names = []
        for scope_id in current_scopes:
            scope_resp = requests.get(
                f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes/{scope_id}',
                headers=headers,
                verify=False,
                timeout=10
            )
            if scope_resp.status_code == 200:
                current_scope_names.append(scope_resp.json()['name'])
        
        print(f"Current client scopes: {', '.join(current_scope_names)}")
        
        # Assign all required scopes
        assigned_count = 0
        for scope_name in required_scope_names:
            scope_id = get_client_scope_id(headers, scope_name)
            if not scope_id:
                print(f"⚠ {scope_name} scope not found (may be built-in)")
                continue
            
            if scope_id in current_scopes:
                print(f"✓ {scope_name} already assigned")
            else:
                print(f"Assigning {scope_name} as default...")
                if assign_default_scope(headers, client_uuid, scope_id):
                    print(f"✓ {scope_name} assigned")
                    assigned_count += 1
                else:
                    print(f"✗ Failed to assign {scope_name}")
        
        if assigned_count > 0:
            print(f"\n✓ Assigned {assigned_count} new scope(s) to client")
        else:
            print("\n✓ All required scopes are already assigned")
        
        return 0
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

