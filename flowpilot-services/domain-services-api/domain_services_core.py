# FlowPilot Domain Services API - Core Logic
#
# Travel domain backend implementation. This is the system of record for travel workflow
# state and acts as the Policy Enforcement Point (PEP) for authorization decisions.
#
# IMPORTANT: This is TRAVEL-DOMAIN SPECIFIC. It implements travel workflows with
# flights, hotels, restaurants, museums, trains, etc. Other domains (nursing, business
# events) would have their own domain-services-api implementations with different
# templates, items, and business logic, but all follow the same workflow PEP pattern.
#
# Key responsibilities:
# - Travel workflow creation from trip templates
# - Travel itinerary item management and state tracking (flights, hotels, restaurants, etc.)
# - Policy enforcement point (PEP) that delegates decisions to the PDP via AuthZ API
# - Dry-run semantics for workflow execution
# - In-memory workflow storage (demo only)
#
# Domain context: Travel - workflows represent trips/itineraries with travel-specific items.

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List, Optional

import requests
import security
from template_loader import load_workflow_templates_from_directory
from utils import (
    build_url,
    coerce_timestamp,
    get_http_config,
    http_post_json,
    read_env_string,
    require_non_empty_string,
)

# Service identity configuration (required environment variable)
SERVICE_ID = read_env_string("SERVICE_ID")


class PolicyDeniedError(PermissionError):
    # Exception raised when authorization policy denies access, carrying reason codes
    def __init__(
        self, message: str, reason_codes: list[str], advice: list[dict[str, Any]]
    ):
        super().__init__(message)
        self.reason_codes = reason_codes
        self.advice = advice


