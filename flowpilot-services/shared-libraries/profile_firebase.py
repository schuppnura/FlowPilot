# flowpilot-services/shared-libraries/profile_firebase.py
#
# Profile module for accessing Firebase/Firestore user profile data.
#
# This module replaces Keycloak-based profile access with Firebase Auth + Firestore.
# User attributes (persona, autobook settings) are stored in Firestore.

from __future__ import annotations

from typing import Any, Dict, List, Optional

import firebase_admin
from firebase_admin import auth, firestore

# ============================================================================
# Firebase Initialization
# ============================================================================

_firestore_client: firestore.Client | None = None


def _get_firestore_client() -> firestore.Client:
    # Get Firestore client instance
    global _firestore_client

    if _firestore_client is None:
        # Initialize if not already done
        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app()

        _firestore_client = firestore.client()

    return _firestore_client


# ============================================================================
# User Profile Functions
# ============================================================================

def fetch_username(user_sub: str) -> str | None:
    # Fetch username for a user by their sub (uid in Firebase).
    #
    # Args:
        #     user_sub: User subject ID (Firebase UID)
    #
    # Returns:
    #     Username string (email), or None if user not found
    try:
        user = auth.get_user(user_sub)
        # Firebase doesn't have a separate username, use email or displayName
        return user.email or user.display_name or user_sub
    except auth.UserNotFoundError:
        return None
    except Exception as e:
        raise RuntimeError(f"Failed to fetch username for user {user_sub}: {e}") from e


def fetch_persona(user_sub: str) -> list[str]:
    # Fetch persona(s) for a user by their sub (uid in Firebase).
    #
    # Note: Personas are now managed via user-profile-api and stored in the database.
    # This function is kept for backward compatibility but should not be used.
    #
    # Args:
    #     user_sub: User subject ID (Firebase UID)
    #
    # Returns:
    #     List of persona strings (e.g., ["traveler", "travel-agent"]), empty list if none
    try:
        db = _get_firestore_client()
        user_doc = db.collection("user_profiles").document(user_sub).get()

        if user_doc.exists:
            data = user_doc.to_dict()
            persona = data.get("persona", [])
            if isinstance(persona, list):
                return persona
            elif isinstance(persona, str):
                return [persona]

        # Default persona
        return ["traveler"]

    except auth.UserNotFoundError:
        return []
    except Exception as e:
        raise RuntimeError(f"Failed to fetch persona for user {user_sub}: {e}") from e


def fetch_attributes(user_sub: str) -> dict[str, Any]:
    # Fetch user attributes from Firestore including personas and autobook settings.
    #
    # Args:
    #     user_sub: User subject ID (Firebase UID)
    #
    # Returns:
    #     Dictionary with user attributes:
    #     - persona: List[str] - List of persona strings
    #     - consent: string (e.g., "Yes", "No")
    #     - autobook_price: string (e.g., "1500")
    #     - autobook_leadtime: string (e.g., "7")
    #     - autobook_risklevel: string (e.g., "2")
    #     Returns empty dict if user not found
    try:
        db = _get_firestore_client()
        user_doc = db.collection("user_profiles").document(user_sub).get()

        if not user_doc.exists:
            return {}

        data = user_doc.to_dict()

        # Extract persona (ensure it's a list)
        persona = data.get("persona", ["traveler"])
        if isinstance(persona, str):
            persona = [persona]
        elif not isinstance(persona, list):
            persona = ["traveler"]

        return {
            "persona": persona,
            "consent": data.get("consent", ""),
            "autobook_price": data.get("autobook_price", ""),
            "autobook_leadtime": data.get("autobook_leadtime", ""),
            "autobook_risklevel": data.get("autobook_risklevel", ""),
        }

    except Exception as e:
        raise RuntimeError(f"Failed to fetch attributes for user {user_sub}: {e}") from e


def list_all_users() -> list[dict[str, Any]]:
    # List all users from Firebase Auth.
    #
    # Returns:
    #     List of user dictionaries with:
    #     - id: User sub (Firebase UID)
    #     - username: Username (derived from email, display name, or uid)
    #     - email: Email address (optional, may be empty string)
    try:
        users_list: list[dict[str, Any]] = []
        
        # Iterate through all users in Firebase Auth
        page = auth.list_users()
        while page:
            for user in page.users:
                # Prioritize display name over email for username (less PII exposure)
                email = user.email or ""
                username = user.display_name or email or user.uid
                
                # Include all users, not just those with email
                users_list.append({
                    "id": user.uid,
                    "username": username,
                    "email": email,
                })
            
            # Get next page
            page = page.get_next_page()
        
        return users_list
    
    except Exception as e:
        raise RuntimeError(f"Failed to list all users: {e}") from e


def list_users_by_persona(persona: str) -> list[dict[str, Any]]:
    # List all users who have a specific persona.
    #
    # Args:
    #     persona: Persona value to filter by (e.g., "travel-agent")
    #
    # Returns:
    #     List of user dictionaries with:
    #     - id: User sub (Firebase UID)
    #     - username: Username (email)
    #     - email: Email
    try:
        db = _get_firestore_client()

        # Query Firestore for users with matching persona
        users_ref = db.collection("user_profiles")
        query = users_ref.where("personas", "array_contains", persona)

        matching_users: list[dict[str, Any]] = []

        for doc in query.stream():
            user_id = doc.id

            # Get email from Firebase Auth
            try:
                user = auth.get_user(user_id)
                email = user.email or ""
                username = email or user.display_name or user_id
            except Exception:
                email = ""
                username = user_id

            matching_users.append({
                "id": user_id,
                "username": username,
                "email": email,
            })

        return matching_users

    except Exception as e:
        raise RuntimeError(f"Failed to list users by persona '{persona}': {e}") from e


# ============================================================================
# Helper Functions for User Management
# ============================================================================

def set_user_attributes(user_sub: str, attributes: dict[str, Any]) -> bool:
    # Set user attributes in Firestore.
    #
    # Args:
    #     user_sub: User subject ID (Firebase UID)
    #     attributes: Dictionary of attributes to set
    #
    # Returns:
    #     True if successful, False otherwise
    try:
        db = _get_firestore_client()
        user_ref = db.collection("user_profiles").document(user_sub)
        user_ref.set(attributes, merge=True)
        return True
    except Exception as e:
        raise RuntimeError(f"Failed to set attributes for user {user_sub}: {e}") from e
