#!/usr/bin/env python3
"""
Configure Keycloak clients to use audience "flowpilot" for both desktop and agent clients.
This ensures all tokens have the same audience, simplifying JWT validation.
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
ADMIN_PASS = os.getenv("KEYCLOAK_ADMIN_PASSWORD") or env_vars.get("KEYCLOAK_ADMIN_PASSWORD")

if not ADMIN_PASS:
    print("ERROR: KEYCLOAK_ADMIN_PASSWORD not found in environment or .env file")
    sys.exit(1)

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
    resp.raise_for_status()
    return resp.json()['access_token']

def get_client_by_id(headers, client_id):
    """Get client configuration by client_id"""
    resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/clients',
        headers=headers,
        params={'clientId': client_id},
        verify=False,
        timeout=10
    )
    resp.raise_for_status()
    clients = resp.json()
    return clients[0] if clients else None

def add_audience_mapper(headers, client_uuid, client_id, audience):
    """Add or update audience protocol mapper for a client"""
    # Get existing mappers
    resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/clients/{client_uuid}/protocol-mappers/models',
        headers=headers,
        verify=False,
        timeout=10
    )
    resp.raise_for_status()
    mappers = resp.json()
    
    # Check if audience mapper already exists
    existing_mapper = None
    for mapper in mappers:
        if mapper.get('name') == 'audience-flowpilot' or mapper.get('protocolMapper') == 'oidc-audience-mapper':
            existing_mapper = mapper
            break
    
    # Audience mapper configuration
    mapper_config = {
        "name": "audience-flowpilot",
        "protocol": "openid-connect",
        "protocolMapper": "oidc-audience-mapper",
        "consentRequired": False,
        "config": {
            "included.client.audience": audience,
            "included.custom.audience": audience,
            "access.token.claim": "true",
            "id.token.claim": "false"
        }
    }
    
    if existing_mapper:
        # Update existing mapper
        mapper_id = existing_mapper['id']
        mapper_config['id'] = mapper_id
        resp = requests.put(
            f'{KEYCLOAK_URL}/admin/realms/{REALM}/clients/{client_uuid}/protocol-mappers/models/{mapper_id}',
            headers=headers,
            json=mapper_config,
            verify=False,
            timeout=10
        )
        if resp.status_code in [200, 204]:
            print(f"  ✓ Updated audience mapper for {client_id}")
            return True
        else:
            print(f"  ✗ Failed to update mapper: {resp.status_code} - {resp.text[:200]}")
            return False
    else:
        # Create new mapper
        resp = requests.post(
            f'{KEYCLOAK_URL}/admin/realms/{REALM}/clients/{client_uuid}/protocol-mappers/models',
            headers=headers,
            json=mapper_config,
            verify=False,
            timeout=10
        )
        if resp.status_code in [200, 201, 204]:
            print(f"  ✓ Created audience mapper for {client_id}")
            return True
        else:
            print(f"  ✗ Failed to create mapper: {resp.status_code} - {resp.text[:200]}")
            return False

def main():
    print("Configuring Keycloak clients to use audience 'flowpilot'...")
    print()
    
    try:
        token = get_admin_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # Configure flowpilot-desktop client
        print("Configuring flowpilot-desktop client...")
        desktop_client = get_client_by_id(headers, 'flowpilot-desktop')
        if not desktop_client:
            print("  ✗ flowpilot-desktop client not found")
            return 1
        
        desktop_success = add_audience_mapper(headers, desktop_client['id'], 'flowpilot-desktop', 'flowpilot')
        
        # Configure flowpilot-agent client
        print("\nConfiguring flowpilot-agent client...")
        agent_client = get_client_by_id(headers, 'flowpilot-agent')
        if not agent_client:
            print("  ✗ flowpilot-agent client not found")
            return 1
        
        agent_success = add_audience_mapper(headers, agent_client['id'], 'flowpilot-agent', 'flowpilot')
        
        if desktop_success and agent_success:
            print("\n✓ Successfully configured audience 'flowpilot' for both clients!")
            print("  Both flowpilot-desktop and flowpilot-agent will now issue tokens with audience='flowpilot'")
            return 0
        else:
            print("\n⚠ Some configuration steps failed")
            return 1
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
