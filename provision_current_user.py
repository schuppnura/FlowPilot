#!/usr/bin/env python3
"""
Provision the current user (from Keycloak access token) in ***REMOVED***.
This allows the macOS app user to execute workflows.
"""
import sys
import requests
import json

def get_users_from_keycloak():
    """Get all users from Keycloak"""
    import os
    admin_password = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin")
    
    # Get admin token first
    token_response = requests.post(
        "http://localhost:8080/realms/master/protocol/openid-connect/token",
        data={
            "client_id": "admin-cli",
            "username": "admin",
            "password": admin_password,
            "grant_type": "password"
        },
        verify=False
    )
    
    if token_response.status_code != 200:
        print(f"Failed to get admin token: {token_response.status_code}")
        return []
    
    admin_token = token_response.json()["access_token"]
    
    # Get users from flowpilot realm
    users_response = requests.get(
        "http://localhost:8080/admin/realms/flowpilot/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        verify=False
    )
    
    if users_response.status_code != 200:
        print(f"Failed to get users: {users_response.status_code}")
        return []
    
    return users_response.json()

def provision_user_in_***REMOVED***(user_id, username):
    """Provision user and delegate relation in ***REMOVED***"""
    print(f"Provisioning user in ***REMOVED***...")
    print(f"  User ID: {user_id}")
    print(f"  Username: {username}")
    
    # Create user object
    print("  Creating user object...")
    response = requests.post(
        "http://localhost:9393/api/v3/directory/object",
        json={
            "object": {
                "type": "user",
                "id": user_id,
                "display_name": username,
                "properties": {}
            }
        },
        verify=False
    )
    
    if response.status_code in [200, 409]:  # 409 means already exists
        print("    ✓ User object created/exists")
    else:
        print(f"    ✗ Failed: {response.status_code} - {response.text}")
        return False
    
    # Create agent object if it doesn't exist
    print("  Creating agent object...")
    response = requests.post(
        "http://localhost:9393/api/v3/directory/object",
        json={
            "object": {
                "type": "agent",
                "id": "agent-runner",
                "display_name": "agent-runner",
                "properties": {}
            }
        },
        verify=False
    )
    
    if response.status_code in [200, 409]:
        print("    ✓ Agent object created/exists")
    else:
        print(f"    ✗ Failed: {response.status_code} - {response.text}")
    
    # Create delegate relation: user --delegate--> agent
    print("  Creating delegate relation...")
    response = requests.post(
        "http://localhost:9393/api/v3/directory/relation",
        json={
            "relation": {
                "object_type": "user",
                "object_id": user_id,
                "relation": "delegate",
                "subject_type": "agent",
                "subject_id": "agent-runner"
            }
        },
        verify=False
    )
    
    if response.status_code in [200, 409]:
        print("    ✓ Delegate relation created/exists")
        return True
    else:
        print(f"    ✗ Failed: {response.status_code} - {response.text}")
        return False

def main():
    print("=" * 60)
    print("Provision Current Keycloak Users in ***REMOVED***")
    print("=" * 60)
    print()
    
    print("Fetching users from Keycloak...")
    users = get_users_from_keycloak()
    
    if not users:
        print("No users found or failed to fetch users")
        return 1
    
    print(f"Found {len(users)} users in Keycloak flowpilot realm:")
    print()
    
    # Skip already provisioned users (carlo, peter, etc.)
    already_provisioned = {"carlo", "peter", "yannick", "isabel", "martine"}
    
    for idx, user in enumerate(users, 1):
        username = user.get("username", "")
        user_id = user.get("id", "")
        email = user.get("email", "")
        
        if username in already_provisioned:
            print(f"{idx}. {username} ({email}) - ALREADY PROVISIONED, skipping")
            continue
        
        print(f"{idx}. {username} ({email})")
        print(f"   ID: {user_id}")
        
        response = input("   Provision this user in ***REMOVED***? (y/n): ").strip().lower()
        if response == 'y':
            if provision_user_in_***REMOVED***(user_id, username):
                print("   ✓ Successfully provisioned!")
            else:
                print("   ✗ Failed to provision")
        else:
            print("   Skipped")
        print()
    
    print("=" * 60)
    print("Done!")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
