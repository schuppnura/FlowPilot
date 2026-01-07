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
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List

import requests

import security
from utils import (
    build_url,
    http_get_json,
    require_non_empty_string,
    build_timeouts,
    get_http_config,
)


@dataclass(frozen=True)
class WorkflowItem:
    workflow_item_id: str
    kind: str
    raw: Dict[str, Any]


def normalize_workflow_id(workflow_id: str) -> str:
    # Normalize workflow_id
    # why: keep validation centralized
    if workflow_id and isinstance(workflow_id, str) and workflow_id.strip():
        return workflow_id.strip()
    raise ValueError("Missing workflow_id")


def list_workflow_items(
    config: Dict[str, Any],
    workflow_id: str,
    principal_user_id: str = None,
    principal_persona: str = None,
) -> List[WorkflowItem]:
    # List workflow items from the workflow service
    # assumption: response contains an 'items' list of dicts.
    # principal_user_id: user's UUID for authorization (passed as query parameter)
    # principal_persona: user's persona for authorization (passed as query parameter)
    require_non_empty_string(workflow_id, "workflow_id")

    base_url = require_non_empty_string(
        str(config.get("workflow_base_url", "")), "workflow_base_url"
    )
    template = require_non_empty_string(
        str(config.get("workflow_items_path_template", "")),
        "workflow_items_path_template",
    )
    timeout_seconds = int(config.get("request_timeout_seconds", 10))

    # Build URL with user_sub and persona query parameters if provided
    base_url_with_path = build_url(base_url, template.format(workflow_id=workflow_id))
    query_params = []
    if principal_user_id:
        query_params.append(f"user_sub={principal_user_id}")
    if principal_persona:
        query_params.append(f"persona={principal_persona}")

    if query_params:
        separator = "&" if "?" in base_url_with_path else "?"
        url = f"{base_url_with_path}{separator}{'&'.join(query_params)}"
    else:
        url = base_url_with_path

    headers = {}
    token = security.get_service_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = http_get_json(
        url=url, timeout_seconds=timeout_seconds, headers=headers if headers else None
    )

    items_raw = payload.get("items", [])
    if not isinstance(items_raw, list):
        raise ValueError("Workflow items response malformed: items must be a list")

    items: List[WorkflowItem] = []
    for item in items_raw:
        if not isinstance(item, dict):
            continue
        item_id = (
            item.get("item_id")
            or item.get("workflow_item_id")
            or item.get("itinerary_item_id")
        )
        kind = item.get("kind") or "unknown"
        if isinstance(item_id, str) and item_id.strip():
            items.append(
                WorkflowItem(workflow_item_id=item_id.strip(), kind=str(kind), raw=item)
            )

    return items


def parse_policy_deny_from_body(response_text: str) -> tuple[list[str], str]:
    # Parse deny reason codes from FlowPilot/AuthZ error bodies
    # Returns (reason_codes, message) tuple
    reason_codes: list[str] = []
    message: str = response_text.strip()

    # Try to parse as JSON
    if response_text.strip().startswith("{"):
        parsed = json.loads(response_text)
        if isinstance(parsed, dict):
            detail = parsed.get("detail")
            if isinstance(detail, str) and detail.strip() != "":
                message = detail.strip()

    # Extract reason codes from message
    if "reason_codes" in message:
        start = message.find("reason_codes=")
        if start >= 0:
            fragment = message[start:]
            left = fragment.find("[")
            right = fragment.find("]")
            if left >= 0 and right > left:
                content = fragment[left + 1 : right]
                reason_codes = [
                    part.strip().strip("'\"")
                    for part in content.split(",")
                    if part.strip() != ""
                ]

    if not reason_codes:
        if "***REMOVED***.deny" in message:
            reason_codes = ["***REMOVED***.deny"]

    return reason_codes, message


def check_workflow_execution_authorization(
    config: Dict[str, Any],
    workflow_id: str,
    principal_user: Dict[str, Any],
    agent_sub: str,
) -> Dict[str, Any]:
    # AuthZEN: Basic anti-spoofing check - verify principal is valid
    # why: prevent trivial principal spoofing before starting workflow execution
    # note: Full authorization happens at workflow item level via domain-services-api
    # side effects: minimal validation, no network I/O required
    require_non_empty_string(workflow_id, "workflow_id")
    if not isinstance(principal_user, dict) or not principal_user.get("id"):
        return {
            "decision": "deny",
            "reason_codes": ["invalid_principal"],
            "advice": [{"type": "error", "message": "Invalid principal_user object"}],
        }

    # Basic validation: principal must have an ID
    principal_id = principal_user.get("id", "").strip()
    if not principal_id:
        return {
            "decision": "deny",
            "reason_codes": ["missing_principal_id"],
            "advice": [{"type": "error", "message": "Principal ID is required"}],
        }

    # For now, allow if principal is valid (full authorization happens at item level)
    # In the future, this could check delegation relationships via authz-api
    return {"decision": "allow", "reason_codes": [], "advice": []}


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
    token = security.get_service_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.post(
        url, json=payload, headers=headers if headers else None, **get_http_config()
    )
    response_text = response.text or ""

    # Parse JSON response if content-type indicates JSON
    parsed_json: dict[str, Any] | None = None
    if response.headers.get("content-type", "").startswith("application/json"):
        parsed = response.json()
        if isinstance(parsed, dict):
            parsed_json = parsed

    return response.status_code, parsed_json, response_text


