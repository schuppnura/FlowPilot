from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from template_loader import load_trip_templates_from_directory
from utils import build_url, http_post_json, validate_non_empty_string


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
                items.append(
                    {
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
                )

        trip: Dict[str, Any] = {
            "trip_id": trip_id,
            "template_id": template_id,
            "owner_sub": owner_sub,
            "created_at": created_at,
            "items": items,
        }
        self._trips[trip_id] = trip

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
            trip_id=trip_id,
            item_id=item_id,
            item_kind=str(item.get("kind", "unknown")),
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

    def _call_authz_for_item(self, trip_id: str, item_id: str, item_kind: str, principal_sub: str, dry_run: bool) -> Dict[str, Any]:
        # Call AuthZ /v1/evaluate
        # why: authorization and ***REMOVED*** relationship checks live there
        # side effect: network I/O.
        authz_base_url = validate_non_empty_string(str(self._config.get("authz_base_url", "")), "authz_base_url")
        agent_sub = validate_non_empty_string(str(self._config.get("agent_sub", "")), "agent_sub")
        timeout_seconds = int(self._config.get("request_timeout_seconds", 10))
        domain = validate_non_empty_string(str(self._config.get("domain", "")), "domain")

        url = build_url(authz_base_url, "/v1/evaluate")
        body: Dict[str, Any] = {
            "subject": {"type": "agent", "id": agent_sub},
            "action": {"name": "book"},
            "resource": {
                "type": "workflow",
                "id": trip_id,
                "properties": {
                    "domain": domain,
                    "workflow_item_id": item_id,
                    "workflow_item_kind": item_kind,
                },
            },
            "context": {"principal": {"type": "user", "id": principal_sub}},
            "options": {"dry_run": bool(dry_run), "explain": True, "metrics": False},
        }

        return http_post_json(url=url, payload=body, timeouts=(timeout_seconds, timeout_seconds))
