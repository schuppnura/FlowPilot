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
from utils import (
    build_timeouts,
    build_url,
    get_http_config,
    http_get_json,
    http_post_json,
    require_non_empty_string,
)


@dataclass(frozen=True)
class WorkflowItem:
    workflow_item_id: str
    kind: str
    raw: dict[str, Any]


def normalize_workflow_id(workflow_id: str) -> str:
    # Normalize workflow_id
    # why: keep validation centralized
    if workflow_id and isinstance(workflow_id, str) and workflow_id.strip():
        return workflow_id.strip()
    raise ValueError("Missing workflow_id")


def list_workflow_items(
    config: dict[str, Any],
    workflow_id: str,
    principal_user_id: str = None,
    principal_persona_title: str = None,
    principal_persona_circle: str = None,
    user_token: str = None,
) -> list[WorkflowItem]:
    # List workflow items from the workflow service
    # assumption: response contains an 'items' list of dicts.
    # principal_user_id: user's UUID for authorization (passed as query parameter)
    # principal_persona_title: user's persona title for authorization (passed as query parameter)
    # principal_persona_circle: user's persona circle for authorization (passed as query parameter)
    require_non_empty_string(workflow_id, "workflow_id")

    base_url = require_non_empty_string(
        str(config.get("workflow_base_url", "")), "workflow_base_url"
    )
    template = require_non_empty_string(
        str(config.get("workflow_items_path_template", "")),
        "workflow_items_path_template",
    )
    timeout_seconds = int(config.get("request_timeout_seconds", 10))

    # Build URL with user_sub, persona_title, and persona_circle query parameters if provided
    base_url_with_path = build_url(base_url, template.format(workflow_id=workflow_id))
    query_params = []
    if principal_user_id:
        query_params.append(f"user_sub={principal_user_id}")
    if principal_persona_title:
        query_params.append(f"persona_title={principal_persona_title}")
    if principal_persona_circle:
        query_params.append(f"persona_circle={principal_persona_circle}")

    if query_params:
        separator = "&" if "?" in base_url_with_path else "?"
        url = f"{base_url_with_path}{separator}{'&'.join(query_params)}"
    else:
        url = base_url_with_path

    headers = {}
    # Use user token if provided (agent acts on behalf of user)
    if user_token:
        headers["Authorization"] = f"Bearer {user_token}"
    else:
        raise ValueError("User token is required for service-to-service calls")

    payload = http_get_json(
        url=url, timeout_seconds=timeout_seconds, headers=headers if headers else None
    )

    items_raw = payload.get("items", [])
    if not isinstance(items_raw, list):
        raise ValueError("Workflow items response malformed: items must be a list")

    items: list[WorkflowItem] = []
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


def _call_authz_for_workflow(
    config: dict[str, Any],
    workflow: dict[str, Any],
    principal_user: dict[str, Any],
    agent_sub: str,
    action: str = "execute",
    user_token: str = None,
) -> dict[str, Any]:
    # Call AuthZ /v1/evaluate for workflow operations
    # Handles workflow-level actions: create, read, update, delete, execute
    # This follows the same pattern as domain-services-api for consistency
    authz_base_url = require_non_empty_string(
        str(config.get("authz_base_url", "")), "authz_base_url"
    )
    
    # Extract workflow properties
    workflow_id = str(workflow.get("workflow_id", ""))
    workflow_domain = workflow.get("domain", "travel")
    owner_sub = str(workflow.get("owner_sub", ""))
    owner_persona_title = workflow.get("owner_persona_title")  # Get persona title from workflow
    owner_persona_circle = workflow.get("owner_persona_circle")  # Get persona circle from workflow
    departure_date = workflow.get("departure_date")
    
    # Validate that owner_persona_title is present (required for authz checks)
    if not owner_persona_title:
        raise ValueError(f"Workflow {workflow_id} is missing owner_persona_title - cannot perform authorization check")
    
    # Build resource properties
    resource_properties: dict[str, Any] = {
        "workflow_id": workflow_id,
        "domain": workflow_domain,
    }
    
    # Add departure_date if available
    if departure_date:
        resource_properties["departure_date"] = departure_date
    
    # Add owner to resource properties (persona means title here in AuthZEN context)
    if owner_sub:
        owner_dict: dict[str, Any] = {"type": "user", "id": owner_sub}
        if owner_persona_title:
            owner_dict["persona"] = str(owner_persona_title)  # In AuthZEN, 'persona' field contains the title
        if owner_persona_circle:
            owner_dict["circle"] = str(owner_persona_circle)
        resource_properties["owner"] = owner_dict
    
    # Build AuthZEN request
    url = build_url(authz_base_url, "/v1/evaluate")
    
    # AuthZEN: Build context with principal-user object
    context: dict[str, Any] = {
        "principal": principal_user,
        "policy_hint": workflow_domain,  # Dynamic policy selection based on domain
    }
    
    # Subject is the agent making the call
    subject: dict[str, Any] = {
        "type": "agent",
        "id": agent_sub,
    }
    
    # Build resource
    resource: dict[str, Any] = {
        "type": "workflow",
        "id": workflow_id,
        "properties": resource_properties,
    }
    
    # Build options
    options: dict[str, Any] = {"explain": True, "metrics": False}
    
    body: dict[str, Any] = {
        "subject": subject,
        "action": {"name": action},
        "resource": resource,
        "context": context,
        "options": options,
    }
    
    # Always use service token for authz-api calls (user identity is in context.principal)
    # This matches how domain-services-api calls authz-api
    import security
    service_token = security.get_service_token()
    headers = {"Authorization": f"Bearer {service_token}"} if service_token else {}
    
    # Log warning if no service token is available
    if not service_token:
        print(f"WARNING: No service token available for authz API call. This may cause authorization failures.", flush=True)
    
    # Use centralized http_post_json for logging and error handling
    return http_post_json(
        url=url,
        payload=body,
        timeouts=build_timeouts(connect_seconds=int(config.get("request_timeout_seconds", 10))),
        headers=headers if headers else None,
    )


