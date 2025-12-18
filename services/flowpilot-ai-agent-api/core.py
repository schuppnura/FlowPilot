# FlowPilot AI Agent API - Core Logic
#
# Domain-agnostic workflow execution loop that iterates workflow items against domain APIs
# and aggregates outcomes. This agent runner executes workflow items item-by-item to produce
# mixed allow/deny outcomes in a single run.
#
# Key responsibilities:
# - List workflow items from domain backend
# - Execute workflow items via domain endpoints
# - Parse and classify authorization decisions (allow/deny)
# - Distinguish policy denials (403) from execution errors
# - Aggregate execution results with reason codes and advice
# - Service-to-service authentication via Keycloak client credentials

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from utils import build_url, http_get_json, validate_non_empty_string, build_timeouts

# Token cache for service-to-service auth
_token_cache: dict[str, Any] = {}


@dataclass(frozen=True)
class WorkflowItem:
    workflow_item_id: str
    kind: str
    raw: Dict[str, Any]


def get_service_token() -> str | None:
    # Get service-to-service bearer token from Keycloak.
    # Check if auth is enabled
    auth_enabled = os.environ.get("AUTH_ENABLED", "true").lower() == "true"
    if not auth_enabled:
        return None
    
    # Check token cache
    if "token" in _token_cache and "expires_at" in _token_cache:
        import time
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
            import time
            _token_cache["token"] = token_data["access_token"]
            _token_cache["expires_at"] = time.time() + token_data.get("expires_in", 300)
            return _token_cache["token"]
    except Exception:
        pass  # Fall through to return None
    
    return None


def normalize_workflow_id(workflow_id: Optional[str], workflow_id: Optional[str]) -> str:
    # Normalize workflow_id with legacy workflow_id fallback
    # why: keep older clients working without branching logic.
    if workflow_id and isinstance(workflow_id, str) and workflow_id.strip():
        return workflow_id.strip()
    if workflow_id and isinstance(workflow_id, str) and workflow_id.strip():
        return workflow_id.strip()
    raise ValueError("Missing workflow_id (or legacy workflow_id)")


def list_workflow_items(config: Dict[str, Any], workflow_id: str) -> List[WorkflowItem]:
    # List workflow items from the workflow service
    # assumption: response contains an 'items' list of dicts.
    validate_non_empty_string(workflow_id, "workflow_id")

    base_url = validate_non_empty_string(str(config.get("workflow_base_url", "")), "workflow_base_url")
    template = validate_non_empty_string(str(config.get("workflow_items_path_template", "")), "workflow_items_path_template")
    timeout_seconds = int(config.get("request_timeout_seconds", 10))

    url = build_url(base_url, template.format(workflow_id=workflow_id))
    
    headers = {}
    token = get_service_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    payload = http_get_json(url=url, timeout_seconds=timeout_seconds, headers=headers if headers else None)

    items_raw = payload.get("items", [])
    if not isinstance(items_raw, list):
        raise ValueError("Workflow items response malformed: items must be a list")

    items: List[WorkflowItem] = []
    for item in items_raw:
        if not isinstance(item, dict):
            continue
        item_id = item.get("item_id") or item.get("workflow_item_id") or item.get("itinerary_item_id")
        kind = item.get("kind") or "unknown"
        if isinstance(item_id, str) and item_id.strip():
            items.append(WorkflowItem(workflow_item_id=item_id.strip(), kind=str(kind), raw=item))

    return items


def parse_policy_deny_from_body(response_text: str) -> tuple[list[str], str]:
    # Parse deny reason codes from FlowPilot/AuthZ error bodies
    # why: map 403 policy denials to a clean agent-runner deny outcome
    # assumptions: body may be JSON with {"detail": "..."} or plain text
    # side effects: none.
    reason_codes: list[str] = []
    message: str = response_text.strip()

    try:
        parsed = json.loads(response_text)
        if isinstance(parsed, dict):
            detail = parsed.get("detail")
            if isinstance(detail, str) and detail.strip() != "":
                message = detail.strip()
    except Exception:
        pass

    if "reason_codes" in message:
        start = message.find("reason_codes=")
        if start >= 0:
            fragment = message[start:]
            left = fragment.find("[")
            right = fragment.find("]")
            if left >= 0 and right > left:
                content = fragment[left + 1 : right]
                reason_codes = [part.strip().strip("'\"") for part in content.split(",") if part.strip() != ""]

    if not reason_codes:
        if "***REMOVED***.deny" in message:
            reason_codes = ["***REMOVED***.deny"]

    return reason_codes, message


