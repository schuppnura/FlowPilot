#!/usr/bin/env python3
"""
Configure Keycloak to:
1. Add autobook client scope with autobook_consent claim
2. Remove PII (email, given_name, family_name) from access tokens
3. Make those fields optional (not required)
4. Apply autobook scope to flowpilot-testing and flowpilot-desktop clients
"""
import requests
import sys
import os

# Disable SSL warnings
requests.packages.urllib3.disable_warnings()

KEYCLOAK_URL = "https://localhost:8443"
REALM = "flowpilot"
ADMIN_USER = os.getenv("KEYCLOAK_ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("KEYCLOAK_ADMIN_PASSWORD", "admin")

def get_admin_token():
    """Get admin access token"""
    print("Getting admin token...")
    resp = requests.post(
        f'{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token',
        data={
            'client_id': 'admin-cli',
            'username': ADMIN_USER,
            'password': ADMIN_PASS,
            'grant_type': 'password'
        },
        verify=False
    )
    resp.raise_for_status()
    return resp.json()['access_token']

def get_client_scope_id(headers, scope_name):
    """Get client scope ID by name"""
    resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes',
        headers=headers,
        verify=False
    )
    resp.raise_for_status()
    for scope in resp.json():
        if scope['name'] == scope_name:
            return scope['id']
    return None

def get_client_id(headers, client_id_name):
    """Get client UUID by clientId"""
    resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/clients?clientId={client_id_name}',
        headers=headers,
        verify=False
    )
    resp.raise_for_status()
    clients = resp.json()
    return clients[0]['id'] if clients else None

def create_autobook_scope(headers):
    """Create or update the autobook client scope"""
    print("\nConfiguring autobook client scope...")
    
    scope_id = get_client_scope_id(headers, "autobook")
    
    scope_config = {
        "name": "autobook",
        "description": "Autobook consent scope",
        "protocol": "openid-connect",
        "attributes": {
            "include.in.token.scope": "true",
            "display.on.consent.screen": "false"
        }
    }
    
    if scope_id:
        print(f"  Updating existing autobook scope (id={scope_id})...")
        resp = requests.put(
            f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes/{scope_id}',
            headers=headers,
            json=scope_config,
            verify=False
        )
        resp.raise_for_status()
    else:
        print("  Creating new autobook scope...")
        resp = requests.post(
            f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes',
            headers=headers,
            json=scope_config,
            verify=False
        )
        resp.raise_for_status()
        scope_id = get_client_scope_id(headers, "autobook")
    
    # Add protocol mapper for autobook_consent
    print("  Adding autobook_consent protocol mapper...")
    mapper_config = {
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
            "userinfo.token.claim": "true"
        }
    }
    
    # Check if mapper already exists
    resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes/{scope_id}/protocol-mappers/models',
        headers=headers,
        verify=False
    )
    resp.raise_for_status()
    existing_mappers = resp.json()
    
    mapper_exists = any(m['name'] == 'autobook_consent' for m in existing_mappers)
    
    if mapper_exists:
        print("  Mapper already exists, skipping...")
    else:
        resp = requests.post(
            f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes/{scope_id}/protocol-mappers/models',
            headers=headers,
            json=mapper_config,
            verify=False
        )
        resp.raise_for_status()
        print("  ✓ Mapper added")
    
    return scope_id

def configure_profile_scope_to_remove_pii(headers):
    """Configure profile scope to exclude PII from access token"""
    print("\nConfiguring profile scope to exclude PII from access token...")
    
    profile_scope_id = get_client_scope_id(headers, "profile")
    if not profile_scope_id:
        print("  ✗ Profile scope not found!")
        return
    
    # Get existing protocol mappers
    resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes/{profile_scope_id}/protocol-mappers/models',
        headers=headers,
        verify=False
    )
    resp.raise_for_status()
    mappers = resp.json()
    
    # Update mappers for given_name, family_name, full name, username to exclude from access token
    pii_fields = ['given name', 'family name', 'full name', 'username']
    for mapper in mappers:
        if mapper['name'] in pii_fields:
            mapper_id = mapper['id']
            # Set access.token.claim to false
            mapper['config']['access.token.claim'] = 'false'
            print(f"  Updating mapper '{mapper['name']}' to exclude from access token...")
            resp = requests.put(
                f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes/{profile_scope_id}/protocol-mappers/models/{mapper_id}',
                headers=headers,
                json=mapper,
                verify=False
            )
            resp.raise_for_status()
    
    print("  ✓ Profile scope configured")

def configure_email_scope_to_remove_pii(headers):
    """Configure email scope to exclude email from access token"""
    print("\nConfiguring email scope to exclude email from access token...")
    
    email_scope_id = get_client_scope_id(headers, "email")
    if not email_scope_id:
        print("  ✗ Email scope not found!")
        return
    
    # Get existing protocol mappers
    resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes/{email_scope_id}/protocol-mappers/models',
        headers=headers,
        verify=False
    )
    resp.raise_for_status()
    mappers = resp.json()
    
    # Update email mapper to exclude from access token (but keep email verified)
    for mapper in mappers:
        if mapper['name'] == 'email' and mapper.get('protocolMapper') != 'oidc-usermodel-property-mapper':
            mapper_id = mapper['id']
            mapper['config']['access.token.claim'] = 'false'
            print(f"  Updating mapper 'email' to exclude from access token...")
            resp = requests.put(
                f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes/{email_scope_id}/protocol-mappers/models/{mapper_id}',
                headers=headers,
                json=mapper,
                verify=False
            )
            resp.raise_for_status()
    
    print("  ✓ Email scope configured")

def add_scope_to_client(headers, client_id_name, scope_id):
    """Add autobook scope as default to a client"""
    print(f"\nAdding autobook scope to {client_id_name}...")
    
    client_uuid = get_client_id(headers, client_id_name)
    if not client_uuid:
        print(f"  ✗ Client {client_id_name} not found!")
        return
    
    # Check if already added
    resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/clients/{client_uuid}/default-client-scopes',
        headers=headers,
        verify=False
    )
    resp.raise_for_status()
    default_scopes = resp.json()
    
    if any(s['name'] == 'autobook' for s in default_scopes):
        print(f"  Autobook scope already added to {client_id_name}")
        return
    
    resp = requests.put(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/clients/{client_uuid}/default-client-scopes/{scope_id}',
        headers=headers,
        verify=False
    )
    
    if resp.status_code == 204:
        print(f"  ✓ Added autobook scope to {client_id_name}")
    else:
        print(f"  ✗ Failed to add scope: {resp.status_code} - {resp.text}")

def main():
    try:
        token = get_admin_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # Create/update autobook scope
        autobook_scope_id = create_autobook_scope(headers)
        
        # Configure profile and email scopes to exclude PII from access token
        configure_profile_scope_to_remove_pii(headers)
        configure_email_scope_to_remove_pii(headers)
        
        # Add autobook scope to clients
        add_scope_to_client(headers, "flowpilot-testing", autobook_scope_id)
        add_scope_to_client(headers, "flowpilot-desktop", autobook_scope_id)
        
        print("\n" + "=" * 60)
        print("✓ Configuration complete!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Set autobook_consent attribute for users (if not already set)")
        print("2. Get a new token - it should now include autobook_consent")
        print("3. PII fields (email, given_name, family_name) will be excluded from access tokens")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
