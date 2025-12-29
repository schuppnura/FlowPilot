#!/usr/bin/env python3
"""
Grant admin permissions to flowpilot-agent service account.

This script grants the necessary realm-management roles to the flowpilot-agent
service account so it can read user attributes from Keycloak.

Required roles:
- view-users: Read user data and attributes
"""

import os
import sys
import requests
import urllib3

# Disable SSL warnings for local development
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
# Support both KEYCLOAK_BASE_URL and KEYCLOAK_HOST/KEYCLOAK_PORT for flexibility
KEYCLOAK_HOST = os.getenv("KEYCLOAK_HOST", "localhost")
KEYCLOAK_PORT = os.getenv("KEYCLOAK_PORT", "8443")
KEYCLOAK_BASE_URL = os.getenv("KEYCLOAK_BASE_URL", f"https://{KEYCLOAK_HOST}:{KEYCLOAK_PORT}")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "flowpilot")
ADMIN_USERNAME = os.getenv("KEYCLOAK_ADMIN", os.getenv("KEYCLOAK_ADMIN_USERNAME", "admin"))
ADMIN_PASSWORD = os.getenv("KEYCLOAK_ADMIN_PASSWORD", "")
AGENT_CLIENT_ID = "flowpilot-agent"
REALM_MANAGEMENT_CLIENT = "realm-management"

# Required roles for the agent service account
REQUIRED_ROLES = [
    "view-users",      # Read user data
    "query-users",     # Query user list
]


def load_env_file(env_file=".env"):
    """Load environment variables from .env file."""
    if not os.path.exists(env_file):
        return
    
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                # Remove quotes if present
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)


def get_admin_token(base_url, admin_username, admin_password):
    """Get admin access token from Keycloak."""
    token_url = f"{base_url}/realms/master/protocol/openid-connect/token"
    
    response = requests.post(
        token_url,
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": admin_username,
            "password": admin_password,
        },
        verify=False,
    )
    
    if response.status_code != 200:
        print(f"❌ Failed to get admin token: {response.status_code}")
        print(f"   Response: {response.text}")
        sys.exit(1)
    
    return response.json()["access_token"]


def get_service_account_user_id(session, base_url, realm, client_id):
    """Get the user ID of the service account for a client."""
    # First, get the client's internal ID
    clients_url = f"{base_url}/admin/realms/{realm}/clients"
    params = {"clientId": client_id}
    
    response = session.get(clients_url, params=params)
    if response.status_code != 200:
        print(f"❌ Failed to find client {client_id}: {response.status_code}")
        return None
    
    clients = response.json()
    if not clients:
        print(f"❌ Client {client_id} not found")
        return None
    
    client_uuid = clients[0]["id"]
    
    # Get the service account user ID
    service_account_url = f"{base_url}/admin/realms/{realm}/clients/{client_uuid}/service-account-user"
    response = session.get(service_account_url)
    
    if response.status_code != 200:
        print(f"❌ Failed to get service account user: {response.status_code}")
        return None
    
    user_data = response.json()
    return user_data["id"]


def get_client_uuid(session, base_url, realm, client_id):
    """Get the internal UUID for a client by its clientId."""
    clients_url = f"{base_url}/admin/realms/{realm}/clients"
    params = {"clientId": client_id}
    
    response = session.get(clients_url, params=params)
    if response.status_code != 200:
        print(f"❌ Failed to find client {client_id}: {response.status_code}")
        return None
    
    clients = response.json()
    if not clients:
        print(f"❌ Client {client_id} not found")
        return None
    
    return clients[0]["id"]


def get_available_roles(session, base_url, realm, user_id, client_uuid):
    """Get available client roles for a user."""
    roles_url = f"{base_url}/admin/realms/{realm}/users/{user_id}/role-mappings/clients/{client_uuid}/available"
    
    response = session.get(roles_url)
    if response.status_code != 200:
        print(f"❌ Failed to get available roles: {response.status_code}")
        return []
    
    return response.json()


def get_assigned_roles(session, base_url, realm, user_id, client_uuid):
    """Get currently assigned client roles for a user."""
    roles_url = f"{base_url}/admin/realms/{realm}/users/{user_id}/role-mappings/clients/{client_uuid}"
    
    response = session.get(roles_url)
    if response.status_code != 200:
        return []
    
    return response.json()


