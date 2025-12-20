#!/usr/bin/env python3
"""Test if delegate relation exists in ***REMOVED***"""
import requests

# Carlo's sub from provisioning
carlo_sub = "2129b076-cd98-4f7b-a101-7d0fa228b1c3"
agent_id = "agent-runner"

print(f"Testing ***REMOVED*** delegate relation:")
print(f"  User: {carlo_sub}")
print(f"  Agent: {agent_id}")
print()

# Test 1: Check if user object exists
print("1. Checking if user object exists in ***REMOVED***...")
response = requests.post(
    "http://localhost:9393/api/v3/directory/check",
    json={
        "subject_type": "user",
        "subject_id": carlo_sub,
        "object_type": "user",
        "object_id": carlo_sub,
        "relation": "is_owner",  # Just checking if object exists, not a real permission
        "trace": False
    },
    verify=False
)
print(f"   Status: {response.status_code}")

# Test 2: Check if agent object exists
print("\n2. Checking if agent object exists in ***REMOVED***...")
response = requests.post(
    "http://localhost:9393/api/v3/directory/check",
    json={
        "subject_type": "agent",
        "subject_id": agent_id,
        "object_type": "agent",
        "object_id": agent_id,
        "relation": "is_owner",  # Just checking if object exists
        "trace": False
    },
    verify=False
)
print(f"   Status: {response.status_code}")

# Test 3: Check if delegate relation exists
print("\n3. Checking if user delegates to agent...")
response = requests.post(
    "http://localhost:9393/api/v3/directory/check",
    json={
        "subject_type": "agent",
        "subject_id": agent_id,
        "object_type": "user",
        "object_id": carlo_sub,
        "relation": "delegate",
        "trace": True
    },
    verify=False
)
print(f"   Status: {response.status_code}")
result = response.json()
print(f"   Check result: {result.get('check', False)}")
if 'trace' in result:
    print(f"   Trace: {result['trace']}")

# Test 4: Now test the actual workflow_item check with a real workflow
print("\n4. Testing workflow_item.can_execute check...")
print("   (This will fail if no workflow exists, but tests the permission chain)")

# Create a test workflow first
print("\n   Creating test workflow...")
workflow_response = requests.post(
    "http://localhost:8003/v1/workflows",
    json={
        "template_id": "template_all_ok",
        "principal_sub": carlo_sub
    },
    headers={"Authorization": "Bearer fake"},
    verify=False
)
if workflow_response.status_code == 200:
    workflow_data = workflow_response.json()
    workflow_id = workflow_data["workflow_id"]
    print(f"   Created workflow: {workflow_id}")

    # Get workflow items
    items_response = requests.get(
        f"http://localhost:8003/v1/workflows/{workflow_id}/items",
        headers={"Authorization": "Bearer fake"},
        verify=False
    )
    if items_response.status_code == 200:
        items_data = items_response.json()
        if items_data.get("items"):
            workflow_item_id = items_data["items"][0]["item_id"]
            print(f"   Got workflow_item: {workflow_item_id}")

            # Now test the permission check
            print(f"\n   Testing: agent:{agent_id} can_execute workflow_item:{workflow_item_id}...")
            perm_response = requests.post(
                "http://localhost:9393/api/v3/directory/check",
                json={
                    "subject_type": "agent",
                    "subject_id": agent_id,
                    "object_type": "workflow_item",
                    "object_id": workflow_item_id,
                    "relation": "can_execute",
                    "trace": True
                },
                verify=False
            )
            perm_result = perm_response.json()
            print(f"   Check result: {perm_result.get('check', False)}")
            if 'trace' in perm_result:
                print(f"   Trace: {perm_result['trace']}")
else:
    print(f"   Failed to create workflow: {workflow_response.status_code}")
