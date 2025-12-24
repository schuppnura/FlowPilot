#!/usr/bin/env python3
"""
Configure the persona attribute as mandatory in Keycloak user profile.
This ensures the attribute is required for all users and always appears in access tokens.
"""
import requests
import sys
import os
import urllib3
import json

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

def configure_persona_attribute(headers):
    """Configure persona attribute as mandatory in user profile"""
    print("Configuring persona attribute in user profile...")
    
    # Get current user profile configuration
    profile_url = f'{KEYCLOAK_URL}/admin/realms/{REALM}/users/profile'
    resp = requests.get(profile_url, headers=headers, verify=False, timeout=10)
    
    if resp.status_code == 404:
        print("  ✗ User profile API not available")
        print("  This requires Keycloak 15+ with user profile enabled")
        return False
    
    resp.raise_for_status()
    profile_data = resp.json()
    
    # Ensure attributes array exists
    if 'attributes' not in profile_data:
        profile_data['attributes'] = []
    
    # Check if persona attribute already exists
    persona_attr = None
    for attr in profile_data['attributes']:
        if attr.get('name') == 'persona':
            persona_attr = attr
            break
    
    # Configure persona attribute
    # Required with empty roles/scopes arrays means required for all users
    persona_config = {
        "name": "persona",
        "displayName": "Persona",
        "group": "",
        "permissions": {},
        "validations": {},
        "annotations": {},
        "required": {
            "roles": [],
            "scopes": []
        },
        "selector": {},
        "multivalued": True,
        "type": "String"
    }
    
    if persona_attr:
        # Update existing attribute
        print("  Updating existing persona attribute...")
        # Merge with existing config, but ensure required and multivalued are set
        persona_attr.update({
            "required": {
                "roles": [],
                "scopes": []
            },
            "multivalued": True,
            "type": "String"
        })
        # Find and replace in the array
        for i, attr in enumerate(profile_data['attributes']):
            if attr.get('name') == 'persona':
                profile_data['attributes'][i] = persona_attr
                break
    else:
        # Add new attribute
        print("  Adding persona attribute...")
        profile_data['attributes'].append(persona_config)
    
    # Update user profile
    update_resp = requests.put(profile_url, headers=headers, json=profile_data, verify=False, timeout=10)
    if update_resp.status_code in [200, 204]:
        print("  ✓ Persona attribute configured as mandatory")
        return True
    else:
        print(f"  ✗ Failed to update: {update_resp.status_code} - {update_resp.text[:200]}")
        return False

def ensure_all_users_have_persona(headers):
    """Ensure all existing users have the persona attribute set (even if empty array)"""
    print("\nEnsuring all users have persona attribute...")
    
    # Get all users
    users_resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/users',
        headers=headers,
        params={'max': 1000},  # Adjust if you have more users
        verify=False,
        timeout=10
    )
    users_resp.raise_for_status()
    users = users_resp.json()
    
    updated_count = 0
    for user in users:
        user_id = user['id']
        
        # Get current user data
        user_resp = requests.get(
            f'{KEYCLOAK_URL}/admin/realms/{REALM}/users/{user_id}',
            headers=headers,
            verify=False,
            timeout=10
        )
        user_resp.raise_for_status()
        user_data = user_resp.json()
        
        # Initialize attributes if not present
        if 'attributes' not in user_data or user_data['attributes'] is None:
            user_data['attributes'] = {}
        
        # Set persona to empty array if not present
        if 'persona' not in user_data['attributes']:
            user_data['attributes']['persona'] = []
            
            # Remove read-only fields
            for field in ['access', 'createdTimestamp', 'totp', 'disableableCredentialTypes', 
                         'requiredActions', 'notBefore', 'federatedIdentities', 'self']:
                user_data.pop(field, None)
            
            # Update user
            update_resp = requests.put(
                f'{KEYCLOAK_URL}/admin/realms/{REALM}/users/{user_id}',
                headers=headers,
                json=user_data,
                verify=False,
                timeout=10
            )
            if update_resp.status_code == 204:
                updated_count += 1
    
    if updated_count > 0:
        print(f"  ✓ Updated {updated_count} user(s) with persona attribute")
    else:
        print("  ✓ All users already have persona attribute")
    
    return True

def verify_persona_mapper(headers):
    """Verify that persona protocol mapper exists and is configured correctly"""
    print("\nVerifying persona protocol mapper...")
    
    # Get autobook scope
    scope_resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes',
        headers=headers,
        verify=False,
        timeout=10
    )
    scope_resp.raise_for_status()
    
    autobook_scope = None
    for scope in scope_resp.json():
        if scope['name'] == 'autobook':
            autobook_scope = scope
            break
    
    if not autobook_scope:
        print("  ✗ Autobook scope not found")
        return False
    
    # Get mappers for autobook scope
    mappers_resp = requests.get(
        f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes/{autobook_scope["id"]}/protocol-mappers/models',
        headers=headers,
        verify=False,
        timeout=10
    )
    mappers_resp.raise_for_status()
    mappers = mappers_resp.json()
    
    # Check if persona mapper exists
    persona_mapper = None
    for mapper in mappers:
        if mapper.get('name') == 'persona':
            persona_mapper = mapper
            break
    
    if not persona_mapper:
        print("  ✗ Persona protocol mapper not found")
        print("  It should be added via the realm configuration template")
        return False
    
    # Verify configuration
    config = persona_mapper.get('config', {})
    needs_update = False
    
    if config.get('multivalued') != 'true':
        print("  ⚠ Persona mapper is not configured as multivalued, updating...")
        config['multivalued'] = 'true'
        needs_update = True
    
    if config.get('access.token.claim') != 'true':
        print("  ⚠ Persona mapper is not configured to appear in access tokens, updating...")
        config['access.token.claim'] = 'true'
        needs_update = True
    
    # Update mapper if needed
    if needs_update:
        mapper_id = persona_mapper['id']
        persona_mapper['config'] = config
        update_resp = requests.put(
            f'{KEYCLOAK_URL}/admin/realms/{REALM}/client-scopes/{autobook_scope["id"]}/protocol-mappers/models/{mapper_id}',
            headers=headers,
            json=persona_mapper,
            verify=False,
            timeout=10
        )
        if update_resp.status_code in [200, 204]:
            print("  ✓ Updated persona protocol mapper configuration")
        else:
            print(f"  ✗ Failed to update mapper: {update_resp.status_code}")
            return False
    
    print("  ✓ Persona protocol mapper is correctly configured")
    return True

def main():
    print("Configuring persona attribute in Keycloak...")
    
    try:
        token = get_admin_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # Configure persona in user profile
        success = configure_persona_attribute(headers)
        
        # Verify protocol mapper
        mapper_ok = verify_persona_mapper(headers)
        
        # Ensure all users have persona attribute
        users_ok = ensure_all_users_have_persona(headers)
        
        if success and mapper_ok and users_ok:
            print("\n✓ Persona attribute configured successfully!")
            print("  - Attribute is mandatory for all users")
            print("  - Attribute is multivalued (list of strings)")
            print("  - Attribute appears in access tokens")
            print("  - All existing users have persona attribute initialized")
            return 0
        else:
            print("\n⚠ Some configuration steps may have failed")
            if not success:
                print("  - Failed to configure user profile")
            if not mapper_ok:
                print("  - Protocol mapper verification failed")
            if not users_ok:
                print("  - Failed to initialize persona for all users")
            return 1
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

