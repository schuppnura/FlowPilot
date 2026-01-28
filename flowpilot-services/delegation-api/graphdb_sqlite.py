# FlowPilot Delegation API - Graph Database Handlers
#
# Pure database handlers for delegation graph operations.
# Currently SQL-based, structured to be easily replaceable with a graph database like CogDB.
#
# Graph structure:
# - Nodes: principal_id (user or agent)
# - Edges: delegation relationships with metadata (workflow_id, expires_at, created_at)
# - Edge type: "delegates" (principal_id -> delegate_id)

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class DelegationGraphDB:
    # SQL-based graph database for delegation relationships.

    def __init__(self, connection_params: dict[str, Any] | None = None):
        # Initialize the database connection.
        # Args:
        #     connection_params: Dict with database connection parameters.
        #                       For SQLite, expected key is 'db_path'.
        #                       If None, uses environment variable DB_PATH or defaults to './delegations.db'
        if connection_params is None:
            connection_params = {}

        # Extract db_path from connection_params or use environment variable / default
        self.db_path = connection_params.get(
            "db_path",
            os.environ.get("DB_PATH", "./delegations.db")
        )
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        # Get a database connection.
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        return conn

    def _init_schema(self) -> None:
        # Initialize the database schema.
        conn = self._get_connection()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS delegations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    principal_id TEXT NOT NULL,
                    delegate_id TEXT NOT NULL,
                    workflow_id TEXT,
                    scope TEXT NOT NULL DEFAULT '["execute"]',
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    revoked_at TEXT,
                    UNIQUE(principal_id, delegate_id, workflow_id, scope)
                )
            """
            )
            # Migration: Add scope column if it doesn't exist (for existing databases)
            try:
                conn.execute(
                    "ALTER TABLE delegations ADD COLUMN scope TEXT NOT NULL DEFAULT '[\"execute\"]'"
                )
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_principal_id ON delegations(principal_id)
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_delegate_id ON delegations(delegate_id)
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_workflow_id ON delegations(workflow_id)
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_expires_at ON delegations(expires_at)
            """
            )
            conn.commit()
        finally:
            conn.close()

    def insert_edge(
        self,
        principal_id: str,
        delegate_id: str,
        expires_at: str,
        workflow_id: str | None = None,
        scope: list[str] | None = None,
    ) -> dict[str, Any]:
        # Insert a delegation edge.
        # Raises ValueError if delegation already exists (must revoke first to modify).
        # Args:
        #     principal_id: ID of the principal delegating authority
        #     delegate_id: ID of the delegate receiving authority
        #     expires_at: ISO 8601 timestamp when delegation expires
        #     workflow_id: Optional workflow ID to scope the delegation
        #     scope: List of actions (e.g. ["read"] or ["read", "execute"]). Defaults to ["execute"]
        # Returns:
        #     Dictionary with delegation details including created_at
        if scope is None:
            scope = ["execute"]
        scope_json = json.dumps(scope)

        conn = self._get_connection()
        try:
            # Check if delegation already exists (same principal, delegate, workflow, AND scope)
            cursor = conn.execute(
                """
                SELECT * FROM delegations
                WHERE principal_id = ? AND delegate_id = ? 
                AND (workflow_id = ? OR (workflow_id IS NULL AND ? IS NULL))
                AND scope = ?
                AND revoked_at IS NULL
            """,
                (principal_id, delegate_id, workflow_id, workflow_id, scope_json),
            )
            existing_row = cursor.fetchone()

            if existing_row:
                # Delegation already exists - raise error suggesting update via separate endpoint
                existing_scope_json = existing_row["scope"]
                try:
                    existing_scope = (
                        json.loads(existing_scope_json)
                        if existing_scope_json
                        else ["execute"]
                    )
                except (json.JSONDecodeError, TypeError):
                    existing_scope = ["execute"]
                
                workflow_desc = f"workflow '{workflow_id}'" if workflow_id else "all workflows (unscoped)"
                raise ValueError(
                    f"Delegation from '{principal_id}' to '{delegate_id}' for {workflow_desc} already exists "
                    f"(scope: {existing_scope}, expires: {existing_row['expires_at']}). "
                    f"To modify the delegation, first revoke it using DELETE /v1/delegations, then create a new one. "
                    f"Or consider if the existing delegation already meets your needs."
                )
            else:
                # Insert new delegation
                created_at = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    """
                    INSERT INTO delegations 
                    (principal_id, delegate_id, workflow_id, scope, expires_at, created_at, revoked_at)
                    VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                    (
                        principal_id,
                        delegate_id,
                        workflow_id,
                        scope_json,
                        expires_at,
                        created_at,
                    ),
                )
                conn.commit()

                # Fetch the inserted row
                cursor = conn.execute(
                    """
                    SELECT * FROM delegations
                    WHERE principal_id = ? AND delegate_id = ? 
                    AND (workflow_id = ? OR (workflow_id IS NULL AND ? IS NULL))
                """,
                    (principal_id, delegate_id, workflow_id, workflow_id),
                )
                row = cursor.fetchone()

            if not row:
                raise RuntimeError("Failed to retrieve delegation")

            scope_value = row["scope"]
            try:
                scope_parsed = json.loads(scope_value) if scope_value else ["execute"]
            except (json.JSONDecodeError, TypeError):
                scope_parsed = ["execute"]

            return {
                "principal_id": row["principal_id"],
                "delegate_id": row["delegate_id"],
                "workflow_id": row["workflow_id"],
                "scope": scope_parsed,
                "expires_at": row["expires_at"],
                "created_at": row["created_at"],
                "revoked_at": row["revoked_at"],
            }
        finally:
            conn.close()

    def revoke_edge(
        self,
        principal_id: str,
        delegate_id: str,
        workflow_id: str | None = None,
    ) -> bool:
        # Revoke a delegation edge.
        # Args:
        #     principal_id: ID of the principal
        #     delegate_id: ID of the delegate
        #     workflow_id: Optional workflow ID to scope the revocation
        # Returns:
        #     True if a delegation was revoked, False otherwise
        revoked_at = datetime.now(timezone.utc).isoformat()

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                UPDATE delegations
                SET revoked_at = ?
                WHERE principal_id = ? AND delegate_id = ? 
                AND (workflow_id = ? OR (workflow_id IS NULL AND ? IS NULL))
                AND revoked_at IS NULL
            """,
                (revoked_at, principal_id, delegate_id, workflow_id, workflow_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def list_outgoing_edges(
        self,
        principal_id: str,
        workflow_id: str | None = None,
        include_expired: bool = False,
    ) -> list[dict[str, Any]]:
        # List all delegations from a principal.
        # Args:
        #     principal_id: ID of the principal
        #     workflow_id: Optional workflow ID to filter by
        #     include_expired: If True, include expired delegations
        # Returns:
        #     List of delegation dictionaries
        now = datetime.now(timezone.utc).isoformat()

        conn = self._get_connection()
        try:
            query = """
                SELECT * FROM delegations
                WHERE principal_id = ? AND revoked_at IS NULL
            """
            params: list[Any] = [principal_id]

            if workflow_id is not None:
                query += " AND (workflow_id = ? OR workflow_id IS NULL)"
                params.append(workflow_id)

            if not include_expired:
                query += " AND expires_at > ?"
                params.append(now)

            query += " ORDER BY created_at DESC"

            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            import json

            result = []
            for row in rows:
                scope_value = row["scope"]
                try:
                    scope_parsed = (
                        json.loads(scope_value) if scope_value else ["execute"]
                    )
                except (json.JSONDecodeError, TypeError):
                    scope_parsed = ["execute"]

                result.append(
                    {
                        "principal_id": row["principal_id"],
                        "delegate_id": row["delegate_id"],
                        "workflow_id": row["workflow_id"],
                        "scope": scope_parsed,
                        "expires_at": row["expires_at"],
                        "created_at": row["created_at"],
                        "revoked_at": row["revoked_at"],
                    }
                )

            return result
        finally:
            conn.close()

    def list_incoming_edges(
        self,
        delegate_id: str,
        workflow_id: str | None = None,
        include_expired: bool = False,
    ) -> list[dict[str, Any]]:
        # List all delegations to a delegate.
        # Args:
        #     delegate_id: ID of the delegate
        #     workflow_id: Optional workflow ID to filter by
        #     include_expired: If True, include expired delegations
        # Returns:
        #     List of delegation dictionaries
        now = datetime.now(timezone.utc).isoformat()

        conn = self._get_connection()
        try:
            query = """
                SELECT * FROM delegations
                WHERE delegate_id = ? AND revoked_at IS NULL
            """
            params: list[Any] = [delegate_id]

            if workflow_id is not None:
                query += " AND (workflow_id = ? OR workflow_id IS NULL)"
                params.append(workflow_id)

            if not include_expired:
                query += " AND expires_at > ?"
                params.append(now)

            query += " ORDER BY created_at DESC"

            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            result = []
            for row in rows:
                scope_value = row["scope"]
                try:
                    scope_parsed = (
                        json.loads(scope_value) if scope_value else ["execute"]
                    )
                except (json.JSONDecodeError, TypeError):
                    scope_parsed = ["execute"]

                result.append(
                    {
                        "principal_id": row["principal_id"],
                        "delegate_id": row["delegate_id"],
                        "workflow_id": row["workflow_id"],
                        "scope": scope_parsed,
                        "expires_at": row["expires_at"],
                        "created_at": row["created_at"],
                        "revoked_at": row["revoked_at"],
                    }
                )

            return result
        finally:
            conn.close()

    def find_delegation_path(
        self,
        principal_id: str,
        delegate_id: str,
        workflow_id: str | None = None,
        max_depth: int = 5,
    ) -> dict[str, Any] | None:
        # Find a delegation path from principal to delegate using BFS with action type computation.
        # Args:
        #     principal_id: Starting principal ID
        #     delegate_id: Target delegate ID
        #     workflow_id: Optional workflow ID to scope the search
        #     max_depth: Maximum depth to search (prevent infinite loops)
        # Returns:
        #     Dictionary with:
        #       - path: List of IDs from principal to delegate
        #       - delegated_actions: List of actions available through this path
        #         If any edge is read-only, the whole path is read-only
        #         If all edges have execute, the path has execute
        #     Returns None if no path found
        if principal_id == delegate_id:
            return {"path": [principal_id], "delegated_actions": ["read", "execute"]}

        now = datetime.now(timezone.utc).isoformat()

        conn = self._get_connection()
        try:
            # BFS search with action tracking
            # Queue items: (current_id, path, delegated_actions)
            # delegated_actions starts as all actions and gets restricted as we traverse
            queue: list[tuple[str, list[str], set[str]]] = [
                (principal_id, [principal_id], {"read", "execute"})
            ]
            visited: set[str] = {principal_id}

            # Track all valid paths to choose the one with strongest permissions
            valid_paths: list[dict[str, Any]] = []

            while queue and len(queue[0][1]) <= max_depth:
                current_id, path, path_actions = queue.pop(0)

                # Find outgoing delegations
                query = """
                    SELECT delegate_id, scope FROM delegations
                    WHERE principal_id = ? AND revoked_at IS NULL AND expires_at > ?
                """
                params: list[Any] = [current_id, now]

                if workflow_id is not None:
                    query += " AND (workflow_id = ? OR workflow_id IS NULL)"
                    params.append(workflow_id)

                cursor = conn.execute(query, params)
                rows = cursor.fetchall()

                for row in rows:
                    next_id = row["delegate_id"]
                    scope_value = row["scope"]

                    try:
                        edge_actions = (
                            set(json.loads(scope_value)) if scope_value else {"execute"}
                        )
                    except (json.JSONDecodeError, TypeError):
                        edge_actions = {"execute"}

                    # Effective actions = intersection of path actions and edge actions
                    new_path_actions = path_actions & edge_actions

                    if not new_path_actions:
                        continue  # No valid actions, skip this edge

                    if next_id == delegate_id:
                        valid_paths.append(
                            {
                                "path": path + [next_id],
                                "delegated_actions": sorted(list(new_path_actions)),
                            }
                        )
                        continue  # Found target, but keep searching for better paths

                    if next_id not in visited:
                        visited.add(next_id)
                        queue.append((next_id, path + [next_id], new_path_actions))

            # Return path with strongest permissions (prefer execute over read-only)
            if valid_paths:
                # Sort by: (1) has execute, (2) path length
                def path_strength(p: dict[str, Any]) -> tuple[int, int]:
                    has_execute = 1 if "execute" in p["delegated_actions"] else 0
                    return (
                        has_execute,
                        -len(p["path"]),
                    )  # Prefer execute, then shorter paths

                return max(valid_paths, key=path_strength)

            return None
        finally:
            conn.close()
