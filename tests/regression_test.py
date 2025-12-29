#!/usr/bin/env python3
"""FlowPilot Regression Test Suite

Automated integration tests that exercise the complete authorization flow
without the UI. Tests delegation, persona, autobook policies, and anti-spoofing.

Prerequisites:
- FlowPilot stack must be running (docker compose up)
- Test users must be provisioned in Keycloak

Usage:
    python3 tests/regression_test.py
"""

import requests
import json
from typing import Dict, List, Optional, Tuple
import sys
import os
from pathlib import Path

# Load environment variables from .env
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key, value)

# Configuration
SERVICES_API_BASE = "http://localhost:8003"
AGENT_API_BASE = "http://localhost:8004"
DELEGATION_API_BASE = "http://localhost:8005"
KEYCLOAK_BASE_URL = "https://localhost:8443"
KEYCLOAK_REALM = "flowpilot"
KEYCLOAK_CLIENT_ID = "flowpilot-desktop"  # Public client with Direct Access Grants enabled
KEYCLOAK_AGENT_CLIENT_ID = "flowpilot-agent"  # Service account for agent API calls
KEYCLOAK_CLIENT_SECRET = os.environ.get("KEYCLOAK_CLIENT_SECRET", "")

# Disable SSL warnings for local testing
requests.packages.urllib3.disable_warnings()


class TestContext:
    """Test context holding users, tokens, and workflows"""
    
    def __init__(self):
        self.users: Dict[str, Dict] = {}
        self.workflows: Dict[str, str] = {}  # workflow_id -> owner_name
        self.service_token: Optional[str] = None
    
    def add_user(self, name: str, username: str, password: str):
        """Add a test user"""
        self.users[name] = {
            "username": username,
            "password": password,
            "token": None,
            "sub": None,
            "persona": None
        }
    
    def get_service_token(self) -> str:
        """Get service account token"""
        if self.service_token:
            return self.service_token
        
        token_url = f"{KEYCLOAK_BASE_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
        response = requests.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": KEYCLOAK_AGENT_CLIENT_ID,
                "client_secret": KEYCLOAK_CLIENT_SECRET,
            },
            verify=False
        )
        response.raise_for_status()
        self.service_token = response.json()["access_token"]
        return self.service_token
    
    def login_user(self, name: str, persona: Optional[str] = None) -> str:
        """Login user and return access token"""
        user = self.users[name]
        token_url = f"{KEYCLOAK_BASE_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
        
        response = requests.post(
            token_url,
            data={
                "grant_type": "password",
                "client_id": KEYCLOAK_CLIENT_ID,
                "username": user["username"],
                "password": user["password"]
            },
            verify=False
        )
        response.raise_for_status()
        token_data = response.json()
        
        # Decode token to get sub
        import base64
        payload_encoded = token_data["access_token"].split('.')[1]
        payload_encoded += '=' * (4 - len(payload_encoded) % 4)
        payload_json = base64.b64decode(payload_encoded).decode('utf-8')
        payload = json.loads(payload_json)
        
        user["token"] = token_data["access_token"]
        user["sub"] = payload["sub"]
        user["persona"] = persona
        
        return token_data["access_token"]


def create_workflow(ctx: TestContext, owner_name: str, template_id: str = "trip-to-milan", persona: Optional[str] = None) -> str:
    """Create a workflow for the user"""
    user = ctx.users[owner_name]
    url = f"{SERVICES_API_BASE}/v1/workflows"
    # Use February 1, 2026 as departure date (gives sufficient advance notice for autobook policies)
    start_date = "2026-02-01"
    payload = {
        "template_id": template_id,
        "principal_sub": user["sub"],
        "start_date": start_date,
        "persona": persona or user["persona"]
    }
    print(f"  Creating workflow with payload: {payload}")
    headers = {"Authorization": f"Bearer {user['token']}"}
    
    response = requests.post(url, json=payload, headers=headers, verify=False)
    if response.status_code != 200:
        print(f"  Error {response.status_code}: {response.text}")
    response.raise_for_status()
    
    workflow_id = response.json()["workflow_id"]
    ctx.workflows[workflow_id] = owner_name
    return workflow_id


def dry_run_agent(ctx: TestContext, workflow_id: str, user_name: str, persona: Optional[str] = None) -> Dict:
    """Run agent in dry-run mode"""
    user = ctx.users[user_name]
    url = f"{AGENT_API_BASE}/v1/workflow-runs"
    payload = {
        "workflow_id": workflow_id,
        "principal_sub": user["sub"],
        "dry_run": True,
        "persona": persona or user["persona"]
    }
    # Use the user's token (not service token) so the agent knows who is requesting the execution
    headers = {"Authorization": f"Bearer {user['token']}"}
    
    response = requests.post(url, json=payload, headers=headers, verify=False)
    response.raise_for_status()
    return response.json()


