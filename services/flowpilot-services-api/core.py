# FlowPilot Services API - Core Logic
#
# Domain backend for the travel demo. This is the system of record for workflow state
# and acts as the Policy Enforcement Point (PEP) for authorization decisions.
#
# Key responsibilities:
# - Workflow (trip) creation from templates
# - Itinerary item management and state tracking
# - Policy enforcement point (PEP) that delegates decisions to AuthZ API
# - Dry-run semantics for workflow execution
# - In-memory workflow storage (demo only)
#
# Domain-specific behavior: This service implements travel-specific workflows.
# The other domains (nursing, logistics) have different incarnations
# but all follow the same workflow PEP pattern.

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from template_loader import load_trip_templates_from_directory
from utils import build_url, http_post_json, validate_non_empty_string

# Token cache for service-to-service auth
_token_cache: Dict[str, Any] = {}


def get_service_token() -> Optional[str]:
    # Get service-to-service bearer token from Keycloak using client credentials grant
    # why: authenticate services-api when calling authz-api endpoints
    # when: called before making requests to authz-api (evaluate, graph writes)
    # caching: tokens are cached with 30s buffer before expiry to minimize Keycloak calls
    # returns: JWT access token string, or None if auth is disabled
    # side effect: network I/O to Keycloak, updates module-level token cache
    auth_enabled = os.environ.get("AUTH_ENABLED", "true").lower() == "true"
    if not auth_enabled:
        return None
    
    # Check token cache
    if "token" in _token_cache and "expires_at" in _token_cache:
        if time.time() < _token_cache["expires_at"] - 30:  # 30s buffer
            return _token_cache["token"]
    
    # Get new token from Keycloak
    keycloak_url = os.environ.get("KEYCLOAK_URL", "https://keycloak:8443")
    realm = os.environ.get("KEYCLOAK_REALM", "flowpilot")
    client_id = os.environ.get("KEYCLOAK_CLIENT_ID", "flowpilot-agent")
    client_secret = os.environ.get("KEYCLOAK_CLIENT_SECRET", "")
    verify_ssl = os.environ.get("KEYCLOAK_VERIFY_SSL", "false").lower() == "true"
    
    token_url = f"{keycloak_url}/realms/{realm}/protocol/openid-connect/token"
    
    try:
        response = requests.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=5,
            verify=verify_ssl,
        )
        
        if response.status_code == 200:
            token_data = response.json()
            _token_cache["token"] = token_data["access_token"]
            _token_cache["expires_at"] = time.time() + token_data.get("expires_in", 300)
            return _token_cache["token"]
    except Exception:
        pass  # Fall through to return None
    
    return None


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
        self._trips: Dict[str, Dict[str, Any]] = {}

    def load_templates(self) -> None:
        # Load templates from directory
        # assumptions: directory exists and contains valid JSON
        # side effect: filesystem reads.
        domain = validate_non_empty_string(str(self._config.get("domain", "")), "domain")
        template_directory = validate_non_empty_string(str(self._config.get("template_directory", "")), "template_directory")
        self._templates = load_trip_templates_from_directory(template_directory=template_directory, domain=domain)

    def get_template_count(self) -> int:
        # Return number of loaded templates
        # why: health/debug
        # side effect: none.
        return len(self._templates)

    def get_trip_count(self) -> int:
        # Return number of trips in memory
        # why: health/debug
        # side effect: none.
        return len(self._trips)

    def list_trip_templates(self) -> List[Dict[str, Any]]:
        # Return minimal template metadata
        # why: client selection without leaking full template details
        # side effect: none.
        templates: List[Dict[str, Any]] = []
        for template_id, template in self._templates.items():
            templates.append(
                {
                    "template_id": template_id,
                    "name": str(template.get("name", template_id)),
                    "domain": str(template.get("domain", self._config.get("domain", "flowpilot"))),
                    "item_count": len(template.get("items", [])) if isinstance(template.get("items", []), list) else 0,
                }
            )
        templates.sort(key=lambda entry: str(entry.get("template_id", "")))
        return templates

    def create_trip_from_template(self, template_id: str, owner_sub: str) -> Dict[str, Any]:
        # Create a trip and itinerary items from a template
        # side effect: stores a new trip in memory.
        template_id = validate_non_empty_string(template_id, "template_id")
        owner_sub = validate_non_empty_string(owner_sub, "owner_sub")

        if template_id not in self._templates:
            raise KeyError(f"Template not found: {template_id}")

        template = self._templates[template_id]
        trip_id = "t_" + uuid.uuid4().hex[:8]
        created_at = get_utc_now_iso()

        items: List[Dict[str, Any]] = []
        raw_items = template.get("items", [])
        if isinstance(raw_items, list):
            for raw in raw_items:
                if not isinstance(raw, dict):
                    continue
                item_id = "i_" + uuid.uuid4().hex[:8]
                kind = str(raw.get("kind", "unknown"))
                item_dict: Dict[str, Any] = {
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
                # Preserve airline_risk_score and other item-level attributes for auto-book policy
                if "airline_risk_score" in raw:
                    item_dict["airline_risk_score"] = raw["airline_risk_score"]
                if "type" in raw:
                    item_dict["type"] = raw["type"]
                items.append(item_dict)

        trip: Dict[str, Any] = {
            "trip_id": trip_id,
            "template_id": template_id,
            "owner_sub": owner_sub,
            "created_at": created_at,
            "items": items,
        }
        # Preserve trip-level attributes for auto-book policy (e.g., departure_date)
        if "departure_date" in template:
            trip["departure_date"] = template["departure_date"]
        self._trips[trip_id] = trip

        # Create workflow and workflow_item objects in ***REMOVED*** via AuthZ API
        try:
            self._create_workflow_graph(trip_id=trip_id, owner_sub=owner_sub, template_name=str(template.get("name", template_id)))
            for item in items:
                self._create_workflow_item_graph(
                    workflow_item_id=str(item["item_id"]),
                    workflow_id=trip_id,
                    item_title=str(item.get("title", "")),
                    item_kind=str(item.get("kind", "unknown")),
                )
        except Exception as graph_error:
            # Log but don't fail the trip creation if graph write fails
            print(f"Warning: Failed to create ***REMOVED*** graph for trip {trip_id}: {graph_error}")

        return {"trip_id": trip_id, "owner_sub": owner_sub, "created_at": created_at, "item_count": len(items)}

    def get_trip(self, trip_id: str) -> Dict[str, Any]:
        # Return a trip record
        # assumptions: trip exists
        # side effect: none.
        trip_id = validate_non_empty_string(trip_id, "trip_id")
        if trip_id not in self._trips:
            raise KeyError(f"Trip not found: {trip_id}")
        trip = self._trips[trip_id]
        return {
            "trip_id": str(trip.get("trip_id")),
            "template_id": str(trip.get("template_id")),
            "owner_sub": str(trip.get("owner_sub")),
            "created_at": str(trip.get("created_at")),
            "item_count": len(trip.get("items", [])) if isinstance(trip.get("items", []), list) else 0,
        }

    def get_itinerary(self, trip_id: str) -> Dict[str, Any]:
        # Return itinerary items for agent-runner
        # assumptions: trip exists
        # side effect: none.
        trip_id = validate_non_empty_string(trip_id, "trip_id")
        if trip_id not in self._trips:
            raise KeyError(f"Trip not found: {trip_id}")

        trip = self._trips[trip_id]
        items_out: List[Dict[str, Any]] = []
        for item in trip.get("items", []):
            if not isinstance(item, dict):
                continue
            items_out.append(
                {
                    "item_id": str(item.get("item_id")),
                    "kind": str(item.get("kind", "unknown")),
                    "title": str(item.get("title", "")),
                    "status": str(item.get("status", "unknown")),
                }
            )

        return {"trip_id": trip_id, "items": items_out}

    def execute_itinerary_item(self, trip_id: str, item_id: str, principal_sub: str, dry_run: bool) -> Dict[str, Any]:
        # Execute an itinerary item with AuthZ decision
        # why: PEP responsibility
        # side effects: network I/O + optional state mutation.
        trip_id = validate_non_empty_string(trip_id, "trip_id")
        item_id = validate_non_empty_string(item_id, "item_id")
        principal_sub = validate_non_empty_string(principal_sub, "principal_sub")

        trip = self._get_trip_or_raise(trip_id=trip_id)
        self._validate_principal_matches_owner(trip=trip, principal_sub=principal_sub)

        item = self._get_trip_item_or_raise(trip=trip, item_id=item_id)
        decision_payload = self._call_authz_for_item(
            trip=trip,
            item=item,
            principal_sub=principal_sub,
            dry_run=bool(dry_run),
        )

        decision = str(decision_payload.get("decision", "deny"))
        reason_codes = list(decision_payload.get("reason_codes", []))
        advice = list(decision_payload.get("advice", []))

        if decision != "allow":
            item["last_decision"] = decision
            item["last_reason_codes"] = reason_codes
            item["last_advice"] = advice
            raise PermissionError(f"Access denied by policy decision: decision={decision} reason_codes={reason_codes}")

        if not dry_run:
            item["status"] = "executed"
        item["last_decision"] = "allow"
        item["last_reason_codes"] = reason_codes
        item["last_advice"] = advice

        return {
            "status": "simulated" if dry_run else "executed",
            "decision": "allow",
            "trip_id": trip_id,
            "item_id": item_id,
            "item_kind": str(item.get("kind", "unknown")),
            "reason_codes": reason_codes,
            "advice": advice,
        }

    def _get_trip_or_raise(self, trip_id: str) -> Dict[str, Any]:
        # Fetch a trip from memory
        # why: centralize errors
        # side effect: none.
        if trip_id not in self._trips:
            raise KeyError(f"Trip not found: {trip_id}")
        trip = self._trips[trip_id]
        if not isinstance(trip, dict):
            raise ValueError("Trip store corrupted: expected object")
        return trip

    def _get_trip_item_or_raise(self, trip: Dict[str, Any], item_id: str) -> Dict[str, Any]:
        # Find a trip item by id
        # why: protect against rogue item ids
        # side effect: none.
        items = trip.get("items", [])
        if not isinstance(items, list):
            raise ValueError("Trip store corrupted: items must be a list")
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("item_id", "")).strip() == item_id:
                return item
        raise KeyError(f"Itinerary item not found: {item_id}")

    def _validate_principal_matches_owner(self, trip: Dict[str, Any], principal_sub: str) -> None:
        # Prevent trivial principal spoofing in the demo
        # assumption: real systems bind principal_sub to token subject.
        owner_sub = str(trip.get("owner_sub", "")).strip()
        if not owner_sub:
            raise ValueError("Trip store corrupted: missing owner_sub")
        if principal_sub != owner_sub:
            raise PermissionError(f"Principal mismatch: principal_sub={principal_sub} is not owner_sub={owner_sub}")

    def _call_authz_for_item(self, trip: Dict[str, Any], item: Dict[str, Any], principal_sub: str, dry_run: bool) -> Dict[str, Any]:
        # Call AuthZ /v1/evaluate for this itinerary item.
        # why: PEP delegates to AuthZ API for ReBAC (***REMOVED***) and, for action 'auto-book', ABAC checks.
        # details: we include attributes (total cost, departure_date, airline_risk_score) in resource.properties so the
        #          AuthZ API can evaluate the auto-book policy. When action='auto-book', the PDP façade enforces
        #          consent/cost/advance/risk constraints after delegation is verified by ***REMOVED***.
        # side effect: network I/O.
        authz_base_url = validate_non_empty_string(str(self._config.get("authz_base_url", "")), "authz_base_url")
        agent_sub = validate_non_empty_string(str(self._config.get("agent_sub", "")), "agent_sub")
        timeout_seconds = int(self._config.get("request_timeout_seconds", 10))
        domain = validate_non_empty_string(str(self._config.get("domain", "")), "domain")

        trip_id = str(trip.get("trip_id", ""))
        item_id = str(item.get("item_id", ""))
        item_kind = str(item.get("kind", "unknown"))

        # Extract attributes for auto-book policy evaluation
        resource_properties: Dict[str, Any] = {
            "domain": domain,
            "workflow_item_id": item_id,
            "workflow_item_kind": item_kind,
        }
        
        # Add departure_date from trip-level (if present)
        if "departure_date" in trip:
            resource_properties["departure_date"] = trip["departure_date"]
        
        # Add airline_risk_score from item-level (if present)
        if "airline_risk_score" in item:
            resource_properties["airline_risk_score"] = item["airline_risk_score"]
        
        # Calculate total trip cost from all items' planned_price
        # Note: This is the total cost across ALL items in the trip (hotels, flights, etc.)
        #       Used by auto-book policy to enforce cost limits
        total_cost = 0.0
        for trip_item in trip.get("items", []):
            if isinstance(trip_item, dict):
                planned_price = trip_item.get("planned_price")
                if isinstance(planned_price, dict):
                    amount = planned_price.get("amount")
                    if isinstance(amount, (int, float)):
                        total_cost += float(amount)
        resource_properties["planned_price"] = total_cost

        url = build_url(authz_base_url, "/v1/evaluate")
        body: Dict[str, Any] = {
            "subject": {"type": "agent", "id": agent_sub},
            "action": {"name": "auto-book"},
            "resource": {
                "type": "workflow",
                "id": trip_id,
                "properties": resource_properties,
            },
            "context": {"principal": {"type": "user", "id": principal_sub}},
            "options": {"dry_run": bool(dry_run), "explain": True, "metrics": False},
        }

        # Get service token for authentication
        token = get_service_token()
        headers = {"Authorization": f"Bearer {token}"} if token else None
        
        response = requests.post(url, json=body, timeout=timeout_seconds, headers=headers, verify=False)
        if response.status_code not in (200, 201):
            raise RuntimeError(f"AuthZ evaluate failed: HTTP {response.status_code}: {response.text}")
        return response.json()

    def _create_workflow_graph(self, trip_id: str, owner_sub: str, template_name: str) -> None:
        # Create workflow object and owner relation in ***REMOVED*** via AuthZ API graph write endpoint
        # why: establish workflow ownership for ReBAC authorization checks during workflow execution
        # when: called immediately after creating workflow in memory (in create_trip_from_template)
        # authorization: uses service-to-service token from Keycloak client credentials
        # endpoint: POST /v1/graph/workflows on authz-api
        # side effect: network I/O to authz-api, which creates objects/relations in ***REMOVED***
        # raises: RuntimeError if authz-api returns non-2xx (logged but doesn't fail workflow creation)
        authz_base_url = validate_non_empty_string(str(self._config.get("authz_base_url", "")), "authz_base_url")
        timeout_seconds = int(self._config.get("request_timeout_seconds", 10))
        domain = validate_non_empty_string(str(self._config.get("domain", "")), "domain")

        url = build_url(authz_base_url, "/v1/graph/workflows")
        body: Dict[str, Any] = {
            "workflow_id": trip_id,
            "owner_sub": owner_sub,
            "display_name": template_name,
            "properties": {"domain": domain},
        }
        
        # Get service token for authentication
        token = get_service_token()
        headers = {"Authorization": f"Bearer {token}"} if token else None
        
        response = requests.post(url, json=body, timeout=timeout_seconds, headers=headers, verify=False)
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Failed to create workflow graph: HTTP {response.status_code}: {response.text}")

    def _create_workflow_item_graph(self, workflow_item_id: str, workflow_id: str, item_title: str, item_kind: str) -> None:
        # Create workflow_item object and workflow relation in ***REMOVED*** via AuthZ API graph write endpoint
        # why: link items to parent workflow for permission inheritance via ReBAC
        # when: called for each workflow item during workflow creation
        # authorization: uses service-to-service token from Keycloak client credentials
        # endpoint: POST /v1/graph/workflow-items on authz-api
        # permission chain: workflow_item.can_execute resolves via workflow relation to workflow.can_execute
        # side effect: network I/O to authz-api, which creates objects/relations in ***REMOVED***
        # raises: RuntimeError if authz-api returns non-2xx (logged but doesn't fail workflow creation)
        authz_base_url = validate_non_empty_string(str(self._config.get("authz_base_url", "")), "authz_base_url")
        timeout_seconds = int(self._config.get("request_timeout_seconds", 10))

        url = build_url(authz_base_url, "/v1/graph/workflow-items")
        body: Dict[str, Any] = {
            "workflow_item_id": workflow_item_id,
            "workflow_id": workflow_id,
            "display_name": item_title,
            "properties": {"kind": item_kind},
        }
        
        # Get service token for authentication
        token = get_service_token()
        headers = {"Authorization": f"Bearer {token}"} if token else None
        
        response = requests.post(url, json=body, timeout=timeout_seconds, headers=headers, verify=False)
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Failed to create workflow_item graph: HTTP {response.status_code}: {response.text}")