def assign_roles(session, base_url, realm, user_id, client_uuid, roles):
    """Assign client roles to a user."""
    roles_url = f"{base_url}/admin/realms/{realm}/users/{user_id}/role-mappings/clients/{client_uuid}"
    
    response = session.post(roles_url, json=roles)
    return response.status_code in [200, 201, 204]


def main():
    print("Granting admin permissions to flowpilot-agent service account...")
    print()
    
    # Load environment variables
    load_env_file()
    
    # Check for admin password
    admin_password = os.getenv("KEYCLOAK_ADMIN_PASSWORD", "")
    if not admin_password:
        print("❌ KEYCLOAK_ADMIN_PASSWORD not set")
        print("   Set it in .env file or environment variable")
        sys.exit(1)
    
    # Get admin token
    print("Step 1: Authenticating as Keycloak admin...")
    token = get_admin_token(KEYCLOAK_BASE_URL, ADMIN_USERNAME, admin_password)
    print("  ✓ Admin token obtained")
    print()
    
    # Create session with token
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    session.verify = False
    
    # Get service account user ID
    print(f"Step 2: Finding {AGENT_CLIENT_ID} service account...")
    user_id = get_service_account_user_id(session, KEYCLOAK_BASE_URL, KEYCLOAK_REALM, AGENT_CLIENT_ID)
    if not user_id:
        print(f"❌ Failed to find service account for {AGENT_CLIENT_ID}")
        sys.exit(1)
    print(f"  ✓ Service account user ID: {user_id}")
    print()
    
    # Get realm-management client UUID
    print(f"Step 3: Finding {REALM_MANAGEMENT_CLIENT} client...")
    client_uuid = get_client_uuid(session, KEYCLOAK_BASE_URL, KEYCLOAK_REALM, REALM_MANAGEMENT_CLIENT)
    if not client_uuid:
        print(f"❌ Failed to find {REALM_MANAGEMENT_CLIENT} client")
        sys.exit(1)
    print(f"  ✓ Realm-management client UUID: {client_uuid}")
    print()
    
    # Get currently assigned roles
    print("Step 4: Checking currently assigned roles...")
    assigned_roles = get_assigned_roles(session, KEYCLOAK_BASE_URL, KEYCLOAK_REALM, user_id, client_uuid)
    assigned_role_names = {role["name"] for role in assigned_roles}
    print(f"  Currently assigned: {', '.join(assigned_role_names) if assigned_role_names else 'none'}")
    print()
    
    # Get available roles
    print("Step 5: Finding roles to assign...")
    available_roles = get_available_roles(session, KEYCLOAK_BASE_URL, KEYCLOAK_REALM, user_id, client_uuid)
    available_by_name = {role["name"]: role for role in available_roles}
    
    # Determine which roles need to be assigned
    roles_to_assign = []
    for role_name in REQUIRED_ROLES:
        if role_name in assigned_role_names:
            print(f"  ✓ {role_name} - already assigned")
        elif role_name in available_by_name:
            roles_to_assign.append(available_by_name[role_name])
            print(f"  → {role_name} - will be assigned")
        else:
            print(f"  ⚠ {role_name} - not available (role may not exist)")
    print()
    
    # Assign roles if needed
    if roles_to_assign:
        print("Step 6: Assigning roles...")
        success = assign_roles(session, KEYCLOAK_BASE_URL, KEYCLOAK_REALM, user_id, client_uuid, roles_to_assign)
        if success:
            print(f"  ✓ Assigned {len(roles_to_assign)} role(s)")
            print()
            print("✅ Permissions granted successfully!")
            print()
            print("The flowpilot-agent service account can now:")
            print("  - Read user data and attributes")
            print("  - Query user lists")
            print()
            print("Next steps:")
            print("  1. Restart the services: docker compose restart")
            print("  2. Run regression tests: python3 tests/regression_test.py")
        else:
            print("❌ Failed to assign roles")
            sys.exit(1)
    else:
        print("✅ All required roles already assigned!")
        print()
        print("The flowpilot-agent service account has the necessary permissions.")


if __name__ == "__main__":
    main()
