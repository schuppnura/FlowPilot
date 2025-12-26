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

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pathlib import Path


class DelegationGraphDB:
    """SQL-based graph database for delegation relationships."""
    
    def __init__(self, db_path: str = ":memory:"):
        """Initialize the database connection.
        
        Args:
            db_path: Path to SQLite database file. Use ":memory:" for in-memory database.
        """
        self.db_path = db_path
        self._init_schema()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        return conn
    
    def _init_schema(self) -> None:
        """Initialize the database schema."""
        conn = self._get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS delegations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    principal_id TEXT NOT NULL,
                    delegate_id TEXT NOT NULL,
                    workflow_id TEXT,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    revoked_at TEXT,
                    UNIQUE(principal_id, delegate_id, workflow_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_principal_id ON delegations(principal_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_delegate_id ON delegations(delegate_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_workflow_id ON delegations(workflow_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_expires_at ON delegations(expires_at)
            """)
            conn.commit()
        finally:
            conn.close()
    
    def insert_edge(
        self,
        principal_id: str,
        delegate_id: str,
        expires_at: str,
        workflow_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert a delegation edge.
        
        Args:
            principal_id: ID of the principal delegating authority
            delegate_id: ID of the delegate receiving authority
            expires_at: ISO 8601 timestamp when delegation expires
            workflow_id: Optional workflow ID to scope the delegation
            
        Returns:
            Dictionary with delegation details including created_at
        """
        created_at = datetime.now(timezone.utc).isoformat()
        
        conn = self._get_connection()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO delegations 
                (principal_id, delegate_id, workflow_id, expires_at, created_at, revoked_at)
                VALUES (?, ?, ?, ?, ?, NULL)
            """, (principal_id, delegate_id, workflow_id, expires_at, created_at))
            conn.commit()
            
            # Fetch the inserted row
            cursor = conn.execute("""
                SELECT * FROM delegations
                WHERE principal_id = ? AND delegate_id = ? AND (workflow_id = ? OR (workflow_id IS NULL AND ? IS NULL))
            """, (principal_id, delegate_id, workflow_id, workflow_id))
            row = cursor.fetchone()
            
            if not row:
                raise RuntimeError("Failed to retrieve inserted delegation")
            
            return {
                "principal_id": row["principal_id"],
                "delegate_id": row["delegate_id"],
                "workflow_id": row["workflow_id"],
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
        workflow_id: Optional[str] = None,
    ) -> bool:
        """Revoke a delegation edge.
        
        Args:
            principal_id: ID of the principal
            delegate_id: ID of the delegate
            workflow_id: Optional workflow ID to scope the revocation
            
        Returns:
            True if a delegation was revoked, False otherwise
        """
        revoked_at = datetime.now(timezone.utc).isoformat()
        
        conn = self._get_connection()
        try:
            cursor = conn.execute("""
                UPDATE delegations
                SET revoked_at = ?
                WHERE principal_id = ? AND delegate_id = ? 
                AND (workflow_id = ? OR (workflow_id IS NULL AND ? IS NULL))
                AND revoked_at IS NULL
            """, (revoked_at, principal_id, delegate_id, workflow_id, workflow_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def list_outgoing_edges(
        self,
        principal_id: str,
        workflow_id: Optional[str] = None,
        include_expired: bool = False,
    ) -> List[Dict[str, Any]]:
        """List all delegations from a principal.
        
        Args:
            principal_id: ID of the principal
            workflow_id: Optional workflow ID to filter by
            include_expired: If True, include expired delegations
            
        Returns:
            List of delegation dictionaries
        """
        now = datetime.now(timezone.utc).isoformat()
        
        conn = self._get_connection()
        try:
            query = """
                SELECT * FROM delegations
                WHERE principal_id = ? AND revoked_at IS NULL
            """
            params: List[Any] = [principal_id]
            
            if workflow_id is not None:
                query += " AND (workflow_id = ? OR workflow_id IS NULL)"
                params.append(workflow_id)
            
            if not include_expired:
                query += " AND expires_at > ?"
                params.append(now)
            
            query += " ORDER BY created_at DESC"
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            return [
                {
                    "principal_id": row["principal_id"],
                    "delegate_id": row["delegate_id"],
                    "workflow_id": row["workflow_id"],
                    "expires_at": row["expires_at"],
                    "created_at": row["created_at"],
                    "revoked_at": row["revoked_at"],
                }
                for row in rows
            ]
        finally:
            conn.close()
    
    def list_incoming_edges(
        self,
        delegate_id: str,
        workflow_id: Optional[str] = None,
        include_expired: bool = False,
    ) -> List[Dict[str, Any]]:
        """List all delegations to a delegate.
        
        Args:
            delegate_id: ID of the delegate
            workflow_id: Optional workflow ID to filter by
            include_expired: If True, include expired delegations
            
        Returns:
            List of delegation dictionaries
        """
        now = datetime.now(timezone.utc).isoformat()
        
        conn = self._get_connection()
        try:
            query = """
                SELECT * FROM delegations
                WHERE delegate_id = ? AND revoked_at IS NULL
            """
            params: List[Any] = [delegate_id]
            
            if workflow_id is not None:
                query += " AND (workflow_id = ? OR workflow_id IS NULL)"
                params.append(workflow_id)
            
            if not include_expired:
                query += " AND expires_at > ?"
                params.append(now)
            
            query += " ORDER BY created_at DESC"
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            return [
                {
                    "principal_id": row["principal_id"],
                    "delegate_id": row["delegate_id"],
                    "workflow_id": row["workflow_id"],
                    "expires_at": row["expires_at"],
                    "created_at": row["created_at"],
                    "revoked_at": row["revoked_at"],
                }
                for row in rows
            ]
        finally:
            conn.close()
    
    def find_delegation_path(
        self,
        principal_id: str,
        delegate_id: str,
        workflow_id: Optional[str] = None,
        max_depth: int = 5,
    ) -> Optional[List[str]]:
        """Find a delegation path from principal to delegate using BFS.
        
        Args:
            principal_id: Starting principal ID
            delegate_id: Target delegate ID
            workflow_id: Optional workflow ID to scope the search
            max_depth: Maximum depth to search (prevent infinite loops)
            
        Returns:
            List of IDs representing the path from principal to delegate, or None if not found
        """
        if principal_id == delegate_id:
            return [principal_id]
        
        now = datetime.now(timezone.utc).isoformat()
        
        conn = self._get_connection()
        try:
            # BFS search
            queue: List[tuple[str, List[str]]] = [(principal_id, [principal_id])]
            visited: set[str] = {principal_id}
            
            while queue and len(queue[0][1]) <= max_depth:
                current_id, path = queue.pop(0)
                
                # Find outgoing delegations
                query = """
                    SELECT delegate_id FROM delegations
                    WHERE principal_id = ? AND revoked_at IS NULL AND expires_at > ?
                """
                params: List[Any] = [current_id, now]
                
                if workflow_id is not None:
                    query += " AND (workflow_id = ? OR workflow_id IS NULL)"
                    params.append(workflow_id)
                
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
                
                for row in rows:
                    next_id = row["delegate_id"]
                    
                    if next_id == delegate_id:
                        return path + [next_id]
                    
                    if next_id not in visited:
                        visited.add(next_id)
                        queue.append((next_id, path + [next_id]))
            
            return None
        finally:
            conn.close()

