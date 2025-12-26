#!/usr/bin/env python3
"""
Assign default client scopes to the realm.
This ensures standard scopes like 'openid' and 'profile' are available.
"""
import requests
import sys
import os
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

KEYCLOAK_URL = "https://localhost:8443"
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

def get_realm_default_scopes(headers):
    """Get realm default client scopes"""
    resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/default-default-client-scopes',
        headers=headers,
        verify=False,
        timeout=10
    )
    resp.raise_for_status()
    return [s['id'] for s in resp.json()]

def assign_realm_default_scope(headers, scope_id):
    """Assign a scope as realm default"""
    resp = requests.put(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/default-default-client-scopes/{scope_id}',
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

def copy_scope_from_master(headers, scope_name):
    """Copy a client scope from master realm to flowpilot realm"""
    # Get scope from master realm
    resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/master/client-scopes',
        headers=headers,
        verify=False,
        timeout=10
    )
    resp.raise_for_status()
    master_scopes = resp.json()
    master_scope = next((s for s in master_scopes if s['name'] == scope_name), None)
    if not master_scope:
        return None
    
    # Get scope details including protocol mappers
    scope_detail_resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/master/client-scopes/{master_scope["id"]}',
        headers=headers,
        verify=False,
        timeout=10
    )
    scope_detail_resp.raise_for_status()
    scope_config = scope_detail_resp.json()
    
    # Get protocol mappers
    mappers_resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/master/client-scopes/{master_scope["id"]}/protocol-mappers/models',
        headers=headers,
        verify=False,
        timeout=10
    )
    mappers_resp.raise_for_status()
    mappers = mappers_resp.json()
    
    # Create scope in flowpilot realm
    create_config = {
        "name": scope_config["name"],
        "description": scope_config.get("description", ""),
        "protocol": scope_config.get("protocol", "openid-connect"),
        "attributes": scope_config.get("attributes", {})
    }
    
    create_resp = requests.post(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes',
        headers=headers,
        json=create_config,
        verify=False,
        timeout=10
    )
    if create_resp.status_code == 201:
        new_scope_id = get_client_scope_id(headers, scope_name)
        # Add protocol mappers
        for mapper in mappers:
            mapper_config = {
                "name": mapper["name"],
                "protocol": mapper["protocol"],
                "protocolMapper": mapper["protocolMapper"],
                "consentRequired": mapper.get("consentRequired", False),
                "config": mapper.get("config", {})
            }
            requests.post(
                f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes/{new_scope_id}/protocol-mappers/models',
                headers=headers,
                json=mapper_config,
                verify=False,
                timeout=10
            )
        return new_scope_id
    elif create_resp.status_code == 409:
        # Scope already exists
        return get_client_scope_id(headers, scope_name)
    return None

def main():
    print("Assigning realm default client scopes...")
    
    # Standard scopes that should be realm defaults (openid is built-in, not a client scope)
    # No realm default scopes needed - persona scope is assigned per-client
    required_scopes = []
    
    try:
        token = get_admin_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # Get current realm default scopes
        current_scopes = get_realm_default_scopes(headers)
        print(f"Current realm default scopes: {len(current_scopes)}")
        
        # Assign required scopes
        for scope_name in required_scopes:
            scope_id = get_client_scope_id(headers, scope_name)
            if not scope_id:
                print(f"  {scope_name} scope not found, copying from master realm...")
                scope_id = copy_scope_from_master(headers, scope_name)
                if not scope_id:
                    print(f"✗ Failed to copy {scope_name} scope")
                    continue
                print(f"✓ Copied {scope_name} scope from master realm")
            
            if scope_id in current_scopes:
                print(f"✓ {scope_name} already assigned as realm default")
            else:
                print(f"Assigning {scope_name} as realm default...")
                if assign_realm_default_scope(headers, scope_id):
                    print(f"✓ {scope_name} assigned as realm default")
                else:
                    print(f"✗ Failed to assign {scope_name}")
        
        print("\n✓ Realm default scopes configured!")
        print("  Note: 'openid' is a built-in OIDC scope and doesn't need to be assigned")
        return 0
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

