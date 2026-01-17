#!/usr/bin/env python3
"""
Setup Firebase test user for FlowPilot.

This script:
1. Initializes Firebase Admin SDK using Application Default Credentials
2. Creates a test user (or uses existing user)
3. Stores user profile in Firestore

Note: Personas are now managed via persona-api, not Firebase custom claims.
"""

import sys
import firebase_admin
from firebase_admin import auth, credentials, firestore

# Test user configuration
TEST_USER_EMAIL = "alice@example.com"
TEST_USER_PASSWORD = "TestPassword123!"
TEST_USER_DISPLAY_NAME = "Alice Test User"

# User profile attributes (stored in Firestore)
PROFILE_ATTRIBUTES = {
    "persona": "traveler",  # Note: Personas should be created via persona-api
    "consent": True,
    "autobook_price": 500,
    "autobook_leadtime": 7,
    "autobook_risklevel": 3,
}


def initialize_firebase():
    """Initialize Firebase Admin SDK with Application Default Credentials."""
    try:
        # Initialize with ADC (works on Cloud Shell and locally with gcloud auth)
        firebase_admin.initialize_app()
        print("✓ Firebase Admin SDK initialized")
        return True
    except ValueError as e:
        if "already exists" in str(e):
            print("✓ Firebase Admin SDK already initialized")
            return True
        print(f"✗ Failed to initialize Firebase: {e}")
        return False


def create_or_get_user(email, password, display_name):
    """Create a new user or get existing user by email."""
    try:
        # Try to get existing user
        user = auth.get_user_by_email(email)
        print(f"✓ Found existing user: {user.uid} ({email})")
        return user
    except auth.UserNotFoundError:
        # User doesn't exist, create new one
        try:
            user = auth.create_user(
                email=email,
                password=password,
                display_name=display_name,
                email_verified=True,  # Skip email verification for testing
            )
            print(f"✓ Created new user: {user.uid} ({email})")
            return user
        except Exception as e:
            print(f"✗ Failed to create user: {e}")
            return None


def create_firestore_profile(uid, email, display_name, attributes):
    """Create user profile document in Firestore.
    
    Note: This only creates a basic profile. Personas should be created via persona-api.
    """
    try:
        db = firestore.client()
        profile_ref = db.collection("user_profiles").document(uid)
        
        profile_data = {
            "email": email,
            "display_name": display_name,
            "persona": attributes.get("persona", "traveler"),
            "consent": attributes.get("consent", False),
            "autobook_price": attributes.get("autobook_price", 0),
            "autobook_leadtime": attributes.get("autobook_leadtime", 10000),
            "autobook_risklevel": attributes.get("autobook_risklevel", 0),
        }
        
        profile_ref.set(profile_data)
        print(f"✓ Created Firestore profile for user {uid}")
        print(f"  Profile: {profile_data}")
        return True
    except Exception as e:
        print(f"✗ Failed to create Firestore profile: {e}")
        return False


def generate_custom_token(uid):
    """Generate a custom token for testing (can be exchanged for ID token)."""
    try:
        custom_token = auth.create_custom_token(uid)
        print(f"\n✓ Generated custom token for user {uid}")
        print(f"  Token: {custom_token.decode('utf-8')}")
        print("\n  To get an ID token, exchange this custom token via:")
        print(f"  curl -X POST 'https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=YOUR_API_KEY' \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"token\":\"{custom_token.decode('utf-8')}\",\"returnSecureToken\":true}}'")
        return custom_token
    except Exception as e:
        print(f"✗ Failed to generate custom token: {e}")
        return None


def main():
    print("=" * 60)
    print("FlowPilot Firebase Test User Setup")
    print("=" * 60)
    print()
    
    # Initialize Firebase
    if not initialize_firebase():
        print("\n✗ Setup failed: Could not initialize Firebase")
        sys.exit(1)
    
    # Create or get user
    user = create_or_get_user(TEST_USER_EMAIL, TEST_USER_PASSWORD, TEST_USER_DISPLAY_NAME)
    if not user:
        print("\n✗ Setup failed: Could not create user")
        sys.exit(1)
    
    # Create Firestore profile
    if not create_firestore_profile(user.uid, user.email, user.display_name, PROFILE_ATTRIBUTES):
        print("\n✗ Setup failed: Could not create Firestore profile")
        sys.exit(1)
    
    # Generate custom token for testing
    generate_custom_token(user.uid)
    
    print("\n" + "=" * 60)
    print("✓ Setup complete!")
    print("=" * 60)
    print(f"\nTest user credentials:")
    print(f"  Email: {TEST_USER_EMAIL}")
    print(f"  Password: {TEST_USER_PASSWORD}")
    print(f"  UID: {user.uid}")
    print(f"\nYou can now use these credentials to sign in via Firebase Auth.")


if __name__ == "__main__":
    main()
