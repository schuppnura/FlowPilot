#!/usr/bin/env python3
import requests
import json
import urllib3
urllib3.disable_warnings()

# Test the exact workflow/item from the macOS app
payload = {
    "subject": {"type": "agent", "id": "agent-runner"},
    "action": {"name": "auto-book"},
    "resource": {
        "type": "workflow",
        "id": "t_1302005a",
        "properties": {
            "domain": "flowpilot",
            "workflow_item_id": "i_83675f88",
            "workflow_item_kind": "hotel",
            "planned_price": 2220,
            "departure_date": "2025-12-31"
        }
    },
    "context": {
        "principal": {"type": "user", "id": "2129b076-cd98-4f7b-a101-7d0fa228b1c3"}
    },
    "options": {
        "dry_run": True,
        "explain": True
    }
}

# Get service token
token_resp = requests.post(
    "https://localhost:8443/realms/flowpilot/protocol/openid-connect/token",
    data={
        "grant_type": "client_credentials",
        "client_id": "flowpilot-agent",
        "client_secret": "DbUpdfiTCgA1GnYlgPduhQDv84R3t65q"
    },
    verify=False
)
token_data = token_resp.json()
if "access_token" not in token_data:
    print(f"Token error: {token_data}")
    exit(1)
token = token_data["access_token"]

# Call authz-api
r = requests.post(
    "http://localhost:8002/v1/evaluate",
    json=payload,
    headers={"Authorization": f"Bearer {token}"}
)

print(f"Status: {r.status_code}")
print("Response:")
print(json.dumps(r.json(), indent=2))
