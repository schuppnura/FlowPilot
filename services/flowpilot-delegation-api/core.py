# FlowPilot Delegation API - Core Business Logic
#
# Business logic for delegation management including:
# - Creating delegations with expiration
# - Validating delegation chains
# - Listing delegations
# - Querying users by persona (via Keycloak)

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

from graphdb import DelegationGraphDB
from utils import validate_non_empty_string


class DelegationService:
    """Business logic for delegation management."""
    
    def __init__(self, graphdb: DelegationGraphDB):
        """Initialize the delegation service.
        
        Args:
            graphdb: Graph database instance
        """
        self.graphdb = graphdb
    
    def create_delegation(
        self,
        principal_id: str,
        delegate_id: str,
        expires_in_days: int = 7,
        workflow_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a delegation relationship.
        
        Args:
            principal_id: ID of the principal delegating authority
            delegate_id: ID of the delegate receiving authority
            expires_in_days: Number of days until expiration (default 7)
            workflow_id: Optional workflow ID to scope the delegation
            
        Returns:
            Dictionary with delegation details
        """
        principal_id = validate_non_empty_string(principal_id, "principal_id")
        delegate_id = validate_non_empty_string(delegate_id, "delegate_id")
        
        if principal_id == delegate_id:
            raise ValueError("principal_id cannot be the same as delegate_id")
        
        if expires_in_days <= 0:
            raise ValueError("expires_in_days must be positive")
        
        # Calculate expiration time
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        expires_at_iso = expires_at.isoformat()
        
        # Insert delegation edge
        delegation = self.graphdb.insert_edge(
            principal_id=principal_id,
            delegate_id=delegate_id,
            workflow_id=workflow_id,
            expires_at=expires_at_iso,
        )
        
        return delegation
    
    def revoke_delegation(
        self,
        principal_id: str,
        delegate_id: str,
        workflow_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Revoke a delegation relationship.
        
        Args:
            principal_id: ID of the principal
            delegate_id: ID of the delegate
            workflow_id: Optional workflow ID to scope the revocation
            
        Returns:
            Dictionary with revocation status
        """
        principal_id = validate_non_empty_string(principal_id, "principal_id")
        delegate_id = validate_non_empty_string(delegate_id, "delegate_id")
        
        revoked = self.graphdb.revoke_edge(
            principal_id=principal_id,
            delegate_id=delegate_id,
            workflow_id=workflow_id,
        )
        
        if not revoked:
            raise ValueError("Delegation not found or already revoked")
        
        return {
            "principal_id": principal_id,
            "delegate_id": delegate_id,
            "workflow_id": workflow_id,
            "revoked": True,
        }
    
    def list_delegations(
        self,
        principal_id: Optional[str] = None,
        delegate_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        include_expired: bool = False,
    ) -> List[Dict[str, Any]]:
        """List delegations.
        
        Args:
            principal_id: Filter by principal ID (outgoing delegations)
            delegate_id: Filter by delegate ID (incoming delegations)
            workflow_id: Filter by workflow ID
            include_expired: Include expired delegations
            
        Returns:
            List of delegation dictionaries
        """
        if principal_id:
            principal_id = validate_non_empty_string(principal_id, "principal_id")
            return self.graphdb.list_outgoing_edges(
                principal_id=principal_id,
                workflow_id=workflow_id,
                include_expired=include_expired,
            )
        elif delegate_id:
            delegate_id = validate_non_empty_string(delegate_id, "delegate_id")
            return self.graphdb.list_incoming_edges(
                delegate_id=delegate_id,
                workflow_id=workflow_id,
                include_expired=include_expired,
            )
        else:
            raise ValueError("Either principal_id or delegate_id must be provided")
    
    def validate_delegation(
        self,
        principal_id: str,
        delegate_id: str,
        workflow_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate that a delegation exists and is active.
        
        Args:
            principal_id: ID of the principal (resource owner)
            delegate_id: ID of the delegate (user/agent attempting to act)
            workflow_id: Optional workflow ID to scope the validation
            
        Returns:
            Dictionary with validation result and delegation chain
        """
        principal_id = validate_non_empty_string(principal_id, "principal_id")
        delegate_id = validate_non_empty_string(delegate_id, "delegate_id")
        
        # Direct match: delegate is the principal
        if delegate_id == principal_id:
            return {
                "valid": True,
                "delegation_chain": [principal_id],
            }
        
        # Find delegation path
        path = self.graphdb.find_delegation_path(
            principal_id=principal_id,
            delegate_id=delegate_id,
            workflow_id=workflow_id,
        )
        
        if path:
            return {
                "valid": True,
                "delegation_chain": path,
            }
        else:
            return {
                "valid": False,
                "delegation_chain": [],
            }
    
    @staticmethod
    def list_users_by_persona(
        keycloak_base_url: str,
        keycloak_realm: str,
        keycloak_admin_username: str,
        keycloak_admin_password: str,
        persona: str,
        verify_tls: bool = False,
    ) -> List[Dict[str, Any]]:
        """List users who have a specific persona.
        
        Args:
            keycloak_base_url: Keycloak base URL (e.g., https://keycloak:8443)
            keycloak_realm: Keycloak realm name
            keycloak_admin_username: Keycloak admin username
            keycloak_admin_password: Keycloak admin password
            persona: Persona value to filter by (e.g., "travel-agent")
            verify_tls: Whether to verify TLS certificates
            
        Returns:
            List of user dictionaries with id, username, and email
        """
        # Get admin token
        token_url = f"{keycloak_base_url.rstrip('/')}/realms/master/protocol/openid-connect/token"
        token_payload = {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": keycloak_admin_username,
            "password": keycloak_admin_password,
        }
        
        token_response = requests.post(token_url, data=token_payload, timeout=10, verify=verify_tls)
        if token_response.status_code != 200:
            error_msg = f"Failed to get Keycloak admin token (status {token_response.status_code}): {token_response.text}"
            print(f"[delegation-api] {error_msg}", flush=True)
            raise RuntimeError(error_msg)
        
        access_token = token_response.json().get("access_token")
        if not access_token:
            error_msg = "Token response did not contain access_token"
            print(f"[delegation-api] {error_msg}", flush=True)
            raise RuntimeError(error_msg)
        
        # Fetch all users from Keycloak
        users_url = f"{keycloak_base_url.rstrip('/')}/admin/realms/{keycloak_realm}/users"
        headers = {"Authorization": f"Bearer {access_token}"}
        users_response = requests.get(users_url, headers=headers, timeout=30, verify=verify_tls)
        if users_response.status_code != 200:
            error_msg = f"Failed to fetch users from Keycloak (status {users_response.status_code}): {users_response.text}"
            print(f"[delegation-api] {error_msg}", flush=True)
            raise RuntimeError(error_msg)
        
        all_users = users_response.json()
        if not isinstance(all_users, list):
            error_msg = f"Unexpected response format from Keycloak: {type(all_users)}"
            print(f"[delegation-api] {error_msg}", flush=True)
            raise RuntimeError(error_msg)
        
        print(f"[delegation-api] Fetched {len(all_users)} users from Keycloak, filtering for persona='{persona}'", flush=True)
        
        # Filter users by persona attribute
        matching_users: List[Dict[str, Any]] = []
        for user in all_users:
            user_id = user.get("id")
            username = user.get("username")
            email = user.get("email")
            
            if not user_id or not username:
                continue
            
            # Check persona attribute
            attributes = user.get("attributes") or {}
            persona_attr = attributes.get("persona")
            
            # Persona can be a list or a single value
            # Keycloak returns attributes as lists (even for single values)
            personas: List[str] = []
            if isinstance(persona_attr, list):
                personas = [str(p).strip() for p in persona_attr if p and str(p).strip()]
            elif persona_attr:
                personas = [str(persona_attr).strip()]
            
            # Check if the requested persona is in the user's personas (case-sensitive match)
            if persona in personas:
                print(f"[delegation-api] Found matching user: username={username}, id={user_id}, personas={personas}", flush=True)
                matching_users.append({
                    "id": user_id,
                    "username": username,
                    "email": email,
                })
            elif personas:
                print(f"[delegation-api] User {username} has personas {personas}, but not matching '{persona}'", flush=True)
        
        print(f"[delegation-api] Returning {len(matching_users)} users with persona '{persona}'", flush=True)
        return matching_users

