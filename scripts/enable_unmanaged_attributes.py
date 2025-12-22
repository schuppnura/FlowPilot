#!/usr/bin/env python3
"""
Enable unmanaged attributes in Keycloak realm for custom user attributes.
This is required in Keycloak 26+ to allow setting custom user attributes.
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

def enable_unmanaged_attributes(headers):
    """Enable unmanaged attributes in user profile"""
    print("Enabling unmanaged attributes in user profile...")
    
    # Get current user profile configuration
    profile_url = f'{KEYCLOAK_URL}/admin/realms/{REALM}/users/profile'
    resp = requests.get(profile_url, headers=headers, verify=False, timeout=10)
    
    if resp.status_code == 404:
        print("  User profile API not available (Keycloak < 15 or feature disabled)")
        print("  Trying alternative method...")
        # For older Keycloak versions, we might need to use realm attributes
        return enable_via_realm_attributes(headers)
    
    resp.raise_for_status()
    profile_data = resp.json()
    
    # Enable unmanaged attributes
    # The profile_data structure is: {'attributes': [...], 'groups': [...]}
    # We need to add unmanagedAttributePolicy at the top level
    if 'unmanagedAttributePolicy' not in profile_data:
        profile_data['unmanagedAttributePolicy'] = 'ENABLED'
        print("  Adding unmanagedAttributePolicy: ENABLED...")
        update_resp = requests.put(profile_url, headers=headers, json=profile_data, verify=False, timeout=10)
        if update_resp.status_code in [200, 204]:
            print("  ✓ Unmanaged attributes enabled")
            return True
        else:
            print(f"  ✗ Failed to update: {update_resp.status_code} - {update_resp.text[:200]}")
            return False
    elif profile_data.get('unmanagedAttributePolicy') != 'ENABLED':
        profile_data['unmanagedAttributePolicy'] = 'ENABLED'
        print("  Updating unmanagedAttributePolicy to ENABLED...")
        update_resp = requests.put(profile_url, headers=headers, json=profile_data, verify=False, timeout=10)
        if update_resp.status_code in [200, 204]:
            print("  ✓ Unmanaged attributes enabled")
            return True
        else:
            print(f"  ✗ Failed to update: {update_resp.status_code} - {update_resp.text[:200]}")
            return False
    else:
        print("  ✓ Unmanaged attributes already enabled")
        return True

def enable_via_realm_attributes(headers):
    """Alternative method: Set realm attribute"""
    print("  Setting realm attribute for unmanaged attributes...")
    realm_url = f'{KEYCLOAK_URL}/admin/realms/{REALM}'
    resp = requests.get(realm_url, headers=headers, verify=False, timeout=10)
    resp.raise_for_status()
    realm_data = resp.json()
    
    if 'attributes' not in realm_data:
        realm_data['attributes'] = {}
    
    # Set userProfileEnabled if not already set
    if realm_data['attributes'].get('userProfileEnabled') != 'true':
        realm_data['attributes']['userProfileEnabled'] = 'true'
        update_resp = requests.put(realm_url, headers=headers, json=realm_data, verify=False, timeout=10)
        if update_resp.status_code in [200, 204]:
            print("  ✓ Realm attribute set")
            return True
        else:
            print(f"  ✗ Failed: {update_resp.status_code}")
            return False
    else:
        print("  ✓ Realm attribute already set")
        return True

def main():
    print("Enabling unmanaged attributes for Keycloak realm...")
    
    try:
        token = get_admin_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        success = enable_unmanaged_attributes(headers)
        
        if success:
            print("\n✓ Unmanaged attributes enabled!")
            print("  You can now set custom user attributes.")
            print("  Re-run seed_keycloak_users.py to set the attributes.")
            return 0
        else:
            print("\n✗ Failed to enable unmanaged attributes")
            print("  You may need to enable this manually in the Keycloak Admin UI:")
            print("  Realm Settings > User Profile > Unmanaged Attributes: Enabled")
            return 1
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())

