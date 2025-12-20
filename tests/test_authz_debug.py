#!/usr/bin/env python3
"""Quick test to debug authorization decisions"""
import requests
import json

# Test the evaluate endpoint
payload = {
    "subject": {"type": "agent", "id": "agent-runner"},
    "action": {"name": "auto-book"},
    "resource": {
        "type": "workflow",
        "id": "test-workflow-123",
        "properties": {
            "domain": "flowpilot",
            "workflow_item_id": "test-item-456",
            "workflow_item_kind": "flight",
            "departure_date": "2025-12-31",
            "planned_price": 1000,
            "airline_risk_score": 2
        }
    },
    "context": {
        "principal": {"type": "user", "id": "test-user"}
    },
    "options": {
        "dry_run": True,
        "explain": True
    }
}

print("Testing authz evaluate endpoint...")
print("Payload:")
print(json.dumps(payload, indent=2))

response = requests.post(
    "http://localhost:8002/v1/evaluate",
    json=payload,
    headers={"Authorization": "Bearer fake-token-for-testing"},
    verify=False
)

print(f"\nStatus: {response.status_code}")
print(f"Response:")
print(json.dumps(response.json(), indent=2))
