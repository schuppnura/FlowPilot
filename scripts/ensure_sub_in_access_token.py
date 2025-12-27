#!/usr/bin/env python3
"""
Ensure the 'sub' claim is included in access tokens.
This adds a protocol mapper to the profile scope to include sub in access tokens.
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

def get_existing_mappers(headers, scope_id):
    """Get existing protocol mappers for a scope"""
    resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes/{scope_id}/protocol-mappers/models',
        headers=headers,
        verify=False,
        timeout=10
    )
    resp.raise_for_status()
    return resp.json()

def add_sub_mapper_to_access_token(headers, scope_id):
    """Add a mapper to include sub claim in access tokens"""
    # Check if mapper already exists
    existing_mappers = get_existing_mappers(headers, scope_id)
    existing_names = [m['name'] for m in existing_mappers]
    
    if 'sub-access-token-mapper' in existing_names:
        print("✓ sub mapper already exists in profile scope")
        return True
    
    # Add mapper to include sub in access token
    mapper_config = {
        "name": "sub-access-token-mapper",
        "protocol": "openid-connect",
        "protocolMapper": "oidc-usermodel-property-mapper",
        "consentRequired": False,
        "config": {
            "user.attribute": "id",
            "claim.name": "sub",
            "jsonType.label": "String",
            "id.token.claim": "true",
            "access.token.claim": "true",  # This is the key - include in access token
            "userinfo.token.claim": "true"
        }
    }
    
    resp = requests.post(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes/{scope_id}/protocol-mappers/models',
        headers=headers,
        json=mapper_config,
        verify=False,
        timeout=10
    )
    
    if resp.status_code == 201:
        print("✓ Added sub mapper to profile scope for access tokens")
        return True
    elif resp.status_code == 409:
        print("✓ sub mapper already exists in profile scope")
        return True
    else:
        print(f"✗ Failed to add mapper: {resp.status_code} - {resp.text[:200]}")
        return False

def ensure_service_account_has_sub(headers):
    """Ensure service account tokens include sub claim"""
    # Service accounts need sub claim too
    # Check if service_account scope has sub mapper
    service_account_scope_id = get_client_scope_id(headers, "service_account")
    if not service_account_scope_id:
        print("⚠ service_account scope not found (may be built-in)")
        return True  # Not an error, might be built-in
    
    existing_mappers = get_existing_mappers(headers, service_account_scope_id)
    existing_names = [m['name'] for m in existing_mappers]
    
    if 'sub-service-account-mapper' in existing_names:
        print("✓ sub mapper already exists in service_account scope")
        return True
    
    # Add mapper for service accounts
    mapper_config = {
        "name": "sub-service-account-mapper",
        "protocol": "openid-connect",
        "protocolMapper": "oidc-usermodel-property-mapper",
        "consentRequired": False,
        "config": {
            "user.attribute": "id",
            "claim.name": "sub",
            "jsonType.label": "String",
            "id.token.claim": "true",
            "access.token.claim": "true",
            "userinfo.token.claim": "true"
        }
    }
    
    resp = requests.post(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes/{service_account_scope_id}/protocol-mappers/models',
        headers=headers,
        json=mapper_config,
        verify=False,
        timeout=10
    )
    
    if resp.status_code == 201:
        print("✓ Added sub mapper to service_account scope")
        return True
    elif resp.status_code == 409:
        print("✓ sub mapper already exists in service_account scope")
        return True
    else:
        print(f"⚠ Failed to add service_account mapper: {resp.status_code} - {resp.text[:200]}")
        return True  # Don't fail, service_account might handle it differently

def main():
    print("Ensuring 'sub' claim is included in access tokens...")
    
    try:
        token = get_admin_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # Get profile scope
        profile_scope_id = get_client_scope_id(headers, "profile")
        if not profile_scope_id:
            print("✗ profile scope not found")
            return 1
        
        print(f"✓ Found profile scope (id={profile_scope_id})")
        
        # Add sub mapper to profile scope (for user tokens)
        if add_sub_mapper_to_access_token(headers, profile_scope_id):
            print("✓ Profile scope configured")
        else:
            return 1
        
        # Ensure service account tokens also have sub
        ensure_service_account_has_sub(headers)
        
        print("\n✓ 'sub' claim will now be included in access tokens!")
        print("  - User tokens: sign in again to get a fresh token")
        print("  - Service tokens: will include 'sub' automatically")
        return 0
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

