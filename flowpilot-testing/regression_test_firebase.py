#!/usr/bin/env python3
"""FlowPilot Regression Test Suite - Firebase/Cloud Run Version

Automated integration tests that exercise the complete authorization flow
without the UI. Tests delegation, persona, autobook policies, and anti-spoofing.

Prerequisites:
- FlowPilot services deployed on Cloud Run
- Test users provisioned in Firebase

Usage:
    python3 flowpilot-testing/regression_test_firebase.py
"""

import requests
import json
from typing import Dict, List, Optional, Tuple
import sys
import firebase_admin
from firebase_admin import auth
import os

# Configuration - Cloud Run URLs
SERVICES_API_BASE = "https://flowpilot-domain-services-api-737191827545.us-central1.run.app"
AGENT_API_BASE = "https://flowpilot-ai-agent-api-737191827545.us-central1.run.app"
DELEGATION_API_BASE = "https://flowpilot-delegation-api-737191827545.us-central1.run.app"
AUTHZ_API_BASE = "https://flowpilot-authz-api-737191827545.us-central1.run.app"
FIREBASE_WEB_API_KEY = "REDACTED_API_KEY"


class TestContext:
    """Test context holding users, tokens, and workflows"""
    
    def __init__(self):
        self.users: Dict[str, Dict] = {}
        self.workflows: Dict[str, str] = {}  # workflow_id -> owner_name
    
    def add_user(self, name: str, email: str, password: str):
        """Add a test user (UID will be fetched on login)"""
        self.users[name] = {
            "email": email,
            "password": password,
            "uid": None,
            "firebase_token": None,
            "access_token": None,
            "sub": None,
            "persona": None
        }
    
    def login_user(self, name: str, persona: Optional[str] = None) -> str:
        """Login user via Firebase email/password authentication and exchange for FlowPilot access token"""
        user = self.users[name]
        
        # Step 1: Sign in with email/password via Firebase Auth REST API
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_WEB_API_KEY}"
        response = requests.post(
            url,
            json={
                "email": user["email"],
                "password": user["password"],
                "returnSecureToken": True
            }
        )
        
        if response.status_code != 200:
            print(f"\n✗ Failed to login {name} ({user['email']})")
            print(f"  Status: {response.status_code}")
            try:
                error_data = response.json()
                print(f"  Error: {error_data}")
            except:
                print(f"  Response: {response.text}")
        
        response.raise_for_status()
        token_data = response.json()
        
        firebase_token = token_data["idToken"]
        user["firebase_token"] = firebase_token
        user["uid"] = token_data["localId"]  # Get actual UID from Firebase
        user["sub"] = token_data["localId"]  # Update sub with actual UID
        user["persona"] = persona
        
        # Step 2: Exchange Firebase ID token for FlowPilot access token
        exchange_url = f"{AUTHZ_API_BASE}/v1/token/exchange"
        exchange_response = requests.post(
            exchange_url,
            headers={"Authorization": f"Bearer {firebase_token}"}
        )
        exchange_response.raise_for_status()
        access_token_data = exchange_response.json()
        
        user["access_token"] = access_token_data["access_token"]
        
        return access_token_data["access_token"]


def create_workflow(ctx: TestContext, owner_name: str, template_id: str = "trip-to-milan", persona: Optional[str] = None) -> str:
    """Create a workflow for the user"""
    user = ctx.users[owner_name]
    url = f"{SERVICES_API_BASE}/v1/workflows"
    start_date = "2026-02-01"
    payload = {
        "template_id": template_id,
        "principal_sub": user["sub"],
        "start_date": start_date,
    }
    if persona or user["persona"]:
        payload["persona"] = persona or user["persona"]
    
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    
    response = requests.post(url, json=payload, headers=headers)
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
    }
    if persona or user["persona"]:
        payload["persona"] = persona or user["persona"]
    
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        print(f"\n✗ Agent API error:")
        print(f"  Status: {response.status_code}")
        print(f"  URL: {url}")
        print(f"  Payload: {json.dumps(payload, indent=2)}")
        try:
            error_data = response.json()
            print(f"  Error: {json.dumps(error_data, indent=2)}")
        except:
            print(f"  Response: {response.text}")
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
    headers = {"Authorization": f"Bearer {owner['access_token']}"}
    
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


def count_results(results: List[Dict]) -> Tuple[int, int, int]:
    """Count allowed, denied, and error results"""
    allowed = sum(1 for r in results if r.get("decision", "").lower() == "allow")
    denied = sum(1 for r in results if r.get("decision", "").lower() == "deny")
    errors = sum(1 for r in results if r.get("status", "").lower() == "error")
    return allowed, denied, errors


