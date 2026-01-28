# FlowPilot Delegation API - PostgreSQL Graph Database Handlers
#
# PostgreSQL-based graph database for delegation relationships.
# Migrated from SQLite for Cloud SQL deployment.
#
# Graph structure:
# - Nodes: principal_id (user or agent)
# - Edges: delegation relationships with metadata (workflow_id, expires_at, created_at)
# - Edge type: "delegates" (principal_id -> delegate_id)

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras


class DelegationGraphDB:
    # PostgreSQL-based graph database for delegation relationships.

    def __init__(self, connection_params: dict[str, Any] | None = None):
        # Initialize the database connection parameters.
        # Args:
        #     connection_params: Dict with database connection parameters
        #                       If None, will use environment variables
        if connection_params is None:
            connection_params = self._get_connection_params_from_env()

        self.connection_params = connection_params
        self._schema_initialized = False

    def _get_connection_params_from_env(self) -> dict[str, Any]:
        # Get connection parameters from environment variables.
        # Supports both Cloud SQL unix socket and standard TCP connections.
        db_host = os.environ.get("DB_HOST")
        db_unix_socket = os.environ.get("DB_UNIX_SOCKET")

        if db_unix_socket:
            # Cloud SQL unix socket connection
            return {
                "host": db_unix_socket,
                "database": os.environ.get("DB_NAME", "flowpilot_delegations"),
                "user": os.environ.get("DB_USER", "postgres"),
                "password": os.environ.get("DB_PASSWORD", ""),
            }
        elif db_host:
            # Standard TCP connection
            return {
                "host": db_host,
                "port": int(os.environ.get("DB_PORT", "5432")),
                "database": os.environ.get("DB_NAME", "flowpilot_delegations"),
                "user": os.environ.get("DB_USER", "postgres"),
                "password": os.environ.get("DB_PASSWORD", ""),
            }
        else:
            # Fallback - localhost
            return {
                "host": "localhost",
                "port": 5432,
                "database": os.environ.get("DB_NAME", "flowpilot_delegations"),
                "user": os.environ.get("DB_USER", "postgres"),
                "password": os.environ.get("DB_PASSWORD", ""),
            }

    @contextmanager
    def _get_connection(self):
        # Get a database connection as a context manager.
        conn = psycopg2.connect(**self.connection_params)
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        # Lazily initialize the database schema on first use.
        if self._schema_initialized:
            return

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS delegations (
                        id SERIAL PRIMARY KEY,
                        principal_id TEXT NOT NULL,
                        delegate_id TEXT NOT NULL,
                        workflow_id TEXT,
                        scope TEXT NOT NULL DEFAULT '["execute"]',
                        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        revoked_at TIMESTAMP WITH TIME ZONE,
                        UNIQUE(principal_id, delegate_id, workflow_id)
                    )
                """)

                # Create indexes
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_principal_id ON delegations(principal_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_delegate_id ON delegations(delegate_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_workflow_id ON delegations(workflow_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_expires_at ON delegations(expires_at)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_revoked_at ON delegations(revoked_at)
                """)

                conn.commit()

        self._schema_initialized = True

    def insert_edge(
        self,
        principal_id: str,
        delegate_id: str,
        expires_at: str,
        workflow_id: str | None = None,
        scope: list[str] | None = None,
    ) -> dict[str, Any]:
        # Insert a delegation edge.
        # Args:
        #     principal_id: ID of the principal delegating authority
        #     delegate_id: ID of the delegate receiving authority
        #     expires_at: ISO 8601 timestamp when delegation expires
        #     workflow_id: Optional workflow ID to scope the delegation
        #     scope: List of actions (e.g. ["read"] or ["read", "execute"]). Defaults to ["execute"]
        # Returns:
        #     Dictionary with delegation details including created_at
        self._ensure_schema()

        if scope is None:
            scope = ["execute"]
        scope_json = json.dumps(scope)

        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Check if delegation already exists
                cursor.execute("""
                    SELECT * FROM delegations
                    WHERE principal_id = %s AND delegate_id = %s 
                    AND (workflow_id = %s OR (workflow_id IS NULL AND %s IS NULL))
                    AND revoked_at IS NULL
                """, (principal_id, delegate_id, workflow_id, workflow_id))

                existing_row = cursor.fetchone()

                if existing_row:
                    # Delegation already exists - check if it needs updating
                    existing_scope_json = existing_row["scope"]
                    try:
                        existing_scope = (
                            json.loads(existing_scope_json)
                            if existing_scope_json
                            else ["execute"]
                        )
                    except (json.JSONDecodeError, TypeError):
                        existing_scope = ["execute"]

                    # Convert to sets for comparison
                    existing_scope_set = set(existing_scope)
                    new_scope_set = set(scope)

                    # Only update if scope is being expanded or expiration extended
                    needs_update = (
                        not new_scope_set.issubset(existing_scope_set)  # Scope is expanding
                        or expires_at
                        > existing_row["expires_at"].isoformat()  # Expiration is being extended
                    )

                    if not needs_update:
                        # Return existing delegation unchanged
                        return {
                            "principal_id": existing_row["principal_id"],
                            "delegate_id": existing_row["delegate_id"],
                            "workflow_id": existing_row["workflow_id"],
                            "scope": existing_scope,
                            "expires_at": existing_row["expires_at"].isoformat(),
                            "created_at": existing_row["created_at"].isoformat(),
                            "revoked_at": existing_row["revoked_at"].isoformat() if existing_row["revoked_at"] else None,
                        }

                    # Update existing delegation with expanded scope or extended expiration
                    merged_scope = sorted(list(existing_scope_set.union(new_scope_set)))
                    merged_scope_json = json.dumps(merged_scope)
                    new_expires_at = max(expires_at, existing_row["expires_at"].isoformat())

                    cursor.execute("""
                        UPDATE delegations
                        SET scope = %s, expires_at = %s
                        WHERE principal_id = %s AND delegate_id = %s 
                        AND (workflow_id = %s OR (workflow_id IS NULL AND %s IS NULL))
                        AND revoked_at IS NULL
                    """, (
                        merged_scope_json,
                        new_expires_at,
                        principal_id,
                        delegate_id,
                        workflow_id,
                        workflow_id,
                    ))
                    conn.commit()

                    # Fetch updated row
                    cursor.execute("""
                        SELECT * FROM delegations
                        WHERE principal_id = %s AND delegate_id = %s 
                        AND (workflow_id = %s OR (workflow_id IS NULL AND %s IS NULL))
                    """, (principal_id, delegate_id, workflow_id, workflow_id))
                    row = cursor.fetchone()
                else:
                    # Insert new delegation
                    created_at = datetime.now(timezone.utc).isoformat()
                    cursor.execute("""
                        INSERT INTO delegations 
                        (principal_id, delegate_id, workflow_id, scope, expires_at, created_at, revoked_at)
                        VALUES (%s, %s, %s, %s, %s, %s, NULL)
                    """, (
                        principal_id,
                        delegate_id,
                        workflow_id,
                        scope_json,
                        expires_at,
                        created_at,
                    ))
                    conn.commit()

                    # Fetch the inserted row
                    cursor.execute("""
                        SELECT * FROM delegations
                        WHERE principal_id = %s AND delegate_id = %s 
                        AND (workflow_id = %s OR (workflow_id IS NULL AND %s IS NULL))
                    """, (principal_id, delegate_id, workflow_id, workflow_id))
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
                    "expires_at": row["expires_at"].isoformat(),
                    "created_at": row["created_at"].isoformat(),
                    "revoked_at": row["revoked_at"].isoformat() if row["revoked_at"] else None,
                }

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
        self._ensure_schema()
        revoked_at = datetime.now(timezone.utc)

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE delegations
                    SET revoked_at = %s
                    WHERE principal_id = %s AND delegate_id = %s 
                    AND (workflow_id = %s OR (workflow_id IS NULL AND %s IS NULL))
                    AND revoked_at IS NULL
                """, (revoked_at, principal_id, delegate_id, workflow_id, workflow_id))

                conn.commit()
                return cursor.rowcount > 0

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
        self._ensure_schema()
        now = datetime.now(timezone.utc)

        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                query = """
                    SELECT * FROM delegations
                    WHERE principal_id = %s AND revoked_at IS NULL
                """
                params: list[Any] = [principal_id]

                if workflow_id is not None:
                    query += " AND (workflow_id = %s OR workflow_id IS NULL)"
                    params.append(workflow_id)

                if not include_expired:
                    query += " AND expires_at > %s"
                    params.append(now)

                query += " ORDER BY created_at DESC"

                cursor.execute(query, params)
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
                            "expires_at": row["expires_at"].isoformat(),
                            "created_at": row["created_at"].isoformat(),
                            "revoked_at": row["revoked_at"].isoformat() if row["revoked_at"] else None,
                        }
                    )

                return result

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
        self._ensure_schema()
        now = datetime.now(timezone.utc)

        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                query = """
                    SELECT * FROM delegations
                    WHERE delegate_id = %s AND revoked_at IS NULL
                """
                params: list[Any] = [delegate_id]

                if workflow_id is not None:
                    query += " AND (workflow_id = %s OR workflow_id IS NULL)"
                    params.append(workflow_id)

                if not include_expired:
                    query += " AND expires_at > %s"
                    params.append(now)

                query += " ORDER BY created_at DESC"

                cursor.execute(query, params)
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
                            "expires_at": row["expires_at"].isoformat(),
                            "created_at": row["created_at"].isoformat(),
                            "revoked_at": row["revoked_at"].isoformat() if row["revoked_at"] else None,
                        }
                    )

                return result

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
        self._ensure_schema()

        if principal_id == delegate_id:
            return {"path": [principal_id], "delegated_actions": ["read", "execute"]}

        now = datetime.now(timezone.utc)

        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
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
                        WHERE principal_id = %s AND revoked_at IS NULL AND expires_at > %s
                    """
                    params: list[Any] = [current_id, now]

                    if workflow_id is not None:
                        query += " AND (workflow_id = %s OR workflow_id IS NULL)"
                        params.append(workflow_id)

                    cursor.execute(query, params)
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