def check_workflow_execution_authorization(
    config: dict[str, Any],
    workflow_id: str,
    principal_user: dict[str, Any],
    agent_sub: str,
    user_token: str = None,
) -> dict[str, Any]:
    # Check workflow-level authorization via authz-api before executing any items
    # why: prevent wasted work by checking if ANY item could be executed
    # side effects: network I/O to authz-api and domain-services-api
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
    
    principal_persona_title = principal_user.get("persona_title", "").strip()
    if not principal_persona_title:
        return {
            "decision": "deny",
            "reason_codes": ["missing_principal_persona_title"],
            "advice": [{"type": "error", "message": "Principal persona title is required"}],
        }
    
    principal_persona_circle = principal_user.get("persona_circle", "").strip()
    if not principal_persona_circle:
        return {
            "decision": "deny",
            "reason_codes": ["missing_principal_persona_circle"],
            "advice": [{"type": "error", "message": "Principal persona circle is required"}],
        }
    
    if not user_token:
        return {
            "decision": "deny",
            "reason_codes": ["missing_user_token"],
            "advice": [{"type": "error", "message": "User token is required for authorization check"}],
        }
    
    # Get workflow from domain-services to extract owner and domain
    workflow_base_url = require_non_empty_string(
        str(config.get("workflow_base_url", "")), "workflow_base_url"
    )
    workflow_url = build_url(workflow_base_url, f"/v1/workflows/{workflow_id}")
    
    headers = {"Authorization": f"Bearer {user_token}"}
    
    # Build query parameters with persona title and circle (required by domain-services API)
    params = {
        "persona_title": principal_persona_title,
        "persona_circle": principal_persona_circle,
    }
    
    try:
        # Fetch workflow metadata
        workflow = http_get_json(
            url=workflow_url,
            params=params,
            timeout_seconds=int(config.get("request_timeout_seconds", 10)),
            headers=headers,
        )
        
        # Call authz-api using the shared helper function
        result = _call_authz_for_workflow(
            config=config,
            workflow=workflow,
            principal_user=principal_user,
            agent_sub=agent_sub,
            action="execute",
            user_token=user_token,
        )
        
        return {
            "decision": result.get("decision", "deny"),
            "reason_codes": result.get("reason_codes", []),
            "advice": result.get("advice", []),
        }
    
    except RuntimeError as exc:
        # Authorization check failed - treat as deny
        error_str = str(exc)
        return {
            "decision": "deny",
            "reason_codes": ["workflow_authorization_check_failed"],
            "advice": [{"type": "error", "message": f"Failed to check authorization: {error_str}"}],
        }


