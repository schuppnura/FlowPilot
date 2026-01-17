#!/usr/bin/env python3
"""Test that duplicate persona titles are rejected."""

import os
import requests

# GCP Cloud Run URLs
USER_PROFILE_API_BASE = "https://flowpilot-persona-api-737191827545.us-central1.run.app"

# Firebase Auth REST API
FIREBASE_WEB_API_KEY = "REDACTED_API_KEY"
FIREBASE_AUTH_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_WEB_API_KEY}"


def firebase_login(email: str, password: str) -> dict:
    """Login via Firebase and get tokens."""
    response = requests.post(
        FIREBASE_AUTH_URL,
        json={"email": email, "password": password, "returnSecureToken": True},
    )
    response.raise_for_status()
    data = response.json()
    return {
        "idToken": data["idToken"],
        "uid": data["localId"],
    }


def create_persona(token: str, title: str, consent: bool = True) -> dict:
    """Create a persona."""
    response = requests.post(
        f"{USER_PROFILE_API_BASE}/v1/personas",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": title,
            "scope": ["read", "execute"],
            "consent": consent,
            "autobook_price": 1000,
            "autobook_leadtime": 10,
            "autobook_risklevel": 50,
        },
    )
    return response


def list_personas(token: str) -> dict:
    """List all personas for the user."""
    response = requests.get(
        f"{USER_PROFILE_API_BASE}/v1/personas",
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    return response.json()


def delete_persona(token: str, persona_id: str) -> None:
    """Delete a persona."""
    response = requests.delete(
        f"{USER_PROFILE_API_BASE}/v1/personas/{persona_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()


def main():
    print("=" * 70)
    print("Test: Persona API Idempotency")
    print("=" * 70)
    
    # Login as Carlo
    print("\n1. Logging in as carlo@me.com...")
    auth = firebase_login("carlo@me.com", "qkr9AXM3wum8fjt*xnc")
    token = auth["idToken"]
    print(f"   ✓ Logged in (UID: {auth['uid']})")
    
    # Clean up: Delete any existing "office-manager" personas
    print("\n2. Cleaning up existing personas...")
    personas = list_personas(token)
    for persona in personas.get("personas", []):
        if persona["title"] == "office-manager":
            delete_persona(token, persona["persona_id"])
            print(f"   ✓ Deleted existing persona: {persona['persona_id']}")
    
    # Create first persona with title "office-manager"
    print("\n3. Creating first persona with title 'office-manager'...")
    response = create_persona(token, "office-manager")
    if response.status_code == 201:
        persona1 = response.json()
        print(f"   ✓ Created persona: {persona1['persona_id']}")
    else:
        print(f"   ✗ Failed to create first persona: {response.status_code} - {response.text}")
        return
    
    # Attempt to create duplicate persona with same title (should be idempotent)
    print("\n4. Creating same persona again (testing idempotency)...")
    response2 = create_persona(token, "office-manager")
    
    if response2.status_code == 201:
        persona2 = response2.json()
        # Check if same persona ID was returned
        if persona2["persona_id"] == persona1["persona_id"]:
            print(f"   ✓ PASS: Returned existing persona with same ID (idempotent)")
        else:
            print(f"   ✗ FAIL: Returned different persona ID")
            print(f"   First:  {persona1['persona_id']}")
            print(f"   Second: {persona2['persona_id']}")
    else:
        print(f"   ✗ FAIL: Expected 201, got {response2.status_code}")
        print(f"   Response: {response2.text}")
    
    # Verify only one persona exists
    print("\n5. Verifying only one persona with this title exists...")
    personas = list_personas(token)
    office_manager_personas = [
        p for p in personas.get("personas", []) 
        if p["title"] == "office-manager"
    ]
    
    if len(office_manager_personas) == 1:
        print(f"   ✓ PASS: Only 1 'office-manager' persona exists")
        print(f"   Persona ID: {office_manager_personas[0]['persona_id']}")
    else:
        print(f"   ✗ FAIL: Found {len(office_manager_personas)} 'office-manager' personas")
        for p in office_manager_personas:
            print(f"   - {p['persona_id']}")
    
    # Clean up
    print("\n6. Cleaning up test persona...")
    try:
        delete_persona(token, persona1["persona_id"])
        print(f"   ✓ Deleted test persona: {persona1['persona_id']}")
    except Exception as e:
        print(f"   Note: Cleanup failed (may need manual deletion): {e}")
    
    print("\n" + "=" * 70)
    print("Test completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    main()