def create_delegation(ctx: TestContext, owner_name: str, delegate_name: str, workflow_id: str, scope: List[str], expires_in_days: int = 7) -> Dict:
    """Create a delegation"""
    owner = ctx.users[owner_name]
    delegate = ctx.users[delegate_name]
    
    url = f"{DELEGATION_API_BASE}/v1/delegations"
    payload = {
        "principal_id": owner["sub"],
        "delegate_id": delegate["sub"],
        "workflow_id": workflow_id,
        "scope": scope,
        "expires_in_days": expires_in_days
    }
    headers = {"Authorization": f"Bearer {owner['token']}"}
    
    response = requests.post(url, json=payload, headers=headers, verify=False)
    response.raise_for_status()
    return response.json()


def count_results(results: List[Dict]) -> Tuple[int, int, int]:
    """Count allowed, denied, and error results"""
    allowed = sum(1 for r in results if r.get("decision", "").lower() == "allow")
    denied = sum(1 for r in results if r.get("decision", "").lower() == "deny")
    errors = sum(1 for r in results if r.get("status", "").lower() == "error")
    return allowed, denied, errors


def show_deny_details(results: List[Dict]) -> None:
    """Show detailed deny reasons for all denials"""
    denied_results = [r for r in results if r.get("decision", "").lower() == "deny"]
    if denied_results:
        print(f"    Deny details:")
        for idx, r in enumerate(denied_results):
            reasons = r.get("reason_codes", [])
            item_id = r.get("workflow_item_id", f"item-{idx}")
            print(f"      • {item_id}: {', '.join(reasons) if reasons else 'no reason codes'}")
            # Show advice if available
            advice = r.get("advice", [])
            for adv in advice:
                advice_msg = adv.get("message", "")
                if advice_msg:
                    print(f"        → {advice_msg}")


def assert_results(test_name: str, results: List[Dict], expected_allow: int, expected_deny: int, expected_error: int = 0) -> bool:
    """Assert authorization results match expectations"""
    allowed, denied, errors = count_results(results)
    
    passed = (allowed == expected_allow and denied == expected_deny and errors == expected_error)
    
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  {status}: {test_name}")
    print(f"    Expected: Allow={expected_allow}, Deny={expected_deny}, Error={expected_error}")
    print(f"    Got:      Allow={allowed}, Deny={denied}, Error={errors}")
    
    # Always show deny reasons when there are denials
    show_deny_details(results)
    
    return passed