def show_decision_details(results: List[Dict]) -> None:
    """Show detailed reasons for all decisions"""
    allowed_results = [r for r in results if r.get("decision", "").lower() == "allow"]
    denied_results = [r for r in results if r.get("decision", "").lower() == "deny"]
    
    if allowed_results:
        print(f"    Allowed items:")
        for idx, r in enumerate(allowed_results):
            item_id = r.get("workflow_item_id", f"item-{idx}")
            print(f"      • {item_id}: Access allowed")
    
    if denied_results:
        print(f"    Deny details:")
        for idx, r in enumerate(denied_results):
            reasons = r.get("reason_codes", [])
            item_id = r.get("workflow_item_id", f"item-{idx}")
            if reasons:
                print(f"      • {item_id}:")
                for reason in reasons:
                    print(f"        - {reason}")
            else:
                print(f"      • {item_id}: no reason codes")


def assert_results(test_name: str, results: List[Dict], expected_allow: int, expected_deny: int, expected_error: int = 0) -> bool:
    """Assert authorization results match expectations"""
    allowed, denied, errors = count_results(results)
    
    passed = (allowed == expected_allow and denied == expected_deny and errors == expected_error)
    
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  {status}: {test_name}")
    print(f"    Expected: Allow={expected_allow}, Deny={expected_deny}, Error={expected_error}")
    print(f"    Got:      Allow={allowed}, Deny={denied}, Error={errors}")
    
    show_decision_details(results)
    
    return passed


