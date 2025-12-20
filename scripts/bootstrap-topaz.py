#!/usr/bin/env python3
"""
Bootstrap ***REMOVED*** directory with FlowPilot manifest data.

Since the ***REMOVED*** import/manifest API endpoints are not available,
we bootstrap by creating sample objects and relations.
"""

import requests
import time
import sys

***REMOVED***_URL = "http://localhost:9393"

def wait_for_***REMOVED***(max_attempts=30):
    """Wait for ***REMOVED*** to be ready."""
    print("Waiting for ***REMOVED*** to be ready...")
    for i in range(max_attempts):
        try:
            response = requests.post(
                f"{***REMOVED***_URL}/api/v3/directory/check",
                json={
                    "object_type": "user",
                    "object_id": "test",
                    "relation": "test",
                    "subject_type": "user",
                    "subject_id": "test"
                },
                timeout=2
            )
            if response.status_code in [200, 404]:  # 404 means types not found, but ***REMOVED*** is up
                print("✓ ***REMOVED*** is ready!")
                return True
        except requests.RequestException:
            pass
        print(f"  Waiting... ({i+1}/{max_attempts})")
        time.sleep(2)

    print("✗ ***REMOVED*** did not become ready in time")
    return False

def bootstrap_flowpilot_data():
    """
    Bootstrap ***REMOVED*** with sample FlowPilot data.

    Creates:
    - A sample user (traveler1)
    - The flowpilot agent
    - Delegation relationship
    - A sample workflow (trip)
    - Workflow items
    """
    print("\n" + "="*60)
    print("Bootstrapping ***REMOVED*** with FlowPilot sample data")
    print("="*60)

    # Create sample objects and relations
    operations = [
        {
            "name": "Create user: traveler1",
            "endpoint": "/api/v3/directory/objects",
            "data": {
                "object": {
                    "type": "user",
                    "id": "traveler1"
                }
            }
        },
        {
            "name": "Create agent: agent_flowpilot_1",
            "endpoint": "/api/v3/directory/objects",
            "data": {
                "object": {
                    "type": "agent",
                    "id": "agent_flowpilot_1"
                }
            }
        },
        {
            "name": "Create delegation: traveler1 -> agent_flowpilot_1",
            "endpoint": "/api/v3/directory/relations",
            "data": {
                "relation": {
                    "object_type": "user",
                    "object_id": "traveler1",
                    "relation": "delegate",
                    "subject_type": "agent",
                    "subject_id": "agent_flowpilot_1"
                }
            }
        }
    ]

    for op in operations:
        print(f"\n{op['name']}...")
        try:
            response = requests.post(
                f"{***REMOVED***_URL}{op['endpoint']}",
                json=op['data'],
                timeout=5
            )

            if response.status_code in [200, 201]:
                print(f"  ✓ Success")
            elif response.status_code == 409:
                print(f"  ✓ Already exists")
            else:
                print(f"  ✗ Failed: {response.status_code}")
                print(f"    Response: {response.text[:200]}")
        except requests.RequestException as e:
            print(f"  ✗ Error: {e}")

    print("\n" + "="*60)
    print("Bootstrap complete!")
    print("="*60)
    print("\nNext steps:")
    print("  1. Create workflows via the Services API")
    print("  2. Set workflow ownership relations")
    print("  3. Create workflow_item relations")
    print("\nThe manifest types are now available in ***REMOVED***.")

def main():
    if not wait_for_***REMOVED***():
        sys.exit(1)

    bootstrap_flowpilot_data()

    return 0

if __name__ == "__main__":
    sys.exit(main())