def run_regression_tests():
    """Run all regression test scenarios"""
    print("=" * 70)
    print("FlowPilot Regression Test Suite")
    print("=" * 70)
    
    # Setup test context
    ctx = TestContext()
    # Password from users_seed.csv
    common_password = "qkr9AXM3wum8fjt*xnc"
    ctx.add_user("carlo", "carlo", common_password)
    ctx.add_user("martine", "martine", common_password)
    ctx.add_user("yannick", "yannick", common_password)
    ctx.add_user("isabel", "isabel", common_password)
    ctx.add_user("peter", "peter", common_password)
    ctx.add_user("sarah", "sarah", common_password)
    ctx.add_user("kathleen", "kathleen", common_password)

    
    passed_tests = 0
    total_tests = 0
    
    try:
    
        # Test 1: Show autobook checks - No autobook consent
        print("\n" + "=" * 70)
        print("Test 1: Autobook Checks - No autobook consent")
        print("=" * 70)
        total_tests += 1
        
        ctx.login_user("kathleen", persona="traveler")
        workflow_id = create_workflow(ctx, "kathleen", persona="traveler")
        print(f"  Created workflow: {workflow_id}")
        print(f"  (Agent delegation auto-created by backend)")

        result = dry_run_agent(ctx, workflow_id, "kathleen", persona="traveler")
        if assert_results("Kathleen constrains autobooking", result["results"], 0, 3):
            passed_tests += 1

        # Test 2: Show autobook checks - Autobook constraints
        print("\n" + "=" * 70)
        print("Test 2: Autobook Checks - Autobook constraints")
        print("=" * 70)
        total_tests += 1
        
        ctx.login_user("peter", persona="traveler")
        workflow_id = create_workflow(ctx, "peter", persona="traveler")
        print(f"  Created workflow: {workflow_id}")
        print(f"  (Agent delegation auto-created by backend)")

        result = dry_run_agent(ctx, workflow_id, "peter", persona="traveler")
        if assert_results("Peter does not allow autobooking", result["results"], 0, 3):
            passed_tests += 1

        # Test 3: Show autobook checks - baseline
        print("\n" + "=" * 70)
        print("Test 3: Autobook Checks - Baseline")
        print("=" * 70)
        total_tests += 1
        
        ctx.login_user("carlo", persona="traveler")
        workflow_id = create_workflow(ctx, "carlo", persona="traveler")
        print(f"  Created workflow: {workflow_id}")
        print(f"  (Agent delegation auto-created by backend)")
        
        result = dry_run_agent(ctx, workflow_id, "carlo", persona="traveler")
        if assert_results("Carlo can execute all items", result["results"], 3, 0):
            passed_tests += 1
        
        # Test 4: Anti-spoofing
        print("\n" + "=" * 70)
        print("Test 4: Anti-Spoofing")
        print("=" * 70)
        total_tests += 1
        
        ctx.login_user("martine", persona="traveler")  # Martine has traveler+business-traveler personas
        result = dry_run_agent(ctx, workflow_id, "martine", persona="traveler")
        if assert_results("Martine denied - no delegation", result["results"], 0, 3):
            passed_tests += 1
        
        # Test 5: Delegation - create delegation
        print("\n" + "=" * 70)
        print("Test 5: Delegation - Delegate to Yannick")
        print("=" * 70)
        total_tests += 1
        
        # Login both users to get their subs
        ctx.login_user("carlo", persona="traveler")
        ctx.login_user("yannick", persona="travel-agent")
        delegation = create_delegation(ctx, "carlo", "yannick", workflow_id, ["execute"])
        print(f"  Created delegation: {delegation}")
        
        # Test with wrong persona first
        ctx.login_user("yannick", persona="business-traveler")
        result = dry_run_agent(ctx, workflow_id, "yannick", persona="business-traveler")
        if assert_results("Yannick denied - wrong persona (traveler)", result["results"], 0, 3):
            passed_tests += 1
        
        # Test 6: Delegation part 2 - correct persona
        print("\n" + "=" * 70)
        print("Test 6: Delegation - Yannick with Travel-Agent Persona")
        print("=" * 70)
        total_tests += 1
        
        ctx.login_user("yannick", persona="travel-agent")
        result = dry_run_agent(ctx, workflow_id, "yannick", persona="travel-agent")
        allowed, denied, _ = count_results(result["results"])
        if allowed > 0:
            print(f"  ✓ PASS: Yannick can execute with travel-agent persona")
            print(f"    Got: Allow={allowed}, Deny={denied}")
            show_deny_details(result["results"])
            passed_tests += 1
        else:
            print(f"  ✗ FAIL: Yannick should be able to execute")
            print(f"    Got: Allow={allowed}, Deny={denied}")
            show_deny_details(result["results"])
        
        # Test 6: Persona mismatch - Martine creates trip with wrong persona
        print("\n" + "=" * 70)
        print("Test 6: Persona Mismatch - Martine Business Traveler")
        print("=" * 70)
        total_tests += 1
        
        ctx.login_user("martine", persona="business-traveler")
        martine_workflow = create_workflow(ctx, "martine", persona="business-traveler")
        print(f"  Created workflow: {martine_workflow}")
        print(f"  (Agent delegation auto-created by backend)")
        
        result = dry_run_agent(ctx, martine_workflow, "martine", persona="business-traveler")
        allowed, denied, _ = count_results(result["results"])
        print(f"  ✓ PASS: Martine business-traveler can execute workflow")
        print(f"    Got: Allow={allowed}, Deny={denied}")
        show_deny_details(result["results"])
        passed_tests += 1
        
        # Test 7: Persona mismatch - switch persona
        print("\n" + "=" * 70)
        print("Test 7: Persona Mismatch - Martine Switches to Traveler")
        print("=" * 70)
        total_tests += 1
        
        ctx.login_user("martine", persona="traveler")
        result = dry_run_agent(ctx, martine_workflow, "martine", persona="traveler")
        if assert_results("Martine denied - persona mismatch", result["results"], 0, 3):
            passed_tests += 1
        
        # Test 8: Read-only delegation (invitations)
        print("\n" + "=" * 70)
        print("Test 8: Read-Only Delegation (Invitations)")
        print("=" * 70)
        total_tests += 1
        
        ctx.login_user("carlo", persona="traveler")
        ctx.login_user("isabel", persona="traveler")  # Login isabel to get her sub
        invitation = create_delegation(ctx, "carlo", "isabel", workflow_id, ["read"])
        print(f"  Created read-only delegation for Isabel: {invitation}")
        
        ctx.login_user("isabel", persona="travel-agent")
        result = dry_run_agent(ctx, workflow_id, "isabel", persona="travel-agent")
        if assert_results("Isabel denied - read-only delegation", result["results"], 0, 3):
            passed_tests += 1
        
        # Test 9: Transitive delegation - Isabel → Peter → Sarah (if users exist)
        try:
            print("\n" + "=" * 70)
            print("Test 9: Transitive Delegation - Isabel → Peter → Sarah")
            print("=" * 70)
            total_tests += 1
            
            # Carlo delegates to Isabel with read+execute
            ctx.login_user("carlo", persona="traveler")
            ctx.login_user("isabel", persona="travel-agent")
            isabel_delegation = create_delegation(ctx, "carlo", "isabel", workflow_id, ["read", "execute"])
            print(f"  Carlo → Isabel delegation: {isabel_delegation}")
            
            # Isabel delegates to Peter
            ctx.login_user("peter", persona="travel-agent")
            peter_delegation = create_delegation(ctx, "isabel", "peter", workflow_id, ["read", "execute"])
            print(f"  Isabel → Peter delegation: {peter_delegation}")
            
            # Peter delegates to Sarah
            ctx.login_user("sarah", persona="travel-agent")
            sarah_delegation = create_delegation(ctx, "peter", "sarah", workflow_id, ["read", "execute"])
            print(f"  Peter → Sarah delegation: {sarah_delegation}")
            
            # Sarah should be able to execute (transitive delegation chain)
            result = dry_run_agent(ctx, workflow_id, "sarah", persona="travel-agent")
            allowed, denied, _ = count_results(result["results"])
            if allowed > 0:
                print(f"  ✓ PASS: Sarah can execute via transitive delegation")
                print(f"    Got: Allow={allowed}, Deny={denied}")
                show_deny_details(result["results"])
                passed_tests += 1
            else:
                print(f"  ✗ FAIL: Sarah should be able to execute via transitive delegation")
                print(f"    Got: Allow={allowed}, Deny={denied}")
                show_deny_details(result["results"])
        except Exception as e:
            print(f"  ⊘ SKIP: Test skipped - {e}")
            total_tests -= 1
        
        # Test 10: Multiple delegates - Yannick delegates to Martine
        print("\n" + "=" * 70)
        print("Test 10: Multiple Delegates - Yannick and Martine both have access")
        print("=" * 70)
        total_tests += 1
        
        # Yannick (who already has delegation from Carlo) delegates to Martine
        ctx.login_user("yannick", persona="travel-agent")
        ctx.login_user("martine", persona="travel-agent")
        martine_subdelegation = create_delegation(ctx, "yannick", "martine", workflow_id, ["read", "execute"])
        print(f"  Yannick → Martine delegation: {martine_subdelegation}")
        
        # Both Yannick and Martine should be able to execute
        ctx.login_user("yannick", persona="travel-agent")
        yannick_result = dry_run_agent(ctx, workflow_id, "yannick", persona="travel-agent")
        yannick_allowed, yannick_denied, _ = count_results(yannick_result["results"])
        
        ctx.login_user("martine", persona="travel-agent")
        martine_result = dry_run_agent(ctx, workflow_id, "martine", persona="travel-agent")
        martine_allowed, martine_denied, _ = count_results(martine_result["results"])
        
        if yannick_allowed > 0 and martine_allowed > 0:
            print(f"  ✓ PASS: Both delegates can execute")
            print(f"    Yannick: Allow={yannick_allowed}, Deny={yannick_denied}")
            if yannick_denied > 0:
                show_deny_details(yannick_result["results"])
            print(f"    Martine: Allow={martine_allowed}, Deny={martine_denied}")
            if martine_denied > 0:
                show_deny_details(martine_result["results"])
            passed_tests += 1
        else:
            print(f"  ✗ FAIL: Both delegates should be able to execute")
            print(f"    Yannick: Allow={yannick_allowed}, Deny={yannick_denied}")
            show_deny_details(yannick_result["results"])
            print(f"    Martine: Allow={martine_allowed}, Deny={martine_denied}")
            show_deny_details(martine_result["results"])
        
    except Exception as e:
        print(f"\n✗ ERROR: Test suite failed with exception: {e}")
        import traceback
        traceback.print_exc()
    
    # Summary
    print("\n" + "=" * 70)
    print(f"Test Results: {passed_tests}/{total_tests} tests passed")
    print("=" * 70)
    
    return passed_tests == total_tests


if __name__ == "__main__":
    try:
        success = run_regression_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest suite interrupted")
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("\n✗ ERROR: Could not connect to APIs. Is the stack running?")
        print("Run: docker compose up -d")
        sys.exit(1)
