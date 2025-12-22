#!/usr/bin/env python3
"""
Verify and configure the flowpilot-desktop client for user authentication.
This ensures the client has the audience mapper for proper token validation.
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

def verify_desktop_client(headers):
    """Verify flowpilot-desktop client configuration"""
    client_uuid = get_client_id(headers, "flowpilot-desktop")
    if not client_uuid:
        print("✗ flowpilot-desktop client not found")
        return False
    
    print(f"✓ Found flowpilot-desktop client (id={client_uuid})")
    
    # Check for audience mapper
    resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/clients/{client_uuid}/protocol-mappers/models',
        headers=headers,
        verify=False,
        timeout=10
    )
    resp.raise_for_status()
    mappers = resp.json()
    
    has_audience_mapper = any(m.get("name") == "audience-mapper" for m in mappers)
    if not has_audience_mapper:
        print("⚠ Missing audience mapper, creating...")
        mapper_config = {
            "name": "audience-mapper",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-audience-mapper",
            "consentRequired": False,
            "config": {
                "included.client.audience": "flowpilot-desktop",
                "id.token.claim": "true",
                "access.token.claim": "true"
            }
        }
        resp = requests.post(
            f'{KEYCLOAK_URL}/admin/realms/{REALM}/clients/{client_uuid}/protocol-mappers/models',
            headers=headers,
            json=mapper_config,
            verify=False,
            timeout=10
        )
        if resp.status_code == 201:
            print("✓ Created audience mapper")
        else:
            print(f"⚠ Failed to create mapper: {resp.status_code} - {resp.text[:200]}")
            return False
    else:
        print("✓ Audience mapper exists")
    
    print("✓ flowpilot-desktop client is properly configured")
    return True

def main():
    print("Verifying flowpilot-desktop client configuration...")
    
    try:
        token = get_admin_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        if verify_desktop_client(headers):
            print("\n✓ Desktop client verification complete!")
            return 0
        else:
            print("\n✗ Desktop client verification failed")
            return 1
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

