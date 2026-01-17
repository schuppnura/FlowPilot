#!/usr/bin/env python3
"""
Clean up all Firebase Authentication users and Firestore user profiles.

This script deletes all users from Firebase Authentication and their
corresponding Firestore documents. Use this to reset the user database
for reprovisioning.

Usage:
    python3 scripts/cleanup-firebase-users.py

Requirements:
    - Firebase Admin SDK credentials (serviceAccountKey.json or GOOGLE_APPLICATION_CREDENTIALS)
    - firebase-admin package installed
"""

import sys
import os

try:
    import firebase_admin
    from firebase_admin import credentials, firestore, auth
except ImportError:
    print("Error: firebase-admin package not found")
    print("Install it with: pip install firebase-admin")
    sys.exit(1)


def initialize_firebase():
    """Initialize Firebase Admin SDK."""
    try:
        # Try to use existing app if already initialized
        firebase_admin.get_app()
        print("Using existing Firebase app")
    except ValueError:
        # Initialize new app
        # Check for service account key file
        key_paths = [
            os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'),
            'serviceAccountKey.json',
            'firebase-admin-key.json',
        ]
        
        cred = None
        for path in key_paths:
            if path and os.path.exists(path):
                print(f"Using credentials from: {path}")
                cred = credentials.Certificate(path)
                break
        
        if cred:
            firebase_admin.initialize_app(cred)
        else:
            # Try default credentials (works in GCP environments)
            print("Using default credentials")
            firebase_admin.initialize_app()


def delete_firestore_users():
    """Delete all user documents from Firestore."""
    db = firestore.client()
    users_ref = db.collection('users')
    
    print("\n=== Deleting Firestore User Documents ===")
    docs = list(users_ref.stream())
    
    if not docs:
        print("No user documents found in Firestore")
        return 0
    
    count = 0
    for doc in docs:
        print(f"Deleting Firestore document: {doc.id}")
        doc.reference.delete()
        count += 1
    
    print(f"Deleted {count} Firestore user document(s)")
    return count


def delete_auth_users():
    """Delete all users from Firebase Authentication."""
    print("\n=== Deleting Firebase Authentication Users ===")
    
    deleted_count = 0
    error_count = 0
    
    # List all users
    page = auth.list_users()
    while page:
        for user in page.users:
            try:
                print(f"Deleting auth user: {user.uid} ({user.email or 'no email'})")
                auth.delete_user(user.uid)
                deleted_count += 1
            except Exception as e:
                print(f"Error deleting user {user.uid}: {e}")
                error_count += 1
        
        # Get next page
        page = page.get_next_page()
    
    print(f"Deleted {deleted_count} authentication user(s)")
    if error_count > 0:
        print(f"Failed to delete {error_count} user(s)")
    
    return deleted_count


def main():
    """Main function."""
    print("=" * 60)
    print("Firebase User Cleanup Script")
    print("=" * 60)
    
    # Confirm with user
    print("\nWARNING: This will delete ALL users from Firebase Authentication")
    print("         and ALL user documents from Firestore.")
    print("\nThis action CANNOT be undone!")
    
    response = input("\nAre you sure you want to continue? (type 'yes' to confirm): ")
    if response.lower() != 'yes':
        print("Aborted.")
        sys.exit(0)
    
    try:
        # Initialize Firebase
        initialize_firebase()
        
        # Delete Firestore user documents
        firestore_count = delete_firestore_users()
        
        # Delete authentication users
        auth_count = delete_auth_users()
        
        print("\n" + "=" * 60)
        print("Cleanup Complete!")
        print("=" * 60)
        print(f"Total Firestore documents deleted: {firestore_count}")
        print(f"Total authentication users deleted: {auth_count}")
        print("\nYou can now reprovision users.")
        
    except Exception as e:
        print(f"\nError during cleanup: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