class FlowPilotService:
    def __init__(self, config: dict[str, Any]) -> None:
        # Initialize service state
        # why: keep in-memory store and config together
        # side effect: none.
        self._config = dict(config)
        self._templates: dict[str, dict[str, Any]] = {}
        self._workflows: dict[str, dict[str, Any]] = {}

    def load_templates(self) -> None:
        # Load templates from directory
        # assumptions: directory exists and contains valid JSON
        # side effect: filesystem reads.
        domain = require_non_empty_string(str(self._config.get("domain", "")), "domain")
        template_directory = require_non_empty_string(
            str(self._config.get("template_directory", "")), "template_directory"
        )
        self._templates = load_workflow_templates_from_directory(
            template_directory=template_directory, domain=domain
        )

    def get_template_count(self) -> int:
        # Return number of loaded templates
        # why: health/debug
        # side effect: none.
        return len(self._templates)

    def get_workflow_count(self) -> int:
        # Return number of workflows in memory
        # why: health/debug
        # side effect: none.
        return len(self._workflows)

    def list_workflows(self) -> list[dict[str, Any]]:
        # Return minimal workflow metadata for all workflows
        # why: allow clients to select an existing workflow
        # side effect: none.
        workflows: list[dict[str, Any]] = []
        for workflow_id, workflow in self._workflows.items():
            if not isinstance(workflow, dict):
                continue
            workflows.append(
                {
                    "workflow_id": str(workflow.get("workflow_id", workflow_id)),
                    "template_id": str(workflow.get("template_id", "")),
                    "owner_sub": str(workflow.get("owner_sub", "")),
                    "created_at": str(workflow.get("created_at", "")),
                    "departure_date": str(workflow.get("departure_date", "")),
                    "item_count": (
                        len(workflow.get("items", []))
                        if isinstance(workflow.get("items", []), list)
                        else 0
                    ),
                }
            )
        workflows.sort(
            key=lambda w: str(w.get("created_at", "")), reverse=True
        )  # Most recent first
        return workflows

    def list_workflow_templates(self) -> list[dict[str, Any]]:
        # Return minimal template metadata
        # why: client selection without leaking full template details
        # side effect: none.
        templates: list[dict[str, Any]] = []
        for template_id, template in self._templates.items():
            templates.append(
                {
                    "template_id": template_id,
                    "name": str(template.get("name", template_id)),
                    "domain": str(
                        template.get("domain", self._config.get("domain", "travel"))
                    ),
                    "item_count": (
                        len(template.get("items", []))
                        if isinstance(template.get("items", []), list)
                        else 0
                    ),
                }
            )
        templates.sort(key=lambda entry: str(entry.get("template_id", "")))
        return templates

    def create_workflow_from_template(
        self,
        template_id: str,
        owner_sub: str,
        start_date: str,
        persona_title: str,  # REQUIRED - persona title must be specified when creating workflows
        persona_circle: str,  # REQUIRED - persona circle must be specified
        domain: str | None = None,
    ) -> dict[str, Any]:
        # Create a workflow and itinerary items from a template
        # IMPORTANT: Both persona_title and persona_circle are now required
        # side effect: stores a new workflow in memory.
        template_id = require_non_empty_string(template_id, "template_id")
        owner_sub = require_non_empty_string(owner_sub, "owner_sub")
        # Note: start_date parameter is accepted but not used (for API compatibility)

        if template_id not in self._templates:
            raise KeyError(f"Template not found: {template_id}")

        template = self._templates[template_id]
        workflow_id = "w_" + uuid.uuid4().hex[:8]
        created_at = coerce_timestamp()

        items: list[dict[str, Any]] = []
        raw_items = template.get("items", [])
        if isinstance(raw_items, list):
            for raw in raw_items:
                if not isinstance(raw, dict):
                    continue
                item_id = "i_" + uuid.uuid4().hex[:8]
                kind = str(raw.get("kind", "unknown"))
                item_dict = {
                    "item_id": item_id,
                    "kind": kind,
                    "title": str(raw.get("title", kind)),
                    "planned_for": raw.get("planned_for"),
                    "planned_price": raw.get("planned_price"),
                    "status": "planned",
                    "last_decision": None,
                    "last_reason_codes": [],
                    "last_advice": [],
                }
                # Only include airline_risk_score if present in template
                if "airline_risk_score" in raw:
                    item_dict["airline_risk_score"] = raw["airline_risk_score"]
                # Copy optional detail fields from template to workflow item
                for field in [
                    "type",
                    "star_rating",
                    "cuisine",
                    "city",
                    "neighborhood",
                    "departure_airport",
                    "arrival_airport",
                ]:
                    if field in raw:
                        item_dict[field] = raw[field]
                items.append(item_dict)

        # Use provided domain or fall back to config default
        workflow_domain = domain if domain else self._config.get("domain", "travel")
        
        print(f"[DEBUG] Storing workflow {workflow_id} with persona_title={repr(persona_title)}, persona_circle={repr(persona_circle)}", flush=True)
        workflow: dict[str, Any] = {
            "workflow_id": workflow_id,
            "template_id": template_id,
            "owner_sub": owner_sub,
            "owner_persona_title": persona_title,  # Store the persona title
            "owner_persona_circle": persona_circle,  # Store the persona circle
            "domain": workflow_domain,  # Store domain for policy_hint routing
            "created_at": created_at,
            "departure_date": start_date,  # Use the start_date parameter provided by the user
            "items": items,
        }
        self._workflows[workflow_id] = workflow

        return {
            "workflow_id": workflow_id,
            "owner_sub": owner_sub,
            "created_at": created_at,
            "item_count": len(items),
        }

    def create_agent_delegation(
        self,
        workflow_id: str,
        owner_sub: str,
        agent_sub: str,
        user_token: str | None = None,
        expires_in_days: int = 7,
    ) -> None:
        # Create a delegation for the AI agent to access the workflow
        # side effect: network I/O to delegation-api.
        workflow_id = require_non_empty_string(workflow_id, "workflow_id")
        owner_sub = require_non_empty_string(owner_sub, "owner_sub")
        agent_sub = require_non_empty_string(agent_sub, "agent_sub")

        delegation_api_base_url = str(self._config.get("delegation_api_base_url", ""))
        if not delegation_api_base_url:
            raise ValueError("delegation_api_base_url not configured")

        url = build_url(delegation_api_base_url, "/v1/delegations")

        # Use fixed agent identity (simplified for Cloud Run deployment)
        agent_sub = "agent-runner"

        # Always use service token for service-to-service authentication
        token = security.get_service_token()

        body = {
            "principal_id": owner_sub,
            "delegate_id": agent_sub,
            "workflow_id": workflow_id,
            "scope": ["read", "execute"],
            "expires_in_days": expires_in_days,
        }

        headers = {"Authorization": f"Bearer {token}"} if token else {}
        # Use centralized http_post_json for logging and error handling
        http_post_json(
            url=url,
            payload=body,
            headers=headers if headers else None,
        )

    def check_authorization(
        self,
        action: str,
        user_sub: str,
        user_persona_title: str,
        user_persona_circle: str,
        user_token: str | None = None,
        workflow_id: str | None = None,
        domain: str | None = None,
    ) -> dict[str, Any]:
        # Generic authorization check for any action on workflows
        # Acts as PEP - delegates all authorization decisions to authz-api/OPA
        # Returns authorization decision metadata (decision, reason_codes, advice)
        # Raises PolicyDeniedError if access is denied
        #
        # Args:
        #   action: The action to check (create, read, update, delete, execute)
        #   user_sub: User subject ID
        #   user_persona_title: User's selected persona title (required)
        #   user_persona_circle: User's selected persona circle (required)
        #   user_token: Optional user token for authentication
        #   workflow_id: Optional workflow ID (required for read/update/delete/execute, not for create)
        #   domain: Optional domain override (defaults to config domain)
        
        # For actions other than create, we need an existing workflow
        if action != "create" and workflow_id:
            workflow = self._get_workflow_or_raise(workflow_id)
        else:
            workflow = None
        
        # Build principal_user object (no claims - only id, persona title, and circle)
        principal_user: dict[str, Any] = {
            "type": "user",
            "id": user_sub,
            "persona_title": user_persona_title,
            "persona_circle": user_persona_circle,
        }
        
        # Call authz-api - let OPA make all policy decisions
        # Pass workflow=None for create action
        decision_payload = self._call_authz_for_workflow(
            workflow=workflow,
            principal_user=principal_user,
            action=action,
            user_token=user_token,
            workflow_domain=domain,
        )
        
        decision = str(decision_payload.get("decision", "deny"))
        reason_codes = list(decision_payload.get("reason_codes", []))
        advice = list(decision_payload.get("advice", []))
        
        if decision != "allow":
            raise PolicyDeniedError(
                f"{action.capitalize()} access denied: decision={decision} reason_codes={reason_codes}",
                reason_codes=reason_codes,
                advice=advice,
            )
        
        return {
            "decision": decision,
            "reason_codes": reason_codes,
            "advice": advice,
        }

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        # Return a workflow record
        # assumptions: workflow exists
        # side effect: none.
        workflow_id = require_non_empty_string(workflow_id, "workflow_id")
        if workflow_id not in self._workflows:
            raise KeyError(f"Workflow not found: {workflow_id}")
        workflow = self._workflows[workflow_id]
        result = {
            "workflow_id": str(workflow.get("workflow_id")),
            "template_id": str(workflow.get("template_id")),
            "owner_sub": str(workflow.get("owner_sub")),
            "owner_persona_title": workflow.get("owner_persona_title"),  # Required for authz checks
            "owner_persona_circle": workflow.get("owner_persona_circle"),  # Required for authz checks
            "domain": workflow.get("domain"),  # Required for policy_hint
            "departure_date": workflow.get("departure_date"),  # Required for advance notice checks
            "created_at": str(workflow.get("created_at")),
            "item_count": (
                len(workflow.get("items", []))
                if isinstance(workflow.get("items", []), list)
                else 0
            ),
        }
        return result

    def get_workflow_items(self, workflow_id: str) -> dict[str, Any]:
        # Return workflow items for agent-runner
        # assumptions: workflow exists
        # side effect: none.
        workflow_id = require_non_empty_string(workflow_id, "workflow_id")
        if workflow_id not in self._workflows:
            raise KeyError(f"Workflow not found: {workflow_id}")

        workflow = self._workflows[workflow_id]
        items_out: list[dict[str, Any]] = []
        for item in workflow.get("items", []):
            if not isinstance(item, dict):
                continue
            item_dict = {
                "item_id": str(item.get("item_id")),
                "kind": str(item.get("kind", "unknown")),
                "title": str(item.get("title", "")),
                "status": str(item.get("status", "unknown")),
            }
            # Include all optional detail fields if present
            for field in [
                "type",
                "star_rating",
                "cuisine",
                "city",
                "neighborhood",
                "departure_airport",
                "arrival_airport",
            ]:
                if field in item:
                    item_dict[field] = item[field]
            items_out.append(item_dict)

        return {"workflow_id": workflow_id, "items": items_out}

    def execute_workflow_item(
        self,
        workflow_id: str,
        workflow_item_id: str,
        principal_user: dict[str, Any],
        dry_run: bool,
    ) -> dict[str, Any]:
        # Execute a workflow item with AuthZ decision
        # why: PEP responsibility
        # side effects: network I/O + optional state mutation.
        # AuthZEN: Accept principal_user object instead of principal_sub and user_token
        workflow_id = require_non_empty_string(workflow_id, "workflow_id")
        workflow_item_id = require_non_empty_string(
            workflow_item_id, "workflow_item_id"
        )
        if not isinstance(principal_user, dict) or not principal_user.get("id"):
            raise ValueError("Invalid principal_user object")

        principal_user.get("id", "")

        workflow = self._get_workflow_or_raise(workflow_id=workflow_id)
        # Note: We no longer validate principal matches owner here because delegation
        # allows other principals (travel agents) to act on behalf of the owner.
        # The authz-api will check both spoofing (principal_id vs owner_id) and delegation.

        item = self._get_workflow_item_or_raise(
            workflow=workflow, item_id=workflow_item_id
        )
        decision_payload = self._call_authz_for_workflow(
            workflow=workflow,
            principal_user=principal_user,
            action="execute",
            item=item,
            dry_run=bool(dry_run),
        )

        decision = str(decision_payload.get("decision", "deny"))
        reason_codes = list(decision_payload.get("reason_codes", []))
        advice = list(decision_payload.get("advice", []))

        if decision != "allow":
            item["last_decision"] = decision
            item["last_reason_codes"] = reason_codes
            item["last_advice"] = advice
            raise PolicyDeniedError(
                f"Access denied by policy decision: decision={decision} reason_codes={reason_codes}",
                reason_codes=reason_codes,
                advice=advice,
            )

        if not dry_run:
            # Update status: planned -> booked, booked -> rebooked, anything else -> booked
            current_status = str(item.get("status", "planned")).lower()
            if current_status == "booked":
                item["status"] = "rebooked"
            else:
                item["status"] = "booked"

        item["last_decision"] = "allow"
        item["last_reason_codes"] = reason_codes
        item["last_advice"] = advice

        # For response, show current status
        response_status = item["status"] if not dry_run else "simulated"

        return {
            "status": response_status,
            "decision": "allow",
            "workflow_id": workflow_id,
            "item_id": workflow_item_id,
            "item_kind": str(item.get("kind", "unknown")),
            "reason_codes": reason_codes,
            "advice": advice,
        }

    def _get_workflow_or_raise(self, workflow_id: str) -> dict[str, Any]:
        # Fetch a workflow from memory
        # why: centralize errors
        # side effect: none.
        if workflow_id not in self._workflows:
            raise KeyError(f"Workflow not found: {workflow_id}")
        workflow = self._workflows[workflow_id]
        if not isinstance(workflow, dict):
            raise ValueError("Workflow store corrupted: expected object")
        return workflow

    def _get_workflow_item_or_raise(
        self, workflow: dict[str, Any], item_id: str
    ) -> dict[str, Any]:
        # Find a workflow item by id
        # why: protect against rogue item ids
        # side effect: none.
        items = workflow.get("items", [])
        if not isinstance(items, list):
            raise ValueError("Workflow store corrupted: items must be a list")
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("item_id", "")).strip() == item_id:
                return item
        raise KeyError(f"Workflow item not found: {item_id}")

    def _validate_principal_matches_owner(
        self, workflow: dict[str, Any], principal_sub: str
    ) -> None:
        # Prevent trivial principal spoofing in the demo
        # assumption: real systems bind principal_sub to token subject.
        owner_sub = str(workflow.get("owner_sub", "")).strip()
        if not owner_sub:
            raise ValueError("Workflow store corrupted: missing owner_sub")
        if principal_sub != owner_sub:
            raise PermissionError(
                f"Principal mismatch: principal_sub={principal_sub} is not owner_sub={owner_sub}"
            )

    def _call_authz_for_workflow(
        self,
        workflow: dict[str, Any] | None,
        principal_user: dict[str, Any],
        action: str = "read",
        user_token: str | None = None,
        workflow_domain: str | None = None,
        item: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        # Call AuthZ /v1/evaluate for workflow or workflow-item operations
        # Handles all actions: create, read, update, delete, execute
        # For create action, workflow can be None
        # For item-level actions, pass item parameter
        authz_base_url = require_non_empty_string(
            str(self._config.get("authz_base_url", "")), "authz_base_url"
        )
        domain = require_non_empty_string(str(self._config.get("domain", "")), "domain")

        # Determine workflow_id and domain from workflow or parameters
        if workflow:
            workflow_id = str(workflow.get("workflow_id", ""))
            effective_domain = workflow.get("domain") or workflow_domain or domain
            owner_sub = str(workflow.get("owner_sub", ""))
            owner_persona_title = workflow.get("owner_persona_title")  # Get persona title from workflow
            owner_persona_circle = workflow.get("owner_persona_circle")  # Get persona circle from workflow
            departure_date = workflow.get("departure_date")
        else:
            # For create action - no workflow yet
            workflow_id = ""
            effective_domain = workflow_domain or domain
            owner_sub = principal_user.get("id", "")
            owner_persona_title = principal_user.get("persona_title")  # Get persona title from principal
            owner_persona_circle = principal_user.get("persona_circle")  # Get persona circle from principal
            departure_date = None

        # Build resource properties
        resource_properties: dict[str, Any] = {
            "domain": effective_domain,
        }
        
        # Add workflow_id if available (not for create)
        if workflow_id:
            resource_properties["workflow_id"] = workflow_id

        # Add departure_date if available
        if departure_date:
            resource_properties["departure_date"] = departure_date
        
        # Add item-specific properties if this is an item-level operation
        if item:
            item_id = str(item.get("item_id", ""))
            item_kind = str(item.get("kind", "unknown"))
            resource_properties["workflow_item_id"] = item_id
            resource_properties["workflow_item_kind"] = item_kind
            
            # Extract planned_price amount (OPA policy expects EUR amount as a number)
            planned_price = item.get("planned_price")
            if isinstance(planned_price, dict):
                resource_properties["planned_price"] = float(planned_price.get("amount", 0))
            else:
                resource_properties["planned_price"] = 0
            
            # Add airline_risk_score if available in item
            airline_risk_score = item.get("airline_risk_score")
            if airline_risk_score is not None:
                resource_properties["airline_risk_score"] = airline_risk_score

        # Add owner to resource properties with explicit persona_title and persona_circle
        if owner_sub:
            owner_dict: dict[str, Any] = {"type": "user", "id": owner_sub}
            if owner_persona_title:
                owner_dict["persona_title"] = str(owner_persona_title)
            if owner_persona_circle:
                owner_dict["persona_circle"] = str(owner_persona_circle)
            resource_properties["owner"] = owner_dict

        url = build_url(authz_base_url, "/v1/evaluate")

        # AuthZEN: Build context with principal-user object
        context: dict[str, Any] = {
            "principal": principal_user,
            "policy_hint": effective_domain,  # Dynamic policy selection based on domain
        }

        # Use service identity from environment configuration
        service_id = SERVICE_ID
        # Always use service token for service-to-service authentication
        # User identity is passed in the context.principal field, not via bearer token
        token = security.get_service_token()

        # Subject is the service making the call
        # For agents, type is sufficient - no persona needed
        subject: dict[str, Any] = {
            "type": "agent",
            "id": service_id,
        }

        # Build resource (with or without id)
        # Resource type depends on whether we're operating on workflow or workflow_item
        resource_type = "workflow_item" if item else "workflow"
        resource_id = str(item.get("item_id", "")) if item else workflow_id
        
        resource: dict[str, Any] = {
            "type": resource_type,
            "properties": resource_properties,
        }
        if resource_id:
            resource["id"] = resource_id

        # Build options (include dry_run for item-level operations)
        options: dict[str, Any] = {"explain": True, "metrics": False}
        if item:
            options["dry_run"] = bool(dry_run)

        body: dict[str, Any] = {
            "subject": subject,
            "action": {"name": action},
            "resource": resource,
            "context": context,
            "options": options,
        }

        headers = {"Authorization": f"Bearer {token}"} if token else {}
        
        # Log warning if no service token is available
        if not token:
            print(f"WARNING: No service token available for authz API call. This may cause authorization failures.", flush=True)
        
        # Use centralized http_post_json for logging, caching and error handling
        return http_post_json(
            url=url,
            payload=body,
            headers=headers if headers else None,
        )
