#!/usr/bin/env python3
"""
Get Firebase ID token for testing FlowPilot services.
Uses the Firebase Authentication REST API to sign in and get an ID token.
"""

import subprocess
import sys
import requests

# Test user credentials
TEST_USER_EMAIL = "alice@example.com"
TEST_USER_PASSWORD = "TestPassword123!"
PROJECT_ID = "vision-course-476214"


def get_firebase_api_key():
    """Get Firebase Web API key from project."""
    # For testing, we can get this from the Firebase console
    # or use the Identity Toolkit API
    # For now, return a placeholder - the key should be in Firebase project settings
    
    # Actually, let's try to get it via gcloud
    try:
        result = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True,
            text=True,
            check=True,
        )
        access_token = result.stdout.strip()
        
        # Get Firebase config
        response = requests.get(
            f"https://firebase.googleapis.com/v1beta1/projects/{PROJECT_ID}/webApps",
            headers={
                "Authorization": f"Bearer {access_token}",
                "x-goog-user-project": PROJECT_ID,
            }
        )
        
        if response.status_code == 200:
            apps = response.json().get("apps", [])
            if apps:
                app_id = apps[0].get("appId")
                # Get the config
                config_response = requests.get(
                    f"https://firebase.googleapis.com/v1beta1/projects/{PROJECT_ID}/webApps/{app_id}/config",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "x-goog-user-project": PROJECT_ID,
                    }
                )
                if config_response.status_code == 200:
                    api_key = config_response.json().get("apiKey")
                    if api_key:
                        return api_key
        
        # If we can't get it from the API, try a different method
        # We can use the identitytoolkit API directly without the API key
        # by using custom tokens
        print("Warning: Could not get Firebase API key automatically")
        return None
    except Exception as e:
        print(f"Error getting Firebase API key: {e}")
        return None


def sign_in_with_password(email, password, api_key=None):
    """Sign in with email/password and get ID token."""
    if api_key:
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    else:
        # Try without API key using service account token
        url = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
    
    data = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    
    headers = {"Content-Type": "application/json"}
    
    # If no API key, try with service account token
    if not api_key:
        try:
            result = subprocess.run(
                ["gcloud", "auth", "print-access-token"],
                capture_output=True,
                text=True,
                check=True,
            )
            access_token = result.stdout.strip()
            headers["Authorization"] = f"Bearer {access_token}"
            headers["x-goog-user-project"] = PROJECT_ID
        except Exception as e:
            print(f"Error getting access token: {e}")
            return None
    
    try:
        response = requests.post(url, json=data, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            id_token = result.get("idToken")
            refresh_token = result.get("refreshToken")
            expires_in = result.get("expiresIn")
            
            print(f"✓ Successfully signed in as {email}")
            print(f"\nID Token (expires in {expires_in} seconds):")
            print(id_token)
            print(f"\nRefresh Token:")
            print(refresh_token)
            
            return id_token
        else:
            print(f"✗ Sign in failed: {response.status_code}")
            print(response.text)
            return None
    except Exception as e:
        print(f"✗ Exception during sign in: {e}")
        return None


def main():
    print("=" * 60)
    print("Firebase ID Token Retrieval")
    print("=" * 60)
    print()
    
    # Try to get API key
    api_key = get_firebase_api_key()
    if api_key:
        print(f"✓ Got Firebase API key: {api_key[:10]}...")
    else:
        print("✓ Will try signing in with service account credentials")
    print()
    
    # Sign in and get token
    id_token = sign_in_with_password(TEST_USER_EMAIL, TEST_USER_PASSWORD, api_key)
    
    if id_token:
        print("\n" + "=" * 60)
        print("✓ Token retrieved successfully!")
        print("=" * 60)
        print("\nYou can now use this token to test the FlowPilot services:")
        print(f'  curl -H "Authorization: Bearer {id_token}" https://...')
        return 0
    else:
        print("\n✗ Failed to get ID token")
        return 1


if __name__ == "__main__":
    sys.exit(main())
