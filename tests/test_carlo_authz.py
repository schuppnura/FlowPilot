#!/usr/bin/env python3
import requests
import json

# Carlo's sub from provisioning output
carlo_sub = "2129b076-cd98-4f7b-a101-7d0fa228b1c3"

payload = {
    "subject": {"type": "agent", "id": "agent-runner"},
    "action": {"name": "auto-book"},
    "resource": {
        "type": "workflow",
        "id": "test-workflow-carlo",
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
        "principal": {"type": "user", "id": carlo_sub}
    },
    "options": {
        "dry_run": True,
        "explain": True
    }
}

print(f"Testing with Carlo's sub: {carlo_sub}")
response = requests.post(
    "http://localhost:8002/v1/evaluate",
    json=payload,
    headers={"Authorization": "Bearer fake"},
    verify=False
)

print(f"Status: {response.status_code}")
result = response.json()
print(f"Decision: {result['decision']}")
print(f"Reason codes: {result.get('reason_codes', [])}")
if result.get('advice'):
    for adv in result['advice']:
        print(f"  - {adv.get('code')}: {adv.get('message')}")
