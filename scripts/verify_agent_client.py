#!/usr/bin/env python3
"""
Verify and configure the flowpilot-agent client for service-to-service authentication.
This ensures the client exists and has service account enabled with proper audience.
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

def verify_agent_client(headers):
    """Verify flowpilot-agent client configuration"""
    client_uuid = get_client_id(headers, "flowpilot-agent")
    if not client_uuid:
        print("✗ flowpilot-agent client not found")
        return False
    
    # Get client details
    resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/clients/{client_uuid}',
        headers=headers,
        verify=False,
        timeout=10
    )
    resp.raise_for_status()
    client = resp.json()
    
    print(f"✓ Found flowpilot-agent client (id={client_uuid})")
    
    # Check required settings
    issues = []
    if not client.get("serviceAccountsEnabled", False):
        issues.append("serviceAccountsEnabled should be True")
    if not client.get("enabled", True):
        issues.append("client should be enabled")
    
    if issues:
        print(f"⚠ Issues found:")
        for issue in issues:
            print(f"  - {issue}")
        
        # Fix issues
        print("Fixing issues...")
        update_data = {}
        if not client.get("serviceAccountsEnabled", False):
            update_data["serviceAccountsEnabled"] = True
        if not client.get("enabled", True):
            update_data["enabled"] = True
        
        if update_data:
            resp = requests.put(
                f'{KEYCLOAK_URL}/admin/realms/{REALM}/clients/{client_uuid}',
                headers=headers,
                json=update_data,
                verify=False,
                timeout=10
            )
            if resp.status_code == 204:
                print("✓ Updated flowpilot-agent client")
            else:
                print(f"✗ Failed to update: {resp.status_code}")
                return False
    
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
                "included.client.audience": "flowpilot-agent",
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
            print(f"⚠ Failed to create mapper: {resp.status_code}")
    else:
        print("✓ Audience mapper exists")
    
    print("✓ flowpilot-agent client is properly configured")
    return True

def main():
    print("Verifying flowpilot-agent client configuration...")
    
    try:
        token = get_admin_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        if verify_agent_client(headers):
            print("\n✓ Agent client verification complete!")
            return 0
        else:
            print("\n✗ Agent client verification failed")
            return 1
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

