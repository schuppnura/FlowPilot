#!/usr/bin/env python3
"""
Remove the 'profile' scope from flowpilot-desktop client to prevent PII leakage.

The profile scope includes PII claims like name, preferred_username, given_name, family_name.
We only want: sub, persona, and autobook attributes in access tokens.
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
    return resp.json()

def remove_default_scope(headers, client_uuid, scope_id):
    """Remove a scope from client's default scopes"""
    resp = requests.delete(
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
    print("Removing 'profile' scope from flowpilot-desktop client to prevent PII leakage...")
    
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
        
        # Check current default scopes
        current_scopes = get_client_default_scopes(headers, client_uuid)
        current_scope_names = [(s['id'], s['name']) for s in current_scopes]
        
        print(f"\nCurrent default client scopes:")
        for scope_id, scope_name in current_scope_names:
            print(f"  - {scope_name}")
        
        # Find and remove profile scope
        profile_scope_id = None
        for scope_id, scope_name in current_scope_names:
            if scope_name == 'profile':
                profile_scope_id = scope_id
                break
        
        if profile_scope_id:
            print(f"\n✓ Found 'profile' scope, removing...")
            if remove_default_scope(headers, client_uuid, profile_scope_id):
                print("✓ Successfully removed 'profile' scope")
            else:
                print("✗ Failed to remove 'profile' scope")
                return 1
        else:
            print("\n✓ 'profile' scope is not assigned (already removed)")
        
        # Verify final state
        final_scopes = get_client_default_scopes(headers, client_uuid)
        final_scope_names = [s['name'] for s in final_scopes]
        
        print(f"\nFinal default client scopes:")
        for scope_name in final_scope_names:
            print(f"  - {scope_name}")
        
        # Verify profile is not present
        if 'profile' in final_scope_names:
            print("\n✗ ERROR: 'profile' scope is still present!")
            return 1
        
        print("\n✓ SUCCESS: Access tokens will no longer contain PII from profile scope")
        print("  Tokens will only contain: sub, persona, autobook attributes")
        print("  Users must log in again to get new tokens without PII")
        
        return 0
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
