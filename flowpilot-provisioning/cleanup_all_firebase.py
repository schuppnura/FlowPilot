#!/usr/bin/env python3
"""
Complete Firebase cleanup script.
Deletes all users from Firebase Authentication AND all personas from Firestore/Database.

WARNING: This will permanently delete all user data and cannot be undone!
"""

import os
import sys

import firebase_admin
from firebase_admin import auth

try:
    from firebase_admin import firestore
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False
    print("Note: Firestore not available (this is OK for Keycloak deployments)")

import requests


def delete_all_auth_users():
    """Delete all users from Firebase Authentication."""
    deleted_count = 0
    error_count = 0
    
    print("=" * 70)
    print("Step 1: Deleting Firebase Authentication users...")
    print("=" * 70)
    
    # List all users
    page = auth.list_users()
    
    while page:
        for user in page.users:
            try:
                print(f"  Deleting user: {user.email} (uid={user.uid})")
                auth.delete_user(user.uid)
                deleted_count += 1
            except Exception as e:
                print(f"    ERROR: Failed to delete {user.email}: {e}")
                error_count += 1
        
        # Get next page
        page = page.get_next_page()
    
    print(f"\n✓ Deleted {deleted_count} users from Firebase Authentication")
    if error_count > 0:
        print(f"✗ Failed to delete {error_count} users")
    
    return deleted_count, error_count


def delete_all_firestore_personas():
    """Delete all personas from Firestore (for Firebase deployments)."""
    if not FIRESTORE_AVAILABLE:
        print("\nFirestore not available - skipping persona cleanup")
        return 0
    
    print()
    print("=" * 70)
    print("Step 2: Deleting Firestore personas...")
    print("=" * 70)
    
    db = firestore.client()
    personas_ref = db.collection("personas")
    
    # Get all personas
    personas = personas_ref.stream()
    
    count = 0
    for persona in personas:
        print(f"  Deleting persona: {persona.id}")
        persona.reference.delete()
        count += 1
    
    print(f"\n✓ Deleted {count} personas from Firestore")
    return count


def delete_all_personas_via_api(profile_api_url: str, firebase_api_key: str):
    """
    Delete all personas via persona-api (works for both Firebase and Keycloak).
    This requires authenticating as each user.
    """
    print()
    print("=" * 70)
    print("Step 3: Deleting personas via API...")
    print("=" * 70)
    print("(Skipped - users were deleted, so personas are orphaned and can be cleaned up separately)")
    print()


def main():
    # Initialize Firebase Admin SDK using service account credentials
    try:
        firebase_admin.get_app()
    except ValueError:
        # Look for service account key in multiple locations
        service_account_paths = [
            "flowpilot-testing/firebase-admin-key.json",
            "../flowpilot-testing/firebase-admin-key.json",
            "firebase-admin-key.json",
        ]
        
        cred = None
        for path in service_account_paths:
            if os.path.exists(path):
                print(f"Using service account key: {path}")
                from firebase_admin import credentials
                cred = credentials.Certificate(path)
                break
        
        if cred:
            firebase_admin.initialize_app(cred)
        else:
            # Fall back to Application Default Credentials
            print("Warning: No service account key found, using Application Default Credentials")
            firebase_admin.initialize_app()
    
    print("=" * 70)
    print("Firebase Complete Cleanup")
    print("=" * 70)
    print()
    print("WARNING: This will PERMANENTLY DELETE:")
    print("  - All users from Firebase Authentication")
    print("  - All personas from Firestore/Database")
    print()
    print("This action CANNOT be undone!")
    print()
    
    # Confirm deletion
    response = input("Delete ALL Firebase data? (type 'y' to confirm): ")
    if response != "y":
        print("Aborted.")
        sys.exit(0)
    print()
    
    # Step 1: Delete Firebase Auth users
    auth_deleted, auth_errors = delete_all_auth_users()
    
    # Step 2: Delete Firestore personas (if available)
    firestore_deleted = delete_all_firestore_personas()
    
    # Summary
    print()
    print("=" * 70)
    print("Cleanup Complete")
    print("=" * 70)
    print(f"Auth users deleted:       {auth_deleted}")
    print(f"Auth deletion errors:     {auth_errors}")
    print(f"Firestore personas deleted: {firestore_deleted}")
    print("=" * 70)
    print()
    print("✓ You can now run seed_firebase_users.py to start with a clean slate")


if __name__ == "__main__":
    main()
