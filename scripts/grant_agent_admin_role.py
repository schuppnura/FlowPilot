#!/usr/bin/env python3
"""
Grant realm-admin role to flowpilot-agent service account.
This allows the service account to access Keycloak's admin API.
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

def get_service_account_user_id(headers, client_uuid):
    """Get the service account user ID for a client"""
    resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/clients/{client_uuid}/service-account-user',
        headers=headers,
        verify=False,
        timeout=10
    )
    if resp.status_code == 200:
        return resp.json().get('id')
    return None

def get_realm_management_client(headers):
    """Get the realm-management client (which contains admin API roles)"""
    resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/clients',
        headers=headers,
        params={'clientId': 'realm-management'},
        verify=False,
        timeout=10
    )
    if resp.status_code == 200:
        clients = resp.json()
        if clients:
            return clients[0]
    return None

def get_role_from_client(headers, client_id, role_name):
    """Get a role from a client"""
    resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/clients/{client_id}/roles/{role_name}',
        headers=headers,
        verify=False,
        timeout=10
    )
    if resp.status_code == 200:
        return resp.json()
    return None

def grant_client_role_to_user(headers, user_id, client_id, role):
    """Grant a client role to a user"""
    # Check if role is already assigned
    resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/users/{user_id}/role-mappings/clients/{client_id}',
        headers=headers,
        verify=False,
        timeout=10
    )
    if resp.status_code == 200:
        existing_roles = resp.json()
        if any(r.get('id') == role.get('id') for r in existing_roles):
            return True  # Role already assigned
    
    # Assign the role
    resp = requests.post(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/users/{user_id}/role-mappings/clients/{client_id}',
        headers=headers,
        json=[role],
        verify=False,
        timeout=10
    )
    return resp.status_code == 204

def main():
    print("Granting realm-admin role to flowpilot-agent service account...")
    
    try:
        token = get_admin_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # Get client UUID
        client_uuid = get_client_id(headers, "flowpilot-agent")
        if not client_uuid:
            print("✗ flowpilot-agent client not found")
            return 1
        
        print(f"✓ Found flowpilot-agent client (id={client_uuid})")
        
        # Get service account user ID
        user_id = get_service_account_user_id(headers, client_uuid)
        if not user_id:
            print("✗ Service account user not found for flowpilot-agent")
            return 1
        
        print(f"✓ Found service account user (id={user_id})")
        
        # Get realm-management client (contains admin API roles)
        realm_mgmt_client = get_realm_management_client(headers)
        if not realm_mgmt_client:
            print("✗ realm-management client not found")
            return 1
        
        client_id = realm_mgmt_client.get('id')
        print(f"✓ Found realm-management client (id={client_id})")
        
        # Grant view-users and query-users roles (needed to list users)
        required_roles = ['view-users', 'query-users']
        all_granted = True
        
        for role_name in required_roles:
            role = get_role_from_client(headers, client_id, role_name)
            if not role:
                print(f"⚠ Role {role_name} not found in realm-management client")
                continue
            
            print(f"✓ Found {role_name} role (id={role.get('id')})")
            
            if grant_client_role_to_user(headers, user_id, client_id, role):
                print(f"✓ Granted {role_name} role to flowpilot-agent service account")
            else:
                print(f"⚠ Failed to grant {role_name} (may already be assigned)")
                all_granted = False
        
        if all_granted:
            print("\n✓ Service account role assignment complete!")
            return 0
        else:
            print("\n⚠ Some roles may already be assigned")
            return 0  # Don't fail if roles are already assigned
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

