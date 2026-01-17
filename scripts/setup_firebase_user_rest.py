#!/usr/bin/env python3
"""
Setup Firebase test user using REST API with gcloud access token.
This avoids the need for application-default credentials.
"""

import json
import subprocess
import sys
import requests

# Test user configuration
TEST_USER_EMAIL = "alice@example.com"
TEST_USER_PASSWORD = "TestPassword123!"
TEST_USER_DISPLAY_NAME = "Alice Test User"
PROJECT_ID = "vision-course-476214"

# Custom claims
CUSTOM_CLAIMS = {
    "persona": "traveler",
    "consent": True,
    "autobook_price": 500,
    "autobook_leadtime": 7,
    "autobook_risklevel": 3,
}


def get_access_token():
    """Get access token from gcloud."""
    try:
        result = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True,
            text=True,
            check=True,
        )
        token = result.stdout.strip()
        print("✓ Got access token from gcloud")
        return token
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to get access token: {e}")
        return None


def create_user_with_password(email, password, display_name, access_token):
    """Create user using Firebase Auth REST API."""
    url = f"https://identitytoolkit.googleapis.com/v1/projects/{PROJECT_ID}/accounts"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "x-goog-user-project": PROJECT_ID,
    }
    
    data = {
        "email": email,
        "password": password,
        "displayName": display_name,
        "emailVerified": True,
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            user_data = response.json()
            uid = user_data.get("localId")
            print(f"✓ Created user: {uid} ({email})")
            return uid
        elif response.status_code == 400 and "EMAIL_EXISTS" in response.text:
            # User already exists, get the UID
            print(f"✓ User already exists: {email}")
            return get_user_by_email(email, access_token)
        else:
            print(f"✗ Failed to create user: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"✗ Exception creating user: {e}")
        return None


def get_user_by_email(email, access_token):
    """Get user UID by email."""
    url = f"https://identitytoolkit.googleapis.com/v1/projects/{PROJECT_ID}/accounts:lookup"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "x-goog-user-project": PROJECT_ID,
    }
    
    data = {"email": [email]}
    
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            users = response.json().get("users", [])
            if users:
                uid = users[0].get("localId")
                print(f"✓ Found user: {uid}")
                return uid
        print(f"✗ User not found: {response.text}")
        return None
    except Exception as e:
        print(f"✗ Exception looking up user: {e}")
        return None


def set_custom_claims(uid, claims, access_token):
    """Set custom claims using Firebase Auth REST API."""
    url = f"https://identitytoolkit.googleapis.com/v1/projects/{PROJECT_ID}/accounts:update"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "x-goog-user-project": PROJECT_ID,
    }
    
    data = {
        "localId": uid,
        "customAttributes": json.dumps(claims),
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            print(f"✓ Set custom claims for user {uid}")
            print(f"  Claims: {claims}")
            return True
        else:
            print(f"✗ Failed to set custom claims: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"✗ Exception setting custom claims: {e}")
        return False


def create_firestore_profile(uid, email, display_name, claims, access_token):
    """Create Firestore document using REST API."""
    doc_path = f"projects/{PROJECT_ID}/databases/(default)/documents/user_profiles/{uid}"
    url = f"https://firestore.googleapis.com/v1/{doc_path}"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "x-goog-user-project": PROJECT_ID,
    }
    
    # Convert Python values to Firestore field format
    fields = {
        "email": {"stringValue": email},
        "display_name": {"stringValue": display_name},
        "persona": {"stringValue": claims.get("persona", "traveler")},
        "consent": {"booleanValue": claims.get("consent", False)},
        "autobook_price": {"integerValue": str(claims.get("autobook_price", 0))},
        "autobook_leadtime": {"integerValue": str(claims.get("autobook_leadtime", 10000))},
        "autobook_risklevel": {"integerValue": str(claims.get("autobook_risklevel", 0))},
    }
    
    data = {"fields": fields}
    
    try:
        # Try to create (PATCH will create or update)
        response = requests.patch(url, headers=headers, json=data)
        if response.status_code in (200, 201):
            print(f"✓ Created Firestore profile for user {uid}")
            profile = {k: list(v.values())[0] for k, v in fields.items()}
            print(f"  Profile: {profile}")
            return True
        else:
            print(f"✗ Failed to create Firestore profile: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"✗ Exception creating Firestore profile: {e}")
        return False


def main():
    print("=" * 60)
    print("FlowPilot Firebase Test User Setup (REST API)")
    print("=" * 60)
    print()
    
    # Get access token
    access_token = get_access_token()
    if not access_token:
        print("\n✗ Setup failed: Could not get access token")
        sys.exit(1)
    
    # Create or get user
    uid = create_user_with_password(TEST_USER_EMAIL, TEST_USER_PASSWORD, TEST_USER_DISPLAY_NAME, access_token)
    if not uid:
        print("\n✗ Setup failed: Could not create user")
        sys.exit(1)
    
    # Set custom claims
    if not set_custom_claims(uid, CUSTOM_CLAIMS, access_token):
        print("\n✗ Setup failed: Could not set custom claims")
        sys.exit(1)
    
    # Create Firestore profile
    if not create_firestore_profile(uid, TEST_USER_EMAIL, TEST_USER_DISPLAY_NAME, CUSTOM_CLAIMS, access_token):
        print("\n✗ Setup failed: Could not create Firestore profile")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✓ Setup complete!")
    print("=" * 60)
    print(f"\nTest user credentials:")
    print(f"  Email: {TEST_USER_EMAIL}")
    print(f"  Password: {TEST_USER_PASSWORD}")
    print(f"  UID: {uid}")
    print(f"\nYou can now use these credentials to sign in via Firebase Auth.")


if __name__ == "__main__":
    main()
