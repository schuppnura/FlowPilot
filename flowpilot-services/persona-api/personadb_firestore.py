# FlowPilot User Profile API - Persona Database Layer (Firestore)
#
# Database abstraction for persona management using Firestore (GCP).
# Follows the same interface as personadb_sqlite.py
#
# Firestore collection: personas
# Document structure matches the SQLite schema

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import firebase_admin
from firebase_admin import firestore

# ============================================================================
# Firestore Initialization
# ============================================================================

_firestore_client: firestore.Client | None = None


def _get_firestore_client() -> firestore.Client:
    """Get Firestore client instance."""
    global _firestore_client

    if _firestore_client is None:
        # Initialize if not already done
        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app()

        _firestore_client = firestore.client()

    return _firestore_client


class PersonaDB:
    """Firestore-based database for persona management."""

    def __init__(self, connection_params: dict[str, Any] | None = None):
        """
        Initialize the Firestore client.
        
        Args:
            connection_params: Not used for Firestore (Firebase SDK handles configuration)
        """
        # Initialize Firestore client
        self.db = _get_firestore_client()
        self.collection_name = "personas"

    def _doc_to_dict(self, doc) -> dict[str, Any]:
        """Convert a Firestore document to a dictionary."""
        if not doc.exists:
            return None

        data = doc.to_dict()
        # Ensure persona_id is set (from document ID)
        data["persona_id"] = doc.id
        return data

    def create_persona(
        self,
        user_sub: str,
        title: str,
        scope: list[str] | None = None,
        valid_from: str | None = None,
        valid_till: str | None = None,
        status: str | None = None,
        **custom_attributes: Any,
    ) -> dict[str, Any]:
        """
        Create a new persona.
        
        Uses composite document ID (user_sub + title) to enforce uniqueness at database level.
        Raises ValueError if a persona with the same title already exists for this user.
        
        Args:
            user_sub: User subject ID (owner)
            title: Persona title (e.g., "traveler")
            scope: List of actions (defaults to ["read", "execute"])
            valid_from: When persona becomes active (ISO 8601, defaults to now)
            valid_till: When persona expires (ISO 8601, defaults to 365 days from now)
            status: Status (active, inactive, suspended, expired). Defaults to "active" if not provided.
            **custom_attributes: Dynamic policy-specific attributes (e.g., consent, autobook_price, etc.)
            
        Returns:
            Dictionary with created persona (or existing persona if already exists)
        """
        # Generate composite document ID from user_sub and title
        # This enforces uniqueness: each user can only have one persona per title
        persona_id = f"{user_sub}_{title}"
        now = datetime.now(timezone.utc).isoformat()

        if scope is None:
            scope = ["read", "execute"]

        if valid_from is None:
            valid_from = now

        if valid_till is None:
            # Default to 365 days from now
            valid_till = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()

        if status is None:
            status = "active"

        # Check if persona already exists
        doc_ref = self.db.collection(self.collection_name).document(persona_id)
        existing_doc = doc_ref.get()
        
        if existing_doc.exists:
            # Persona already exists - raise error suggesting PATCH
            existing_data = self._doc_to_dict(existing_doc)
            raise ValueError(
                f"Persona with title '{title}' already exists for this user. "
                f"Use PATCH/PUT (update) instead of POST (create) to modify it. "
                f"Existing persona_id: {persona_id}"
            )

        # Build base persona data with standard fields
        persona_data = {
            "user_sub": user_sub,
            "title": title,
            "scope": scope,
            "valid_from": valid_from,
            "valid_till": valid_till,
            "status": status,
            "created_at": now,
            "updated_at": now,
        }
        
        # Add all custom attributes dynamically
        persona_data.update(custom_attributes)

        # Create document with composite ID
        doc_ref.set(persona_data)

        # Return created persona with ID
        persona_data["persona_id"] = persona_id
        return persona_data

    def get_persona(self, persona_id: str) -> dict[str, Any] | None:
        """
        Get a persona by ID.
        
        Args:
            persona_id: Persona ID
            
        Returns:
            Persona dictionary or None if not found
        """
        doc_ref = self.db.collection(self.collection_name).document(persona_id)
        doc = doc_ref.get()
        return self._doc_to_dict(doc)

    def list_personas(
        self,
        user_sub: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List personas for a user.
        
        Args:
            user_sub: User subject ID
            status: Optional status filter ("active", "inactive", "suspended", "expired")
            
        Returns:
            List of persona dictionaries
        """
        query = self.db.collection(self.collection_name).where("user_sub", "==", user_sub)

        if status:
            query = query.where("status", "==", status)

        # Order by created_at descending
        query = query.order_by("created_at", direction=firestore.Query.DESCENDING)

        docs = query.stream()
        return [self._doc_to_dict(doc) for doc in docs]

    def update_persona(
        self,
        persona_id: str,
        title: str | None = None,
        scope: list[str] | None = None,
        valid_from: str | None = None,
        valid_till: str | None = None,
        status: str | None = None,
        **custom_attributes: Any,
    ) -> dict[str, Any] | None:
        """
        Update a persona (partial update).
        
        Args:
            persona_id: Persona ID
            title: Optional new title
            scope: Optional new scope
            valid_from: Optional new valid_from
            valid_till: Optional new valid_till
            status: Optional new status
            **custom_attributes: Dynamic policy-specific attributes to update (e.g., consent, autobook_price, etc.)
            
        Returns:
            Updated persona dictionary or None if not found
        """
        doc_ref = self.db.collection(self.collection_name).document(persona_id)
        doc = doc_ref.get()

        if not doc.exists:
            return None

        # Build update dict with standard fields
        updates = {}

        if title is not None:
            updates["title"] = title
        if scope is not None:
            updates["scope"] = scope
        if valid_from is not None:
            updates["valid_from"] = valid_from
        if valid_till is not None:
            updates["valid_till"] = valid_till
        if status is not None:
            updates["status"] = status
        
        # Add all custom attributes dynamically (only non-None values)
        for key, value in custom_attributes.items():
            if value is not None:
                updates[key] = value

        # Always update updated_at
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()

        if updates:
            doc_ref.update(updates)

        # Fetch and return updated persona
        doc = doc_ref.get()
        return self._doc_to_dict(doc)

    def delete_persona(self, persona_id: str) -> bool:
        """
        Delete a persona.
        
        Args:
            persona_id: Persona ID
            
        Returns:
            True if deleted, False if not found
        """
        doc_ref = self.db.collection(self.collection_name).document(persona_id)
        doc = doc_ref.get()

        if not doc.exists:
            return False

        doc_ref.delete()
        return True

    def list_personas_by_title(
        self,
        title: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List all personas with a given title.
        
        Args:
            title: Persona title to filter by
            status: Optional status filter ("active", "inactive", "suspended", "expired")
            
        Returns:
            List of persona dictionaries (unordered to avoid composite index requirement)
        """
        query = self.db.collection(self.collection_name).where("title", "==", title)

        if status:
            query = query.where("status", "==", status)

        # Note: Removed order_by to avoid requiring composite index (title + status + created_at)
        # Ordering is not critical for listing users by persona

        docs = query.stream()
        return [self._doc_to_dict(doc) for doc in docs]

    def get_active_persona(self, user_sub: str) -> dict[str, Any] | None:
        """
        Get the first active persona for a user (most recently created).
        
        Args:
            user_sub: User subject ID
            
        Returns:
            Active persona dictionary or None if not found
        """
        query = (
            self.db.collection(self.collection_name)
            .where("user_sub", "==", user_sub)
            .where("status", "==", "active")
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .limit(1)
        )

        docs = query.stream()
        for doc in docs:
            return self._doc_to_dict(doc)

        return None