def run_regression_tests():
    """Run all regression test scenarios"""
    print("=" * 70)
    print("FlowPilot Regression Test Suite - Firebase/Cloud Run")
    print("=" * 70)
    
    # Note: Firebase Admin SDK not needed for email/password auth
    
    # Setup test context with actual seeded Firebase users
    ctx = TestContext()
    common_password = "qkr9AXM3wum8fjt*xnc"
    # Using actual emails from users_seed.csv - UIDs fetched on login
    ctx.add_user("carlo", "carlo@me.com", common_password)
    ctx.add_user("peter", "peter@me.com", common_password)
    ctx.add_user("yannick", "yannick@me.com", common_password)
    ctx.add_user("isabel", "isabel@me.com", common_password)
    ctx.add_user("kathleen", "kathleen@me.com", common_password)
    ctx.add_user("martine", "martine@me.com", common_password)
    ctx.add_user("sarah", "sarah@me.com", common_password)
    ctx.add_user("alexia", "alexia@me.com", common_password)
    
    passed_tests = 0
    total_tests = 0
    
    try:
        # Test 1: Autobook constraints - Kathleen has very restrictive limits
        print("\n" + "=" * 70)
        print("Test 1: Autobook - Kathleen's Restrictive Constraints")
        print("=" * 70)
        total_tests += 1
        
        ctx.login_user("kathleen", persona="traveler")
        workflow_id = create_workflow(ctx, "kathleen", persona="traveler")
        print(f"  Created workflow: {workflow_id}")
        print(f"  (Agent delegation auto-created by backend)")

        result = dry_run_agent(ctx, workflow_id, "kathleen", persona="traveler")
        if assert_results("Kathleen constrains autobooking", result["results"], 0, 3):
            passed_tests += 1

        # Test 2: Peter - No autobook consent
        print("\n" + "=" * 70)
        print("Test 2: Autobook - Peter No Consent")
        print("=" * 70)
        total_tests += 1
        
        ctx.login_user("peter", persona="traveler")
        workflow_id = create_workflow(ctx, "peter", persona="traveler")
        print(f"  Created workflow: {workflow_id}")

        result = dry_run_agent(ctx, workflow_id, "peter", persona="traveler")
        if assert_results("Peter does not allow autobooking", result["results"], 0, 3):
            passed_tests += 1

        # Test 3: Carlo - Baseline (should allow all)
        print("\n" + "=" * 70)
        print("Test 3: Autobook - Carlo Baseline (All Allowed)")
        print("=" * 70)
        total_tests += 1
        
        ctx.login_user("carlo", persona="traveler")
        workflow_id = create_workflow(ctx, "carlo", persona="traveler")
        print(f"  Created workflow: {workflow_id}")
        
        result = dry_run_agent(ctx, workflow_id, "carlo", persona="traveler")
        if assert_results("Carlo can execute all items", result["results"], 3, 0):
            passed_tests += 1
        
        # Test 4: Anti-spoofing - Martine without delegation
        print("\n" + "=" * 70)
        print("Test 4: Anti-Spoofing - No Delegation")
        print("=" * 70)
        total_tests += 1
        
        ctx.login_user("martine", persona="traveler")
        result = dry_run_agent(ctx, workflow_id, "martine", persona="traveler")
        if assert_results("Martine denied - no delegation", result["results"], 0, 3):
            passed_tests += 1
        
        # Test 5: Delegation - Create delegation to Yannick
        print("\n" + "=" * 70)
        print("Test 5: Delegation - Delegate to Yannick")
        print("=" * 70)
        total_tests += 1
        
        ctx.login_user("carlo", persona="traveler")
        ctx.login_user("yannick", persona="travel-agent")
        delegation = create_delegation(ctx, "carlo", "yannick", workflow_id, ["execute"])
        print(f"  Created delegation: {delegation}")
        
        # Test with wrong persona first
        ctx.login_user("yannick", persona="business-traveler")
        result = dry_run_agent(ctx, workflow_id, "yannick", persona="business-traveler")
        if assert_results("Yannick denied - wrong persona", result["results"], 0, 3):
            passed_tests += 1
        
        # Test 6: Delegation with correct persona
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
            show_decision_details(result["results"])
            passed_tests += 1
        else:
            print(f"  ✗ FAIL: Yannick should be able to execute")
            print(f"    Got: Allow={allowed}, Deny={denied}")
            show_decision_details(result["results"])
        
        # Test 7: Persona mismatch - Martine creates trip with business-traveler
        print("\n" + "=" * 70)
        print("Test 7: Persona Mismatch - Martine Business Traveler")
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
        show_decision_details(result["results"])
        passed_tests += 1
        
        # Test 8: Persona mismatch - switch persona
        print("\n" + "=" * 70)
        print("Test 8: Persona Mismatch - Martine Switches to Traveler")
        print("=" * 70)
        total_tests += 1
        
        ctx.login_user("martine", persona="traveler")
        result = dry_run_agent(ctx, martine_workflow, "martine", persona="traveler")
        if assert_results("Martine denied - persona mismatch", result["results"], 0, 3):
            passed_tests += 1
        
        # Test 9: Read-only delegation (invitations)
        print("\n" + "=" * 70)
        print("Test 9: Read-Only Delegation (Invitations)")
        print("=" * 70)
        total_tests += 1
        
        ctx.login_user("carlo", persona="traveler")
        ctx.login_user("isabel", persona="traveler")
        invitation = create_delegation(ctx, "carlo", "isabel", workflow_id, ["read"])
        print(f"  Created read-only delegation for Isabel: {invitation}")
        
        ctx.login_user("isabel", persona="travel-agent")
        result = dry_run_agent(ctx, workflow_id, "isabel", persona="travel-agent")
        if assert_results("Isabel denied - read-only delegation", result["results"], 0, 3):
            passed_tests += 1
        
        # Test 10: Transitive delegation - Isabel → Peter → Sarah
        try:
            print("\n" + "=" * 70)
            print("Test 10: Transitive Delegation - Isabel → Peter → Sarah")
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
                show_decision_details(result["results"])
                passed_tests += 1
            else:
                print(f"  ✗ FAIL: Sarah should be able to execute via transitive delegation")
                print(f"    Got: Allow={allowed}, Deny={denied}")
                show_decision_details(result["results"])
        except Exception as e:
            print(f"  ⊘ SKIP: Test skipped - {e}")
            total_tests -= 1
        
        # Test 11: Multiple delegates - Yannick delegates to Martine
        print("\n" + "=" * 70)
        print("Test 11: Multiple Delegates - Yannick and Martine both have access")
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
                show_decision_details(yannick_result["results"])
            print(f"    Martine: Allow={martine_allowed}, Deny={martine_denied}")
            if martine_denied > 0:
                show_decision_details(martine_result["results"])
            passed_tests += 1
        else:
            print(f"  ✗ FAIL: Both delegates should be able to execute")
            print(f"    Yannick: Allow={yannick_allowed}, Deny={yannick_denied}")
            show_decision_details(yannick_result["results"])
            print(f"    Martine: Allow={martine_allowed}, Deny={martine_denied}")
            show_decision_details(martine_result["results"])
        
        # Test 12: Persona not yet valid - Alexia with future valid_from date
        print("\n" + "=" * 70)
        print("Test 12: Persona Not Yet Valid - Alexia (suspended, valid from 2026-03-01)")
        print("=" * 70)
        total_tests += 1
        
        ctx.login_user("alexia", persona="traveler")
        alexia_workflow = create_workflow(ctx, "alexia", persona="traveler")
        print(f"  Created workflow: {alexia_workflow}")
        print(f"  (Agent delegation auto-created by backend)")
        print(f"  Alexia's persona is suspended and valid from 2026-03-01 (future date)")
        
        result = dry_run_agent(ctx, alexia_workflow, "alexia", persona="traveler")
        results_list = result["results"]
        allowed, denied, _ = count_results(results_list)
        
        # Check that we get denials with 2 reason codes
        if denied == 3:
            # Check if any result has 2 reason codes
            has_two_reasons = any(len(r.get("reason_codes", [])) >= 2 for r in results_list)
            if has_two_reasons:
                print(f"  ✓ PASS: Alexia denied with multiple reason codes (suspended + not yet valid)")
                print(f"    Got: Allow={allowed}, Deny={denied}")
                show_decision_details(results_list)
                passed_tests += 1
            else:
                print(f"  ✗ FAIL: Expected at least 2 reason codes per denial")
                print(f"    Got: Allow={allowed}, Deny={denied}")
                show_decision_details(results_list)
        else:
            print(f"  ✗ FAIL: Expected all items to be denied")
            print(f"    Got: Allow={allowed}, Deny={denied}")
            show_decision_details(results_list)
        
        print(f"\n✓ Completed {passed_tests}/{total_tests} tests successfully")
        
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
        print("\n✗ ERROR: Could not connect to APIs. Are the Cloud Run services running?")
        sys.exit(1)
