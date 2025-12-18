#!/usr/bin/env python3
"""Debug script to check workflow owner_sub

This script will:
1. Get a user token via browser login
2. Create a workflow
3. Show the workflow details including owner_sub
4. Attempt to execute via agent-runner
"""

import sys
import os

# Add parent directory to path so we can import from tests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from user_based_testing import (
    get_user_token_via_browser,
    create_workflow_for_owner,
    SERVICES_API_BASE,
)
import requests

# Disable SSL warnings
requests.packages.urllib3.disable_warnings()

def main():
    print("\n" + "=" * 60)
    print("Workflow Owner Debug Script")
    print("=" * 60)
    
    # Get user token
    print("\n[1] Authenticating...")
    try:
        access_token, user_sub, username = get_user_token_via_browser()
        print(f"  ✓ User: {username}")
        print(f"  ✓ Sub: {user_sub}")
    except Exception as e:
        print(f"  ✗ Auth failed: {e}")
        return 1
    
    # Create workflow
    print(f"\n[2] Creating workflow...")
    try:
        result = create_workflow_for_owner(owner_sub=user_sub, access_token=access_token)
        workflow_id = result["workflow_id"]
        print(f"  ✓ Workflow ID: {workflow_id}")
        print(f"  ✓ Owner Sub: {result.get('owner_sub', 'N/A')}")
    except Exception as e:
        print(f"  ✗ Create failed: {e}")
        return 1
    
    # Get workflow details from services API
    print(f"\n[3] Fetching workflow details...")
    try:
        url = f"{SERVICES_API_BASE}/v1/workflows/{workflow_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(url, headers=headers, verify=False)
        response.raise_for_status()
        workflow_data = response.json()
        print(f"  Workflow data: {workflow_data}")
        stored_owner = workflow_data.get("owner_sub", "N/A")
        print(f"  ✓ Stored owner_sub: {stored_owner}")
        
        if stored_owner == user_sub:
            print(f"  ✓ MATCH: owner_sub matches authenticated user")
        else:
            print(f"  ✗ MISMATCH: owner_sub ({stored_owner}) != user_sub ({user_sub})")
    except Exception as e:
        print(f"  ✗ Fetch failed: {e}")
        return 1
    
    # Get workflow items
    print(f"\n[4] Fetching workflow items...")
    try:
        url = f"{SERVICES_API_BASE}/v1/workflows/{workflow_id}/items"
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(url, headers=headers, verify=False)
        response.raise_for_status()
        items_data = response.json()
        items = items_data.get("items", [])
        print(f"  ✓ Found {len(items)} items")
        for item in items:
            print(f"    - {item.get('item_id')} ({item.get('kind')}): {item.get('title')}")
    except Exception as e:
        print(f"  ✗ Fetch items failed: {e}")
        return 1
    
    # Try to execute first item directly
    if items:
        first_item = items[0]
        print(f"\n[5] Attempting direct execution of first item...")
        print(f"  Item ID: {first_item['item_id']}")
        print(f"  Using principal_sub: {user_sub}")
        try:
            url = f"{SERVICES_API_BASE}/v1/workflows/{workflow_id}/items/{first_item['item_id']}/execute"
            headers = {"Authorization": f"Bearer {access_token}"}
            payload = {"principal_sub": user_sub, "dry_run": True}
            response = requests.post(url, json=payload, headers=headers, verify=False)
            print(f"  Response status: {response.status_code}")
            if response.status_code == 200:
                print(f"  ✓ SUCCESS: {response.json()}")
            elif response.status_code == 403:
                print(f"  ✗ DENIED: {response.text}")
            else:
                print(f"  ✗ ERROR: {response.text}")
        except Exception as e:
            print(f"  ✗ Execution failed: {e}")
    
    print("\n" + "=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
