# FlowPilot User Profile API - Persona Database Layer (SQLite)
#
# Database abstraction for persona management.
# Follows the same pattern as delegation-api's graphdb_sqlite.py
#
# Persona schema:
# - persona_id (UUID): Unique identifier
# - user_sub (string): Owner of persona
# - title (string): Persona title (e.g., "traveler", "travel-agent")
# - circle (string): Circle/community/business unit (e.g., "family", "acme-corp")
# - scope (JSON array): Actions (e.g., ["read", "execute"])
# - valid_from (ISO 8601): When persona becomes active
# - valid_till (ISO 8601): When persona expires
# - status (string): "active", "inactive", "suspended", "revoked"
# - created_at (ISO 8601): Creation timestamp
# - updated_at (ISO 8601): Last update timestamp
# - consent (boolean): Auto-booking consent
# - autobook_price (integer): Max auto-booking price
# - autobook_leadtime (integer): Max lead time (days)
# - autobook_risklevel (integer): Risk tolerance (0-100)

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


class PersonaDB:
    """SQLite-based database for persona management."""

    def __init__(self, connection_params: dict[str, Any] | None = None):
        """
        Initialize the database connection.
        
        Args:
            connection_params: Dict with database connection parameters.
                              For SQLite, expected key is 'db_path'.
                              If None, uses environment variable PERSONA_DB_PATH or defaults to './personas.db'
        """
        if connection_params is None:
            connection_params = {}

        # Extract db_path from connection_params or use environment variable / default
        self.db_path = connection_params.get(
            "db_path",
            os.environ.get("PERSONA_DB_PATH", "./personas.db")
        )
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        return conn

    def _init_schema(self) -> None:
        """Initialize the database schema.
        
        Uses composite primary key (persona_id = user_sub_title_circle) to enforce uniqueness.
        """
        conn = self._get_connection()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS personas (
                    persona_id TEXT PRIMARY KEY,
                    user_sub TEXT NOT NULL,
                    title TEXT NOT NULL,
                    circle TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT '["read", "execute"]',
                    valid_from TEXT NOT NULL,
                    valid_till TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    consent INTEGER NOT NULL DEFAULT 0,
                    autobook_price INTEGER NOT NULL DEFAULT 0,
                    autobook_leadtime INTEGER NOT NULL DEFAULT 0,
                    autobook_risklevel INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(user_sub, title, circle)
                )
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_sub ON personas(user_sub)
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_status ON personas(status)
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_title ON personas(title)
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_circle ON personas(circle)
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_valid_from ON personas(valid_from)
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_valid_till ON personas(valid_till)
            """
            )
            conn.commit()
        finally:
            conn.close()

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert a database row to a dictionary."""
        return {
            "persona_id": row["persona_id"],
            "user_sub": row["user_sub"],
            "title": row["title"],
            "circle": row["circle"],
            "scope": json.loads(row["scope"]) if row["scope"] else ["read", "execute"],
            "valid_from": row["valid_from"],
            "valid_till": row["valid_till"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "consent": bool(row["consent"]),
            "autobook_price": row["autobook_price"],
            "autobook_leadtime": row["autobook_leadtime"],
            "autobook_risklevel": row["autobook_risklevel"],
        }

    def create_persona(
        self,
        user_sub: str,
        title: str,
        circle: str,
        scope: list[str] | None = None,
        valid_from: str | None = None,
        valid_till: str | None = None,
        status: str | None = None,
        **custom_attributes: Any,
    ) -> dict[str, Any]:
        """
        Create a new persona.
        
        Uses composite persona ID (user_sub + title + circle) to enforce uniqueness at database level.
        Raises ValueError if a persona with the same title and circle already exists for this user.
        
        Args:
            user_sub: User subject ID (owner)
            title: Persona title (e.g., "traveler")
            circle: Circle/community/business unit (e.g., "family", "acme-corp")
            scope: List of actions (defaults to ["read", "execute"])
            valid_from: When persona becomes active (ISO 8601, defaults to now)
            valid_till: When persona expires (ISO 8601, defaults to 365 days from now)
            status: Status (active, inactive, suspended, revoked). Defaults to "active" if not provided.
            **custom_attributes: Dynamic policy-specific attributes (e.g., consent, autobook_price, etc.)
            
        Returns:
            Dictionary with created persona (or existing persona if already exists)
        """
        # Generate composite persona ID from user_sub, title, and circle
        # This enforces uniqueness: each user can have multiple personas per title but unique per (title, circle)
        persona_id = f"{user_sub}_{title}_{circle}"
        now = datetime.now(timezone.utc).isoformat()

        if scope is None:
            scope = ["read", "execute"]
        scope_json = json.dumps(scope)

        if valid_from is None:
            valid_from = now

        if valid_till is None:
            # Default to 365 days from now
            valid_till = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
            
        if status is None:
            status = "active"

        conn = self._get_connection()
        try:
            # Check if persona already exists
            cursor = conn.execute(
                "SELECT * FROM personas WHERE persona_id = ?", (persona_id,)
            )
            existing_row = cursor.fetchone()
            if existing_row:
                # Persona already exists - raise error suggesting PATCH
                raise ValueError(
                    f"Persona with title '{title}' and circle '{circle}' already exists for this user. "
                    f"Use PATCH/PUT (update) instead of POST (create) to modify it. "
                    f"Existing persona_id: {persona_id}"
                )
            
            # Extract dynamic attributes with defaults
            consent = custom_attributes.get("consent", False)
            autobook_price = custom_attributes.get("autobook_price", 0)
            autobook_leadtime = custom_attributes.get("autobook_leadtime", 0)
            autobook_risklevel = custom_attributes.get("autobook_risklevel", 0)
            
            conn.execute(
                """
                INSERT INTO personas (
                    persona_id, user_sub, title, circle, scope, valid_from, valid_till,
                    status, created_at, updated_at, consent, autobook_price,
                    autobook_leadtime, autobook_risklevel
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    persona_id,
                    user_sub,
                    title,
                    circle,
                    scope_json,
                    valid_from,
                    valid_till,
                    status,
                    now,
                    now,
                    int(consent),
                    autobook_price,
                    autobook_leadtime,
                    autobook_risklevel,
                ),
            )
            conn.commit()

            # Fetch and return created persona
            cursor = conn.execute(
                "SELECT * FROM personas WHERE persona_id = ?", (persona_id,)
            )
            row = cursor.fetchone()
            return self._row_to_dict(row)
        finally:
            conn.close()

    def get_persona(self, persona_id: str) -> dict[str, Any] | None:
        """
        Get a persona by ID.
        
        Args:
            persona_id: Persona ID
            
        Returns:
            Persona dictionary or None if not found
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM personas WHERE persona_id = ?", (persona_id,)
            )
            row = cursor.fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    def list_personas(
        self,
        user_sub: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List personas for a user.
        
        Args:
            user_sub: User subject ID
            status: Optional status filter ("active", "inactive", "suspended", "revoked")
            
        Returns:
            List of persona dictionaries
        """
        conn = self._get_connection()
        try:
            if status:
                cursor = conn.execute(
                    "SELECT * FROM personas WHERE user_sub = ? AND status = ? ORDER BY created_at DESC",
                    (user_sub, status),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM personas WHERE user_sub = ? ORDER BY created_at DESC",
                    (user_sub,),
                )

            rows = cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]
        finally:
            conn.close()

    def update_persona(
        self,
        persona_id: str,
        title: str | None = None,
        circle: str | None = None,
        scope: list[str] | None = None,
        valid_from: str | None = None,
        valid_till: str | None = None,
        status: str | None = None,
        consent: bool | None = None,
        autobook_price: int | None = None,
        autobook_leadtime: int | None = None,
        autobook_risklevel: int | None = None,
    ) -> dict[str, Any] | None:
        """
        Update a persona (partial update).
        
        Args:
            persona_id: Persona ID
            title: Optional new title
            circle: Optional new circle
            scope: Optional new scope
            valid_from: Optional new valid_from
            valid_till: Optional new valid_till
            status: Optional new status
            consent: Optional new consent
            autobook_price: Optional new price
            autobook_leadtime: Optional new leadtime
            autobook_risklevel: Optional new risklevel
            
        Returns:
            Updated persona dictionary or None if not found
        """
        conn = self._get_connection()
        try:
            # Check if persona exists
            cursor = conn.execute(
                "SELECT * FROM personas WHERE persona_id = ?", (persona_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            # Build update query dynamically
            updates = []
            params = []

            if title is not None:
                updates.append("title = ?")
                params.append(title)
            if circle is not None:
                updates.append("circle = ?")
                params.append(circle)
            if scope is not None:
                updates.append("scope = ?")
                params.append(json.dumps(scope))
            if valid_from is not None:
                updates.append("valid_from = ?")
                params.append(valid_from)
            if valid_till is not None:
                updates.append("valid_till = ?")
                params.append(valid_till)
            if status is not None:
                updates.append("status = ?")
                params.append(status)
            if consent is not None:
                updates.append("consent = ?")
                params.append(int(consent))
            if autobook_price is not None:
                updates.append("autobook_price = ?")
                params.append(autobook_price)
            if autobook_leadtime is not None:
                updates.append("autobook_leadtime = ?")
                params.append(autobook_leadtime)
            if autobook_risklevel is not None:
                updates.append("autobook_risklevel = ?")
                params.append(autobook_risklevel)

            # Always update updated_at
            now = datetime.now(timezone.utc).isoformat()
            updates.append("updated_at = ?")
            params.append(now)

            params.append(persona_id)

            if updates:
                query = f"UPDATE personas SET {', '.join(updates)} WHERE persona_id = ?"
                conn.execute(query, params)
                conn.commit()

            # Fetch and return updated persona
            cursor = conn.execute(
                "SELECT * FROM personas WHERE persona_id = ?", (persona_id,)
            )
            row = cursor.fetchone()
            return self._row_to_dict(row)
        finally:
            conn.close()

    def delete_persona(self, persona_id: str) -> bool:
        """
        Delete a persona.
        
        Args:
            persona_id: Persona ID
            
        Returns:
            True if deleted, False if not found
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM personas WHERE persona_id = ?", (persona_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def list_personas_by_title(
        self,
        title: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List all personas with a given title.
        
        Args:
            title: Persona title to filter by
            status: Optional status filter ("active", "inactive", "suspended", "revoked")
            
        Returns:
            List of persona dictionaries
        """
        conn = self._get_connection()
        try:
            if status:
                cursor = conn.execute(
                    "SELECT * FROM personas WHERE title = ? AND status = ? ORDER BY created_at DESC",
                    (title, status),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM personas WHERE title = ? ORDER BY created_at DESC",
                    (title,),
                )

            rows = cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]
        finally:
            conn.close()

    def get_active_persona(self, user_sub: str) -> dict[str, Any] | None:
        """
        Get the first active persona for a user (most recently created).
        
        Args:
            user_sub: User subject ID
            
        Returns:
            Active persona dictionary or None if not found
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM personas 
                WHERE user_sub = ? AND status = 'active'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_sub,),
            )
            row = cursor.fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()
