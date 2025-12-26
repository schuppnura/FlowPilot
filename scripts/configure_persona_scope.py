#!/usr/bin/env python3
"""
Create and configure the persona scope with persona and username mappers.
This script ensures the persona scope exists and has the correct protocol mappers.
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
    resp.raise_for_status()
    return resp.json()['access_token']

def get_client_scope_id(headers, scope_name):
    """Get client scope ID by name"""
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

def add_protocol_mapper(headers, scope_id, mapper_config):
    """Add a protocol mapper to a scope"""
    resp = requests.post(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes/{scope_id}/protocol-mappers/models',
        headers=headers,
        json=mapper_config,
        verify=False,
        timeout=10
    )
    if resp.status_code == 201:
        return True
    elif resp.status_code == 409:
        # Mapper already exists
        return True
    else:
        print(f"  Failed to add mapper '{mapper_config['name']}': {resp.status_code} - {resp.text}")
        return False

def main():
    print("Configuring persona scope with persona and username mappers...")
    
    try:
        token = get_admin_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # Get or create persona scope
        scope_id = get_client_scope_id(headers, "persona")
        if not scope_id:
            print("Persona client scope not found, creating it...")
            scope_config = {
                "name": "persona",
                "description": "Persona attribute scope - includes only persona attributes (all personas for the user)",
                "protocol": "openid-connect",
                "attributes": {
                    "include.in.token.scope": "true",
                    "display.on.consent.screen": "false"
                }
            }
            resp = requests.post(
                f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes',
                headers=headers,
                json=scope_config,
                verify=False,
                timeout=10
            )
            if resp.status_code == 201:
                scope_id = get_client_scope_id(headers, "persona")
                print(f"✓ Created persona scope (id={scope_id})")
            else:
                print(f"✗ Failed to create scope: {resp.status_code} - {resp.text}")
                return 1
        else:
            print(f"✓ Found persona scope (id={scope_id})")
        
        # Get existing mappers
        existing_mappers = get_existing_mappers(headers, scope_id)
        existing_names = [m['name'] for m in existing_mappers]
        print(f"  Existing mappers: {', '.join(existing_names) if existing_names else 'none'}")
        
        # Define required mappers
        required_mappers = [
            {
                "name": "persona-mapper",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-attribute-mapper",
                "consentRequired": False,
                "config": {
                    "user.attribute": "persona",
                    "claim.name": "persona",
                    "jsonType.label": "String",
                    "id.token.claim": "false",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "false",
                    "multivalued": "true",
                    "aggregate.attrs": "false"
                }
            },
            {
                "name": "username-mapper",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-property-mapper",
                "consentRequired": False,
                "config": {
                    "user.attribute": "username",
                    "claim.name": "username",
                    "jsonType.label": "String",
                    "id.token.claim": "false",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "false",
                    "access.tokenResponse.claim": "false"
                }
            }
        ]
        
        # Check and add missing mappers
        added_count = 0
        for mapper in required_mappers:
            mapper_name = mapper['name']
            if any(m['name'] == mapper_name for m in existing_mappers):
                print(f"✓ Mapper '{mapper_name}' already exists")
            else:
                print(f"  Adding mapper '{mapper_name}'...")
                if add_protocol_mapper(headers, scope_id, mapper):
                    print(f"✓ Added mapper '{mapper_name}'")
                    added_count += 1
                else:
                    print(f"✗ Failed to add mapper '{mapper_name}'")
        
        if added_count > 0:
            print(f"\n✓ Configured {added_count} new mapper(s)")
        else:
            print("\n✓ All mappers are already configured")
        
        return 0
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())