def post_execute_workflow_item(
    url: str,
    payload: dict[str, Any],
    timeouts: tuple[float, float],
    user_token: str = None,
) -> tuple[int, dict[str, Any] | None, str]:
    # Call the domain execute endpoint and return status + parsed JSON when possible
    # why: distinguish policy deny (403) from execution errors
    # assumptions: JSON body on success and often on failure
    # side effects: network I/O, automatic logging via http_post_json
    #
    # Note: This function wraps http_post_json to provide status code + text for 403 handling
    headers = {}
    # Use user token if provided (agent acts on behalf of user)
    if user_token:
        headers["Authorization"] = f"Bearer {user_token}"

    try:
        # Use centralized http_post_json for logging and error handling
        response_json = http_post_json(
            url=url,
            payload=payload,
            timeouts=timeouts,
            headers=headers if headers else None,
        )
        # Success: return 200 with parsed JSON
        return 200, response_json, ""
    except RuntimeError as exc:
        # http_post_json raised RuntimeError for non-2xx response
        # Parse the error message to extract status code and body
        error_str = str(exc)
        
        # Extract status code from error message: "HTTP POST non-2xx: url=... http=403 body=..."
        status_code = 500  # Default to 500 if we can't parse
        response_text = error_str
        
        if "http=" in error_str:
            try:
                # Extract status code
                parts = error_str.split("http=")
                if len(parts) > 1:
                    status_part = parts[1].split()[0]
                    status_code = int(status_part)
                
                # Extract body
                if "body=" in error_str:
                    body_parts = error_str.split("body=")
                    if len(body_parts) > 1:
                        response_text = body_parts[1]
            except (ValueError, IndexError):
                pass
        
        # Try to parse JSON from response text
        parsed_json: dict[str, Any] | None = None
        if response_text and response_text.strip().startswith("{"):
            try:
                import json
                parsed_json = json.loads(response_text)
                if not isinstance(parsed_json, dict):
                    parsed_json = None
            except (json.JSONDecodeError, ValueError):
                pass
        
        return status_code, parsed_json, response_text


def execute_workflow_item(
    config: dict[str, Any],
    workflow_id: str,
    workflow_item_id: str,
    principal_user: dict[str, Any],
    dry_run: bool,
    user_token: str = None,
) -> dict[str, Any]:
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
    payload: dict[str, Any] = {
        "principal_user": principal_user,
        "dry_run": bool(dry_run),
    }

    status_code, response_json, response_text = post_execute_workflow_item(
        url=url, payload=payload, timeouts=timeouts, user_token=user_token
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
    config: dict[str, Any],
    workflow_id: str,
    principal_user: dict[str, Any],
    dry_run: bool,
    user_token: str = None,
) -> dict[str, Any]:
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
    # List workflow items using the agent's delegation from the principal
    # Pass principal_user_id so domain-services can verify the agent has delegation from the principal
    # Authorization for execution is checked per-item below
    try:
        items = list_workflow_items(
            config=config,
            workflow_id=workflow_id,
            principal_user_id=principal_user.get("id"),
            principal_persona_title=principal_user.get("persona_title"),
            principal_persona_circle=principal_user.get("persona_circle"),
            user_token=user_token,
        )
    except (ValueError, RuntimeError) as exc:
        # If listing workflow items fails with 403, it means the principal lacks read access
        # Return empty results with appropriate error rather than crashing
        error_str = str(exc)
        if "http=403" in error_str:
            # Extract reason codes from error message if available
            reason_codes = ["workflow_access_denied"]
            advice_msg = "Principal does not have read access to this workflow"
            
            # Try to parse reason codes from the error body
            if "body=" in error_str:
                body_parts = error_str.split("body=")
                if len(body_parts) > 1:
                    try:
                        import json
                        error_body = json.loads(body_parts[1])
                        if isinstance(error_body, dict):
                            detail = error_body.get("detail", {})
                            if isinstance(detail, dict):
                                reason_codes = detail.get("reason_codes", reason_codes)
                                advice_list = detail.get("advice", [])
                                if advice_list and isinstance(advice_list, list) and len(advice_list) > 0:
                                    advice_msg = advice_list[0].get("message", advice_msg)
                    except (json.JSONDecodeError, ValueError, KeyError, IndexError):
                        pass
            
            return {
                "run_id": run_id,
                "workflow_id": workflow_id,
                "principal_sub": principal_user.get("id", ""),
                "principal_user": principal_user,
                "dry_run": bool(dry_run),
                "results": [],
                "error": {
                    "message": advice_msg,
                    "reason_codes": reason_codes,
                }
            }
        # Re-raise if not a 403 error
        raise

    results: list[dict[str, Any]] = []
    for item in items:
        try:
            response = execute_workflow_item(
                config=config,
                workflow_id=workflow_id,
                workflow_item_id=item.workflow_item_id,
                principal_user=principal_user,
                dry_run=dry_run,
                user_token=user_token,
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