def execute_workflow_item(
    config: Dict[str, Any],
    workflow_id: str,
    workflow_item_id: str,
    principal_user: Dict[str, Any],
    dry_run: bool,
) -> Dict[str, Any]:
    # Execute a single workflow item via the domain service and classify policy denies (HTTP 403) as completed results
    # why: denies are valid authorization outcomes and must not be treated as execution failures
    # assumptions: domain service returns 2xx on allow, 403 on deny, and other 4xx/5xx on true failures
    # side effects: network I/O.
    # AuthZEN: Pass principal-user object instead of just principal_sub
    require_non_empty_string(workflow_id, "workflow_id")
    require_non_empty_string(workflow_item_id, "workflow_item_id")
    if not isinstance(principal_user, dict) or not principal_user.get("id"):
        raise ValueError("Invalid principal_user object")

    base_url = require_non_empty_string(
        str(config.get("workflow_base_url", "")), "workflow_base_url"
    )
    template = require_non_empty_string(
        str(config.get("workflow_item_execute_path_template", "")),
        "workflow_item_execute_path_template",
    )

    timeout_seconds = int(config.get("request_timeout_seconds", 10))
    timeouts = build_timeouts(connect_seconds=timeout_seconds)

    url = build_url(
        base_url,
        template.format(workflow_id=workflow_id, workflow_item_id=workflow_item_id),
    )
    # AuthZEN: Pass principal-user object instead of just principal_sub
    payload: Dict[str, Any] = {
        "principal_user": principal_user,
        "dry_run": bool(dry_run),
    }

    status_code, response_json, response_text = post_execute_workflow_item(
        url=url, payload=payload, timeouts=timeouts
    )

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
        # Extract reason_codes from JSON response if available, otherwise parse from text
        reason_codes: list[str] = []
        advice: list[dict[str, Any]] = []
        if response_json and isinstance(response_json, dict):
            # Try to get reason_codes from detail object
            detail = response_json.get("detail", {})
            if isinstance(detail, dict):
                reason_codes = list(detail.get("reason_codes", []) or [])
                advice = list(detail.get("advice", []) or [])
            elif isinstance(detail, str):
                # Fallback: parse from string format
                parsed_reason_codes, message = parse_policy_deny_from_body(
                    response_text
                )
                reason_codes = parsed_reason_codes
                if message:
                    advice = [{"type": "deny", "message": message}]
        else:
            # Fallback: parse from text
            parsed_reason_codes, message = parse_policy_deny_from_body(response_text)
            reason_codes = parsed_reason_codes
            if message:
                advice = [{"type": "deny", "message": message}]

        return {
            "http_status": status_code,
            "status": "completed",
            "outcome": "deny",
            "reason_codes": reason_codes,
            "advice": (
                advice if advice else [{"type": "deny", "message": "Access denied"}]
            ),
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


def execute_workflow_run(
    config: Dict[str, Any],
    workflow_id: str,
    principal_user: Dict[str, Any],
    dry_run: bool,
) -> Dict[str, Any]:
    # Execute a workflow by iterating items and delegating execution to domain endpoints,
    # normalizing each item result into a stable schema
    # why: the UI expects consistent status/decision fields even for denies
    # assumptions: execute_workflow_item returns {status, outcome, reason_codes, advice}
    # and may raise ValueError for invalid inputs
    # side effects: network I/O.
    # AuthZEN: Accept principal-user object instead of just principal_sub
    require_non_empty_string(workflow_id, "workflow_id")
    if not isinstance(principal_user, dict) or not principal_user.get("id"):
        raise ValueError("Invalid principal_user object")

    run_id = "wr_" + uuid.uuid4().hex[:10]
    # List workflow items using the agent's own delegation (from workflow owner)
    # Do NOT pass principal_user_id - that would check if the principal has read access
    # The agent has its own read delegation and can list items regardless of who requests execution
    # Authorization for execution is checked per-item below
    items = list_workflow_items(
        config=config,
        workflow_id=workflow_id,
        principal_user_id=None,
        principal_persona=None,
    )

    results: List[Dict[str, Any]] = []
    for item in items:
        try:
            response = execute_workflow_item(
                config=config,
                workflow_id=workflow_id,
                workflow_item_id=item.workflow_item_id,
                principal_user=principal_user,
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
        "principal_sub": principal_user.get(
            "id", ""
        ),  # Keep for backward compatibility
        "principal_user": principal_user,  # AuthZEN: include full principal-user object
        "dry_run": bool(dry_run),
        "results": results,
    }
