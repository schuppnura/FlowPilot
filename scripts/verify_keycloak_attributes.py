#!/usr/bin/env python3
"""
Verify and configure Keycloak autobook attributes in access tokens.
This script ensures the protocol mappers are configured correctly.
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
    for scope in resp.json():
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
    if resp.status_code == 409:
        print(f"  Mapper '{mapper_config['name']}' already exists")
        return False
    resp.raise_for_status()
    print(f"  ✓ Added mapper '{mapper_config['name']}'")
    return True

def main():
    print("Verifying Keycloak autobook attributes configuration...")
    
    try:
        token = get_admin_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # Get or create autobook scope
        scope_id = get_client_scope_id(headers, "autobook")
        if not scope_id:
            print("Autobook client scope not found, creating it...")
            scope_config = {
                "name": "autobook",
                "description": "Autobook consent scope",
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
                scope_id = get_client_scope_id(headers, "autobook")
                print(f"✓ Created autobook scope (id={scope_id})")
            else:
                print(f"✗ Failed to create scope: {resp.status_code} - {resp.text}")
                return 1
        else:
            print(f"✓ Found autobook scope (id={scope_id})")
        
        # Get existing mappers
        existing_mappers = get_existing_mappers(headers, scope_id)
        existing_names = [m['name'] for m in existing_mappers]
        print(f"  Existing mappers: {', '.join(existing_names)}")
        
        # Define required mappers
        required_mappers = [
            {
                "name": "autobook_consent",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-attribute-mapper",
                "consentRequired": False,
                "config": {
                    "user.attribute": "autobook_consent",
                    "claim.name": "autobook_consent",
                    "jsonType.label": "String",
                    "id.token.claim": "false",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "false"
                }
            },
            {
                "name": "autobook_price",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-attribute-mapper",
                "consentRequired": False,
                "config": {
                    "user.attribute": "autobook_price",
                    "claim.name": "autobook_price",
                    "jsonType.label": "String",
                    "id.token.claim": "false",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "false"
                }
            },
            {
                "name": "autobook_leadtime",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-attribute-mapper",
                "consentRequired": False,
                "config": {
                    "user.attribute": "autobook_leadtime",
                    "claim.name": "autobook_leadtime",
                    "jsonType.label": "String",
                    "id.token.claim": "false",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "false"
                }
            },
            {
                "name": "autobook_risklevel",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-attribute-mapper",
                "consentRequired": False,
                "config": {
                    "user.attribute": "autobook_risklevel",
                    "claim.name": "autobook_risklevel",
                    "jsonType.label": "String",
                    "id.token.claim": "false",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "false"
                }
            }
        ]
        
        # Add missing mappers
        print("\nChecking protocol mappers...")
        added_count = 0
        for mapper in required_mappers:
            if mapper['name'] not in existing_names:
                add_protocol_mapper(headers, scope_id, mapper)
                added_count += 1
            else:
                print(f"  ✓ Mapper '{mapper['name']}' already exists")
        
        if added_count > 0:
            print(f"\n✓ Added {added_count} new protocol mapper(s)")
        else:
            print("\n✓ All protocol mappers are configured")
        
        # Verify final state
        final_mappers = get_existing_mappers(headers, scope_id)
        final_names = [m['name'] for m in final_mappers]
        print(f"\nFinal mappers: {', '.join(final_names)}")
        
        required_names = [m['name'] for m in required_mappers]
        missing = [name for name in required_names if name not in final_names]
        if missing:
            print(f"✗ Missing mappers: {', '.join(missing)}")
            return 1
        
        print("\n✓ All required protocol mappers are configured!")
        return 0
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())

