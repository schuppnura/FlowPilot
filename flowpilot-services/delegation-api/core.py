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

from graphdb import DelegationGraphDB
from utils import require_non_empty_string, read_env_string

# Delegation allowed actions configuration (imported from environment)
_DELEGATION_ALLOWED_ACTIONS_STR = read_env_string("DELEGATION_ALLOWED_ACTIONS", "read,execute")
DELEGATION_ALLOWED_ACTIONS = {action.strip() for action in _DELEGATION_ALLOWED_ACTIONS_STR.split(",") if action.strip()}


class DelegationService:
    # Business logic for delegation management.

    def __init__(self, graphdb: DelegationGraphDB):
        # Initialize the delegation service.
        #
        # Args:
        #     graphdb: Graph database instance
        self.graphdb = graphdb

    def create_delegation(
        self,
        principal_id: str,
        delegate_id: str,
        expires_in_days: int = 7,
        workflow_id: Optional[str] = None,
        scope: Optional[List[str]] = None,
        delegator_id: Optional[str] = None,  # ID of the authenticated user creating this delegation
    ) -> Dict[str, Any]:
        # Create a delegation relationship.
        #
        # Args:
        #     principal_id: ID of the principal delegating authority (resource owner)
        #     delegate_id: ID of the delegate receiving authority
        #     expires_in_days: Number of days until expiration (default 7)
        #     workflow_id: Optional workflow ID to scope the delegation
        #     scope: List of actions (e.g. ["read"] or ["read", "execute"]). Defaults to ["execute"]
        #     delegator_id: ID of the authenticated user creating this delegation (from JWT)
        #
        # Returns:
        #     Dictionary with delegation details
        principal_id = require_non_empty_string(principal_id, "principal_id")
        delegate_id = require_non_empty_string(delegate_id, "delegate_id")

        if principal_id == delegate_id:
            raise ValueError("principal_id cannot be the same as delegate_id")

        if expires_in_days <= 0:
            raise ValueError("expires_in_days must be positive")
        
        # Validate that delegator can only delegate permissions they have
        if delegator_id and delegator_id != principal_id:
            # Delegator is not the resource owner - check what permissions they have
            delegator_validation = self.validate_delegation(
                principal_id=principal_id,
                delegate_id=delegator_id,
                workflow_id=workflow_id,
            )
            
            if not delegator_validation.get("valid"):
                raise ValueError("You cannot delegate permissions you don't have")
            
            delegator_actions = set(delegator_validation.get("effective_actions", []))
            requested_actions = set(scope) if scope else {"execute"}
            
            # Check if delegator is trying to delegate more than they have
            if not requested_actions.issubset(delegator_actions):
                raise ValueError(
                    f"Cannot delegate {list(requested_actions)}. You only have {list(delegator_actions)} permissions."
                )

        # Calculate expiration time
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        expires_at_iso = expires_at.isoformat()

        # Insert delegation edge
        delegation = self.graphdb.insert_edge(
            principal_id=principal_id,
            delegate_id=delegate_id,
            workflow_id=workflow_id,
            expires_at=expires_at_iso,
            scope=scope,
        )

        return delegation

    def revoke_delegation(
        self,
        principal_id: str,
        delegate_id: str,
        workflow_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Revoke a delegation relationship.
        #
        # Args:
        #     principal_id: ID of the principal
        #     delegate_id: ID of the delegate
        #     workflow_id: Optional workflow ID to scope the revocation
        #
        # Returns:
        #     Dictionary with revocation status
        principal_id = require_non_empty_string(principal_id, "principal_id")
        delegate_id = require_non_empty_string(delegate_id, "delegate_id")

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
        # List delegations.
        #
        # Args:
        #     principal_id: Filter by principal ID (outgoing delegations)
        #     delegate_id: Filter by delegate ID (incoming delegations)
        #     workflow_id: Filter by workflow ID
        #     include_expired: Include expired delegations
        #
        # Returns:
        #     List of delegation dictionaries
        if principal_id:
            principal_id = require_non_empty_string(principal_id, "principal_id")
            return self.graphdb.list_outgoing_edges(
                principal_id=principal_id,
                workflow_id=workflow_id,
                include_expired=include_expired,
            )
        elif delegate_id:
            delegate_id = require_non_empty_string(delegate_id, "delegate_id")
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
        # Validate that a delegation exists and is active.
        #
        # Args:
        #     principal_id: ID of the principal (resource owner)
        #     delegate_id: ID of the delegate (user/agent attempting to act)
        #     workflow_id: Optional workflow ID to scope the validation
        #
        # Returns:
        #     Dictionary with validation result, delegation chain, and effective actions
        principal_id = require_non_empty_string(principal_id, "principal_id")
        delegate_id = require_non_empty_string(delegate_id, "delegate_id")

        # Direct match: delegate is the principal
        if delegate_id == principal_id:
            return {
                "valid": True,
                "delegation_chain": [principal_id],
                "effective_actions": list(DELEGATION_ALLOWED_ACTIONS),
            }

        # Find delegation path with action computation
        path_result = self.graphdb.find_delegation_path(
            principal_id=principal_id,
            delegate_id=delegate_id,
            workflow_id=workflow_id,
        )

        if path_result:
            return {
                "valid": True,
                "delegation_chain": path_result["path"],
                "effective_actions": path_result["effective_actions"],
            }
        else:
            return {
                "valid": False,
                "delegation_chain": [],
                "effective_actions": [],
            }

