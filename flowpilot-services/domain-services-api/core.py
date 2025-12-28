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

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

import security
from template_loader import load_workflow_templates_from_directory
from utils import build_url, require_non_empty_string


class PolicyDeniedError(PermissionError):
    # Exception raised when authorization policy denies access, carrying reason codes
    def __init__(
        self, message: str, reason_codes: List[str], advice: List[Dict[str, Any]]
    ):
        super().__init__(message)
        self.reason_codes = reason_codes
        self.advice = advice


def get_utc_now_iso() -> str:
    # Return a stable UTC timestamp string
    # why: deterministic timestamps in responses
    # side effect: reads system time.
    return datetime.now(timezone.utc).isoformat()


class FlowPilotService:
    def __init__(self, config: Dict[str, Any]) -> None:
        # Initialize service state
        # why: keep in-memory store and config together
        # side effect: none.
        self._config = dict(config)
        self._templates: Dict[str, Dict[str, Any]] = {}
        self._workflows: Dict[str, Dict[str, Any]] = {}

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

    def list_workflows(self) -> List[Dict[str, Any]]:
        # Return minimal workflow metadata for all workflows
        # why: allow clients to select an existing workflow
        # side effect: none.
        workflows: List[Dict[str, Any]] = []
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
                    "item_count": len(workflow.get("items", []))
                    if isinstance(workflow.get("items", []), list)
                    else 0,
                }
            )
        workflows.sort(
            key=lambda w: str(w.get("created_at", "")), reverse=True
        )  # Most recent first
        return workflows

    def list_workflow_templates(self) -> List[Dict[str, Any]]:
        # Return minimal template metadata
        # why: client selection without leaking full template details
        # side effect: none.
        templates: List[Dict[str, Any]] = []
        for template_id, template in self._templates.items():
            templates.append(
                {
                    "template_id": template_id,
                    "name": str(template.get("name", template_id)),
                    "domain": str(
                        template.get("domain", self._config.get("domain", "flowpilot"))
                    ),
                    "item_count": len(template.get("items", []))
                    if isinstance(template.get("items", []), list)
                    else 0,
                }
            )
        templates.sort(key=lambda entry: str(entry.get("template_id", "")))
        return templates

    def create_workflow_from_template(
        self,
        template_id: str,
        owner_sub: str,
        start_date: str,
        persona: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Create a workflow and itinerary items from a template
        # side effect: stores a new workflow in memory.
        template_id = require_non_empty_string(template_id, "template_id")
        owner_sub = require_non_empty_string(owner_sub, "owner_sub")
        # Note: start_date parameter is accepted but not used (for API compatibility)

        if template_id not in self._templates:
            raise KeyError(f"Template not found: {template_id}")

        template = self._templates[template_id]
        workflow_id = "w_" + uuid.uuid4().hex[:8]
        created_at = get_utc_now_iso()

        items: List[Dict[str, Any]] = []
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
                    "airline_risk_score": raw.get("airline_risk_score"),
                    "status": "planned",
                    "last_decision": None,
                    "last_reason_codes": [],
                    "last_advice": [],
                }
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

        workflow: Dict[str, Any] = {
            "workflow_id": workflow_id,
            "template_id": template_id,
            "owner_sub": owner_sub,
            "owner_persona": persona,  # Store the persona used when creating the workflow
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

    def check_read_authorization(
        self, workflow_id: str, user_sub: str, user_persona: Optional[str] = None
    ) -> None:
        # Check if user is authorized to read the workflow
        # Raises PolicyDeniedError if access is denied
        workflow = self._get_workflow_or_raise(workflow_id)
        owner_sub = str(workflow.get("owner_sub", ""))
        
        # Debug logging
        print(f"[check_read_authorization] workflow_id={workflow_id}, user_sub={user_sub}, owner_sub={owner_sub}, user_persona={user_persona}", flush=True)
        
        # Owner can always read their own workflows
        if user_sub == owner_sub:
            print(f"[check_read_authorization] Owner match - allowing access", flush=True)
            return
        
        # Non-owner must have authorization
        # Build principal_user object (no claims - only id and persona)
        principal_user: Dict[str, Any] = {
            "type": "user",
            "id": user_sub,
        }
        if user_persona:
            principal_user["persona"] = user_persona
        
        # Call authz-api with action="read"
        decision_payload = self._call_authz_for_workflow(
            workflow=workflow,
            principal_user=principal_user,
            action="read",
        )
        
        decision = str(decision_payload.get("decision", "deny"))
        reason_codes = list(decision_payload.get("reason_codes", []))
        advice = list(decision_payload.get("advice", []))
        
        if decision != "allow":
            raise PolicyDeniedError(
                f"Read access denied: decision={decision} reason_codes={reason_codes}",
                reason_codes=reason_codes,
                advice=advice,
            )

    def get_workflow(self, workflow_id: str) -> Dict[str, Any]:
        # Return a workflow record
        # assumptions: workflow exists
        # side effect: none.
        workflow_id = require_non_empty_string(workflow_id, "workflow_id")
        if workflow_id not in self._workflows:
            raise KeyError(f"Workflow not found: {workflow_id}")
        workflow = self._workflows[workflow_id]
        return {
            "workflow_id": str(workflow.get("workflow_id")),
            "template_id": str(workflow.get("template_id")),
            "owner_sub": str(workflow.get("owner_sub")),
            "created_at": str(workflow.get("created_at")),
            "item_count": len(workflow.get("items", []))
            if isinstance(workflow.get("items", []), list)
            else 0,
        }

    def get_workflow_items(self, workflow_id: str) -> Dict[str, Any]:
        # Return workflow items for agent-runner
        # assumptions: workflow exists
        # side effect: none.
        workflow_id = require_non_empty_string(workflow_id, "workflow_id")
        if workflow_id not in self._workflows:
            raise KeyError(f"Workflow not found: {workflow_id}")

        workflow = self._workflows[workflow_id]
        items_out: List[Dict[str, Any]] = []
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
        principal_user: Dict[str, Any],
        dry_run: bool,
    ) -> Dict[str, Any]:
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
        decision_payload = self._call_authz_for_item(
            workflow=workflow,
            item=item,
            principal_user=principal_user,
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
            item["status"] = "executed"
        item["last_decision"] = "allow"
        item["last_reason_codes"] = reason_codes
        item["last_advice"] = advice

        return {
            "status": "simulated" if dry_run else "executed",
            "decision": "allow",
            "workflow_id": workflow_id,
            "item_id": workflow_item_id,
            "item_kind": str(item.get("kind", "unknown")),
            "reason_codes": reason_codes,
            "advice": advice,
        }

    def _get_workflow_or_raise(self, workflow_id: str) -> Dict[str, Any]:
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
        self, workflow: Dict[str, Any], item_id: str
    ) -> Dict[str, Any]:
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
        self, workflow: Dict[str, Any], principal_sub: str
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

    def _call_authz_for_item(
        self,
        workflow: Dict[str, Any],
        item: Dict[str, Any],
        principal_user: Dict[str, Any],
        dry_run: bool,
        action: str = "execute",
    ) -> Dict[str, Any]:
        # Call AuthZ /v1/evaluate
        # why: authorization and ***REMOVED*** relationship checks live there
        # side effect: network I/O.
        # AuthZEN: Pass principal_user object instead of principal_sub and user_token
        authz_base_url = require_non_empty_string(
            str(self._config.get("authz_base_url", "")), "authz_base_url"
        )
        agent_sub = require_non_empty_string(
            str(self._config.get("agent_sub", "")), "agent_sub"
        )
        timeout_seconds = int(self._config.get("request_timeout_seconds", 10))
        domain = require_non_empty_string(str(self._config.get("domain", "")), "domain")

        workflow_id = str(workflow.get("workflow_id", ""))
        item_id = str(item.get("item_id", ""))
        item_kind = str(item.get("kind", "unknown"))

        # Extract planned_price amount (OPA policy expects EUR amount as a number)
        planned_price_eur = 0
        planned_price = item.get("planned_price")
        if isinstance(planned_price, dict):
            planned_price_eur = float(planned_price.get("amount", 0))

        # Build resource properties for OPA policy
        resource_properties: Dict[str, Any] = {
            "domain": domain,
            "workflow_id": workflow_id,
            "workflow_item_id": item_id,
            "workflow_item_kind": item_kind,
            "planned_price": planned_price_eur,
        }

        # Add departure_date if available in workflow
        departure_date = workflow.get("departure_date")
        if departure_date:
            resource_properties["departure_date"] = departure_date

        # Add airline_risk_score if available in item
        airline_risk_score = item.get("airline_risk_score")
        if airline_risk_score is not None:
            resource_properties["airline_risk_score"] = airline_risk_score

        url = build_url(authz_base_url, "/v1/evaluate")

        # AuthZEN: Build context with principal-user object (not token)
        context: Dict[str, Any] = {"principal": principal_user}

        # Get service token for authentication
        token = security.get_service_token()
        if not token:
            raise RuntimeError("Service token not available - cannot call authz-api")

        # Decode service token to get sub or azp for the agent subject
        try:
            service_claims = security.verify_token_string(token)
            service_id = (
                service_claims.get("sub") or service_claims.get("azp") or agent_sub
            )
        except Exception:
            # Fallback to agent_sub if token decode fails
            service_id = agent_sub

        # Subject is always the agent (service) making the call to authz-api
        # This is a service-to-service call, so subject identifies the calling service (ai-agent-api)
        # The user information (with persona) goes in context.principal
        subject: Dict[str, Any] = {"type": "agent", "id": service_id}

        # Add owner to resource properties (with persona from workflow creation)
        owner_sub = str(workflow.get("owner_sub", ""))
        owner_persona = workflow.get("owner_persona")
        if owner_sub:
            owner_dict: Dict[str, Any] = {"type": "user", "id": owner_sub}
            if owner_persona:
                owner_dict["persona"] = str(owner_persona)
            resource_properties["owner"] = owner_dict

        body: Dict[str, Any] = {
            "subject": subject,
            "action": {"name": action},
            "resource": {
                "type": "workflow_item",
                "id": item_id,
                "properties": resource_properties,
            },
            "context": context,
            "options": {"dry_run": bool(dry_run), "explain": True, "metrics": False},
        }

        headers = {"Authorization": f"Bearer {token}"}
        response = requests.post(
            url, json=body, timeout=timeout_seconds, headers=headers, verify=False
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"AuthZ evaluate failed: HTTP {response.status_code}: {response.text}"
            )
        return response.json()

    def _call_authz_for_workflow(
        self,
        workflow: Dict[str, Any],
        principal_user: Dict[str, Any],
        action: str = "read",
    ) -> Dict[str, Any]:
        # Call AuthZ /v1/evaluate for workflow-level operations (e.g., read)
        # Similar to _call_authz_for_item but for workflow resource type
        authz_base_url = require_non_empty_string(
            str(self._config.get("authz_base_url", "")), "authz_base_url"
        )
        agent_sub = require_non_empty_string(
            str(self._config.get("agent_sub", "")), "agent_sub"
        )
        timeout_seconds = int(self._config.get("request_timeout_seconds", 10))
        domain = require_non_empty_string(str(self._config.get("domain", "")), "domain")

        workflow_id = str(workflow.get("workflow_id", ""))

        # Build resource properties
        resource_properties: Dict[str, Any] = {
            "domain": domain,
            "workflow_id": workflow_id,
        }

        # Add departure_date if available
        departure_date = workflow.get("departure_date")
        if departure_date:
            resource_properties["departure_date"] = departure_date

        url = build_url(authz_base_url, "/v1/evaluate")

        # AuthZEN: Build context with principal-user object
        context: Dict[str, Any] = {"principal": principal_user}

        # Get service token for authentication
        token = security.get_service_token()
        if not token:
            raise RuntimeError("Service token not available - cannot call authz-api")

        # Decode service token to get sub or azp for the subject
        try:
            service_claims = security.verify_token_string(token)
            service_id = (
                service_claims.get("sub") or service_claims.get("azp") or agent_sub
            )
        except Exception:
            service_id = agent_sub

        # Subject is the service making the call
        subject: Dict[str, Any] = {"type": "agent", "id": service_id}

        # Add owner to resource properties
        owner_sub = str(workflow.get("owner_sub", ""))
        owner_persona = workflow.get("owner_persona")
        if owner_sub:
            owner_dict: Dict[str, Any] = {"type": "user", "id": owner_sub}
            if owner_persona:
                owner_dict["persona"] = str(owner_persona)
            resource_properties["owner"] = owner_dict

        body: Dict[str, Any] = {
            "subject": subject,
            "action": {"name": action},
            "resource": {
                "type": "workflow",
                "id": workflow_id,
                "properties": resource_properties,
            },
            "context": context,
            "options": {"explain": True, "metrics": False},
        }

        headers = {"Authorization": f"Bearer {token}"}
        response = requests.post(
            url, json=body, timeout=timeout_seconds, headers=headers, verify=False
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"AuthZ evaluate failed: HTTP {response.status_code}: {response.text}"
            )
        return response.json()

