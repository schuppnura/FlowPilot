#!/usr/bin/env python3
"""
Update the flowpilot-agent client secret in Keycloak to match .env file.
"""
import requests
import sys
import os
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

KEYCLOAK_URL = "https://localhost:8443"
REALM = "flowpilot"

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
CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET") or env_vars.get("KEYCLOAK_CLIENT_SECRET")

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
        print(f"Response: {resp.text}")
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

def update_client_secret(headers, client_uuid, secret):
    """Update client secret"""
    resp = requests.put(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/clients/{client_uuid}/client-secret',
        headers=headers,
        json={'value': secret, 'temporary': False},
        verify=False,
        timeout=10
    )
    return resp.status_code == 204

def main():
    if not CLIENT_SECRET:
        print("✗ KEYCLOAK_CLIENT_SECRET not found in .env or environment")
        return 1
    
    print("Updating flowpilot-agent client secret...")
    
    try:
        token = get_admin_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        client_uuid = get_client_id(headers, "flowpilot-agent")
        if not client_uuid:
            print("✗ flowpilot-agent client not found")
            return 1
        
        print(f"✓ Found flowpilot-agent client (id={client_uuid})")
        
        if update_client_secret(headers, client_uuid, CLIENT_SECRET):
            print("✓ Updated client secret")
            return 0
        else:
            print("✗ Failed to update client secret")
            return 1
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

