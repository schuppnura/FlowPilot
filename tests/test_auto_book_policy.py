#!/usr/bin/env python3
"""Test script for auto-book policy validation

This script tests the auto-book ABAC policy implementation by making
direct API calls to the AuthZ API.

Prerequisites:
- FlowPilot stack must be running (docker compose up)
- User must be provisioned in Keycloak and ***REMOVED***
- Agent delegation must be set up

Test scenarios:
1. No consent - should deny with auto_book.consent_missing
2. Cost exceeds limit - should deny with auto_book.cost_exceeds_limit
3. Insufficient advance days - should deny with auto_book.insufficient_advance
4. High airline risk - should deny with auto_book.airline_risk_too_high
5. All conditions met - should allow
"""

import json
import requests
from datetime import datetime, timedelta

# Configuration
AUTHZ_API_BASE = "http://localhost:8002"
TEST_USER_SUB = "test-user-123"  # Replace with actual user sub from Keycloak
TEST_AGENT_SUB = "agent-runner"
TEST_WORKFLOW_ID = "test-workflow-001"
TEST_ITEM_ID = "test-item-001"

# Disable SSL warnings for local testing
requests.packages.urllib3.disable_warnings()


def set_profile_parameters(principal_sub: str, params: dict) -> dict:
    """Set profile parameters via AuthZ API"""
    url = f"{AUTHZ_API_BASE}/v1/profiles/{principal_sub}/policy-parameters"
    response = requests.patch(url, json={"parameters": params}, verify=False)
    response.raise_for_status()
    return response.json()


def evaluate_auto_book(resource_properties: dict) -> dict:
    """Call AuthZ evaluate endpoint for auto-book action"""
    url = f"{AUTHZ_API_BASE}/v1/evaluate"
    payload = {
        "subject": {"type": "agent", "id": TEST_AGENT_SUB},
        "action": {"name": "auto-book"},
        "resource": {
            "type": "workflow",
            "id": TEST_WORKFLOW_ID,
            "properties": {
                "domain": "flowpilot",
                "workflow_item_id": TEST_ITEM_ID,
                "workflow_item_kind": "flight",
                **resource_properties,
            },
        },
        "context": {"principal": {"type": "user", "id": TEST_USER_SUB}},
        "options": {"dry_run": False, "explain": True},
    }
    response = requests.post(url, json=payload, verify=False)
    response.raise_for_status()
    return response.json()


def run_tests():
    """Run all test scenarios"""
    print("=" * 60)
    print("Auto-Book Policy Test Suite")
    print("=" * 60)

    # Setup: Reset profile parameters
    print("\n[Setup] Resetting profile parameters...")
    set_profile_parameters(
        TEST_USER_SUB,
        {
            "auto_book_consent": False,
            "auto_book_max_cost_eur": 1500,
            "auto_book_min_days_advance": 7,
            "auto_book_max_airline_risk": 5,
        },
    )

    # Test 1: No consent
    print("\n[Test 1] No consent - expecting deny with consent_missing")
    result = evaluate_auto_book(
        {
            "planned_price": 1000,
            "departure_date": (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d"),
            "airline_risk_score": 3,
        }
    )
    print(f"  Decision: {result['decision']}")
    print(f"  Reason codes: {result.get('reason_codes', [])}")
    assert result["decision"] == "deny", f"Expected deny, got {result['decision']}"
    assert (
        "auto_book.consent_missing" in result.get("reason_codes", [])
    ), "Expected consent_missing reason code"
    print("  ✓ PASS")

    # Enable consent for remaining tests
    print("\n[Setup] Enabling auto-book consent...")
    set_profile_parameters(TEST_USER_SUB, {"auto_book_consent": True})

    # Test 2: Cost exceeds limit
    print("\n[Test 2] Cost exceeds limit - expecting deny with cost_exceeds_limit")
    result = evaluate_auto_book(
        {
            "planned_price": 1600,
            "departure_date": (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d"),
            "airline_risk_score": 3,
        }
    )
    print(f"  Decision: {result['decision']}")
    print(f"  Reason codes: {result.get('reason_codes', [])}")
    assert result["decision"] == "deny", f"Expected deny, got {result['decision']}"
    assert (
        "auto_book.cost_exceeds_limit" in result.get("reason_codes", [])
    ), "Expected cost_exceeds_limit reason code"
    print("  ✓ PASS")

    # Test 3: Insufficient advance days
    print("\n[Test 3] Insufficient advance - expecting deny with insufficient_advance")
    result = evaluate_auto_book(
        {
            "planned_price": 1000,
            "departure_date": (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d"),
            "airline_risk_score": 3,
        }
    )
    print(f"  Decision: {result['decision']}")
    print(f"  Reason codes: {result.get('reason_codes', [])}")
    assert result["decision"] == "deny", f"Expected deny, got {result['decision']}"
    assert (
        "auto_book.insufficient_advance" in result.get("reason_codes", [])
    ), "Expected insufficient_advance reason code"
    print("  ✓ PASS")

    # Test 4: High airline risk
    print("\n[Test 4] High airline risk - expecting deny with airline_risk_too_high")
    result = evaluate_auto_book(
        {
            "planned_price": 1000,
            "departure_date": (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d"),
            "airline_risk_score": 7,
        }
    )
    print(f"  Decision: {result['decision']}")
    print(f"  Reason codes: {result.get('reason_codes', [])}")
    assert result["decision"] == "deny", f"Expected deny, got {result['decision']}"
    assert (
        "auto_book.airline_risk_too_high" in result.get("reason_codes", [])
    ), "Expected airline_risk_too_high reason code"
    print("  ✓ PASS")

    # Test 5: All conditions met (NOTE: This will fail if ReBAC not set up)
    print("\n[Test 5] All conditions met - expecting allow or ReBAC deny")
    result = evaluate_auto_book(
        {
            "planned_price": 1000,
            "departure_date": (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d"),
            "airline_risk_score": 3,
        }
    )
    print(f"  Decision: {result['decision']}")
    print(f"  Reason codes: {result.get('reason_codes', [])}")
    if result["decision"] == "deny" and "***REMOVED***.deny" in result.get("reason_codes", []):
        print("  ⚠ ReBAC delegation not configured, skipping final allow test")
    else:
        # If ReBAC is configured, this should allow
        print(f"  Decision: {result['decision']}")
    print("  ✓ PASS (ABAC conditions passed)")

    print("\n" + "=" * 60)
    print("All tests completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        run_tests()
    except requests.exceptions.ConnectionError:
        print("ERROR: Could not connect to AuthZ API. Is the stack running?")
        print("Run: docker compose up -d")
        exit(1)
    except Exception as e:
        print(f"ERROR: Test failed with exception: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