def post_execute_workflow_item(
    url: str,
    payload: dict[str, Any],
    timeouts: tuple[float, float],
) -> tuple[int, dict[str, Any] | None, str]:
    # Call the domain execute endpoint and return status + parsed JSON when possible
    # why: distinguish policy deny (403) from execution errors
    # assumptions: JSON body on success and often on failure
    # side effects: network I/O.
    headers = {}
    token = get_service_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    response = requests.post(url, json=payload, timeout=timeouts, headers=headers if headers else None)
    response_text = response.text or ""

    parsed_json: dict[str, Any] | None = None
    try:
        parsed = response.json()
        if isinstance(parsed, dict):
            parsed_json = parsed
    except Exception:
        parsed_json = None

    return response.status_code, parsed_json, response_text


def execute_workflow_item(
    config: Dict[str, Any],
    workflow_id: str,
    workflow_item_id: str,
    principal_sub: str,
    dry_run: bool,
) -> Dict[str, Any]:
    # Execute a single workflow item via the domain service and classify policy denies (HTTP 403) as completed results
    # why: denies are valid authorization outcomes and must not be treated as execution failures
    # assumptions: domain service returns 2xx on allow, 403 on deny, and other 4xx/5xx on true failures
    # side effects: network I/O.
    validate_non_empty_string(workflow_id, "workflow_id")
    validate_non_empty_string(workflow_item_id, "workflow_item_id")
    validate_non_empty_string(principal_sub, "principal_sub")

    base_url = validate_non_empty_string(str(config.get("workflow_base_url", "")), "workflow_base_url")
    template = validate_non_empty_string(
        str(config.get("workflow_item_execute_path_template", "")),
        "workflow_item_execute_path_template",
    )

    timeout_seconds = int(config.get("request_timeout_seconds", 10))
    timeouts = build_timeouts(connect_seconds=timeout_seconds)

    url = build_url(base_url, template.format(workflow_id=workflow_id, workflow_item_id=workflow_item_id))
    payload: Dict[str, Any] = {"principal_sub": principal_sub, "dry_run": bool(dry_run)}

    status_code, response_json, response_text = post_execute_workflow_item(url=url, payload=payload, timeouts=timeouts)

    if 200 <= status_code < 300:
        return {
            "http_status": status_code,
            "status": "completed",
            "outcome": "allow",
            "reason_codes": [],
            "advice": [],
            "response": response_json,
        }

    if status_code == 403:
        reason_codes, message = parse_policy_deny_from_body(response_text)
        return {
            "http_status": status_code,
            "status": "completed",
            "outcome": "deny",
            "reason_codes": reason_codes,
            "advice": [{"type": "deny", "message": message}],
            "response": response_json,
        }

    return {
        "http_status": status_code,
        "status": "error",
        "outcome": "deny",
        "reason_codes": ["agent_runner.item_execution_failed"],
        "advice": [
            {
                "type": "error",
                "message": f"HTTP POST non-2xx: url={url} http={status_code} body={response_text}",
            }
        ],
        "response": response_json,
    }


def execute_workflow_run(config: Dict[str, Any], workflow_id: str, principal_sub: str, dry_run: bool) -> Dict[str, Any]:
    # Execute a workflow by iterating items and delegating execution to domain endpoints,
    # normalizing each item result into a stable schema
    # why: the UI expects consistent status/decision fields even for denies
    # assumptions: execute_workflow_item returns {status, outcome, reason_codes, advice}
    # and may raise ValueError for invalid inputs
    # side effects: network I/O.
    validate_non_empty_string(workflow_id, "workflow_id")
    validate_non_empty_string(principal_sub, "principal_sub")

    run_id = "wr_" + uuid.uuid4().hex[:10]
    items = list_workflow_items(config=config, workflow_id=workflow_id)

    results: List[Dict[str, Any]] = []
    for item in items:
        try:
            response = execute_workflow_item(
                config=config,
                workflow_id=workflow_id,
                workflow_item_id=item.workflow_item_id,
                principal_sub=principal_sub,
                dry_run=dry_run,
            )

            status = str(response.get("status", "error"))
            decision = str(response.get("outcome", response.get("decision", "unknown")))
            reason_codes = list(response.get("reason_codes", []) or [])
            advice = list(response.get("advice", []) or [])

            results.append(
                {
                    "workflow_item_id": item.workflow_item_id,
                    "kind": item.kind,
                    "status": status,
                    "decision": decision,
                    "reason_codes": reason_codes,
                    "advice": advice,
                }
            )
        except ValueError as exception:
            results.append(
                {
                    "workflow_item_id": item.workflow_item_id,
                    "kind": item.kind,
                    "status": "error",
                    "decision": "deny",
                    "reason_codes": ["agent_runner.item_execution_failed"],
                    "advice": [{"type": "error", "message": str(exception)}],
                }
            )

    return {
        "run_id": run_id,
        "workflow_id": workflow_id,
        "principal_sub": principal_sub,
        "dry_run": bool(dry_run),
        "results": results,
    }
