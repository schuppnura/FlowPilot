# Core authorization logic for FlowPilot AuthZ API using OPA (no ***REMOVED***).
#
# Design goals
# - Keep policy evaluation simple: call a plain OPA server (HTTP) running in "server mode".
# - Keep the AuthZ API responsible for:
#   - authenticating callers (via shared security.py)
#   - shaping input for the Rego policy
#   - mapping OPA outputs into the OpenAPI response schema
#
# Assumptions
# - An OPA server is reachable at OPA_URL (default: http://opa:8181).
# - The Rego policy package is "auto_book" (configurable via OPA_PACKAGE).
# - Policy rules used:
#   - data.<package>.allow  -> boolean
#   - data.<package>.reason -> set/list of strings (optional)

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from utils import (
    http_post_json,
    build_timeouts,
    coerce_int,
    coerce_dict,
    coerce_bool,
    coerce_float,
    coerce_str,
    normalize_departure_date,
    read_env_string,
    read_env_int,
    read_env_float,
    read_env_bool,
    get_http_config,
)

# Required imports for fetching owner attributes and service tokens
import api_logging
import profile
import security

# ============================================================================
# Configuration Constants
# ============================================================================

# Default values for autobook attributes when not present in Keycloak
# These must be configured via environment variables in docker-compose.yml
DEFAULT_AUTOBOOK_CONSENT = read_env_bool("DEFAULT_AUTOBOOK_CONSENT")
DEFAULT_AUTOBOOK_PRICE = read_env_int("DEFAULT_AUTOBOOK_PRICE")
DEFAULT_AUTOBOOK_LEADTIME = read_env_int("DEFAULT_AUTOBOOK_LEADTIME")
DEFAULT_AUTOBOOK_RISKLEVEL = read_env_int("DEFAULT_AUTOBOOK_RISKLEVEL")

# Allowed action names (AuthZEN compliant, comma-separated)
# Must be configured via ALLOWED_ACTIONS environment variable
_ALLOWED_ACTIONS_STR = read_env_string("ALLOWED_ACTIONS")
ALLOWED_ACTIONS = {action.strip() for action in _ALLOWED_ACTIONS_STR.split(",") if action.strip()}




@dataclass(frozen=True)
class OpaConfig:
    base_url: str
    package: str
    allow_rule: str = "allow"
    reason_rule: str = "reasons"
    connect_timeout_seconds: float = 3.0
    read_timeout_seconds: float = 10.0


class OpaClient:
    def __init__(self, config: OpaConfig) -> None:
        self._config = config

    def evaluate_allow(self, input_document: dict[str, Any]) -> bool:
        result = self._post_data(
            path=f"{self._config.package}/{self._config.allow_rule}",
            input_document=input_document,
        )
        # OPA data API: {"result": <value>}
        return bool(result.get("result", False))

    def evaluate_reasons(self, input_document: dict[str, Any]) -> list[str]:
        result = self._post_data(
            path=f"{self._config.package}/{self._config.reason_rule}",
            input_document=input_document,
        )
        reasons = result.get("result", [])
        if reasons is None:
            return []
        if isinstance(reasons, list):
            return [str(item) for item in reasons]
        # Sets sometimes serialize as objects in some contexts; be defensive.
        if isinstance(reasons, dict):
            return [str(key) for key in reasons.keys()]
        return [str(reasons)]

    def _post_data(self, path: str, input_document: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._config.base_url.rstrip('/')}/v1/data/{path.lstrip('/')}"
        payload = {"input": input_document}
        timeouts = build_timeouts(
            connect_seconds=self._config.connect_timeout_seconds,
            read_seconds=self._config.read_timeout_seconds,
        )
        return http_post_json(url=url, payload=payload, timeouts=timeouts)


def _build_opa_client() -> OpaClient:
    # Build OPA client from required environment variables.
    config = OpaConfig(
        base_url=read_env_string("OPA_URL"),
        package=read_env_string("OPA_PACKAGE"),
    )
    return OpaClient(config=config)


# ============================================================================
# Module-Level Clients and Services
# ============================================================================

# OPA client instance (initialized on module load)
_OPA_CLIENT = _build_opa_client()

# Delegation API configuration (required environment variables)
_DELEGATION_API_BASE_URL = read_env_string("DELEGATION_API_BASE_URL")


@dataclass(frozen=True)
class EvaluateResult:
    decision: str  # "allow" | "deny"
    reason_codes: list[str]
    advice: list[dict[str, Any]]


def build_opa_input(
    *,
    authzen_request: dict[str, Any],
    delegation_result: Optional[Dict[str, Any]] = None,
    owner_attributes: Optional[Dict[str, Any]] = None,
) -> dict[str, Any]:
    # Build OPA input document from AuthZEN request.
    #
    # Args:
    #     authzen_request: AuthZEN-compliant request body with context.principal containing claims
    #     delegation_result: Computed delegation chain result from delegation-api (PIP data)
    #     owner_attributes: Optional owner's autobook attributes (always used if available, regardless of delegation)
    
    # Extract top-level AuthZEN elements
    request_context = authzen_request.get("context") or {}
    request_resource = authzen_request.get("resource") or {}
    request_action = authzen_request.get("action") or {}
    resource_properties = coerce_dict(request_resource.get("properties"), "resource.properties")
    
    # ========================================================================
    # SUBJECT: Extract principal (current user) information
    # ========================================================================
    principal = request_context.get("principal") or {}
    principal_sub = principal.get("id", "")
    
    # Extract principal persona (the persona the current user is using)
    principal_persona = principal.get("persona") or ""
    if isinstance(principal_persona, list) and principal_persona:
        principal_persona = principal_persona[0]
    principal_persona = str(principal_persona) if principal_persona else ""
    
    subject = {
        "type": "user",
        "id": principal_sub,
        "persona": principal_persona,
    }
    
    # ========================================================================
    # RESOURCE: Preserve AuthZEN structure and augment with owner attributes
    # ========================================================================
    # Start with the original resource structure from AuthZEN request
    resource = dict(request_resource)
    
    # Make a copy of properties to augment
    resource_properties_augmented = dict(resource_properties)
    
    # Normalize resource attributes for OPA consumption
    if "planned_price" in resource_properties_augmented:
        resource_properties_augmented["planned_price"] = coerce_float(
            resource_properties_augmented["planned_price"]
        )
    if "departure_date" in resource_properties_augmented:
        resource_properties_augmented["departure_date"] = normalize_departure_date(
            resource_properties_augmented["departure_date"]
        )
    if "airline_risk_score" in resource_properties_augmented:
        resource_properties_augmented["airline_risk_score"] = coerce_float(
            resource_properties_augmented["airline_risk_score"]
        )
    
    # Extract owner information
    owner_props = coerce_dict(resource_properties_augmented.get("owner"), "resource.properties.owner")
    owner_id = owner_props.get("id") if owner_props else None
    
    # Augment resource.properties.owner with fetched autobook attributes
    if owner_id and owner_attributes:
        owner_attrs = owner_attributes
        autobook_consent = coerce_bool(
            owner_attrs.get("autobook_consent"), DEFAULT_AUTOBOOK_CONSENT
        )
        autobook_price = coerce_int(
            owner_attrs.get("autobook_price"), DEFAULT_AUTOBOOK_PRICE
        )
        autobook_leadtime = coerce_int(
            owner_attrs.get("autobook_leadtime"), DEFAULT_AUTOBOOK_LEADTIME
        )
        autobook_risklevel = coerce_int(
            owner_attrs.get("autobook_risklevel"), DEFAULT_AUTOBOOK_RISKLEVEL
        )
        
        # Augment existing owner with autobook attributes
        if "owner" not in resource_properties_augmented:
            resource_properties_augmented["owner"] = {}
        if not isinstance(resource_properties_augmented["owner"], dict):
            resource_properties_augmented["owner"] = {}
        
        resource_properties_augmented["owner"]["autobook_consent"] = autobook_consent
        resource_properties_augmented["owner"]["autobook_price"] = autobook_price
        resource_properties_augmented["owner"]["autobook_leadtime"] = autobook_leadtime
        resource_properties_augmented["owner"]["autobook_risklevel"] = autobook_risklevel
    
    # Update resource with augmented properties
    resource["properties"] = resource_properties_augmented
    
    # ========================================================================
    # DELEGATION: Delegation data from delegation-api (PIP)
    # OPA will check if effective_actions contains the requested action
    # ========================================================================
    if delegation_result is not None:
        delegation = delegation_result
    else:
        delegation = {
            "valid": False,
            "delegation_chain": [],
            "effective_actions": [],
        }
    
    # ========================================================================
    # CONTEXT: Build AuthZEN-compliant context with delegation
    # ========================================================================
    context = {
        "delegation": delegation,
    }
    
    # ========================================================================
    # Assemble final OPA input document
    # ========================================================================
    return {
        "subject": subject,
        "action": request_action,
        "resource": resource,
        "context": context,
    }


def compute_delegation_chain(
    *,
    owner_id: str,
    principal_id: str,
    workflow_id: Optional[str],
    requested_action: str,
) -> Dict[str, Any]:
    # Fetch delegation chain data from delegation-api.
    # Returns delegation information for OPA to evaluate.
    #
    # This function acts as a Policy Information Point (PIP) - it fetches data
    # but does NOT make policy decisions. The OPA policy (PDP) decides whether
    # the available delegation permissions are sufficient.
    #
    # Args:
    #     owner_id: Owner ID (resource owner)
    #     principal_id: Principal ID (user attempting to act)
    #     workflow_id: Optional workflow ID to scope the delegation
    #     requested_action: Unused - kept for API compatibility, will be removed
    #
    # Returns:
    #     Dictionary with:
    #       - valid: boolean (whether delegation path exists)
    #       - delegation_chain: list of user IDs in the chain
    #       - effective_actions: list of actions available through delegation
    #
    # Raises:
    #     RuntimeError: If service token is not available
    
    # Get service token for delegation API authentication
    service_token = security.get_service_token()
    if not service_token:
        raise RuntimeError("Service token not available - cannot validate delegation")
    
    headers = {"Authorization": f"Bearer {service_token.strip()}"}
    
    params: Dict[str, str] = {
        "principal_id": owner_id,
        "delegate_id": principal_id,
    }
    if workflow_id:
        params["workflow_id"] = workflow_id
    
    response = requests.get(
        f"{_DELEGATION_API_BASE_URL.rstrip('/')}/v1/delegations/validate",
        params=params,
        headers=headers,
        **get_http_config(),
    )
    response.raise_for_status()  # Raise HTTPError for bad responses
    
    data = response.json()
    valid = data.get("valid", False)
    delegation_chain = data.get("delegation_chain", [])
    effective_actions = data.get("effective_actions", [])
    
    # Return raw delegation data - let OPA decide if permissions are sufficient
    return {
        "valid": valid,
        "delegation_chain": delegation_chain,
        "effective_actions": effective_actions,
    }


def evaluate_authorization_request(
    authzen_request: dict[str, Any],
) -> EvaluateResult:
    # Evaluate an authorization request end-to-end.
    #
    # This function handles the complete authorization flow:
    # 1. Validates AuthZEN compliance
    # 2. Computes delegation chain (if resource has owner)
    # 3. Fetches owner attributes (if resource has owner)
    # 4. Evaluates the request with OPA
    #
    # Args:
    #     authzen_request: AuthZEN-compliant request body
    #
    # Returns:
    #     EvaluateResult with decision, reason_codes, and advice
    #
    # Raises:
    #     ValueError: If request is not AuthZEN compliant
    
    # Validate and extract principal
    context = authzen_request.get("context", {})
    principal = context.get("principal")
    if not principal or not isinstance(principal, dict):
        raise ValueError("Request must be AuthZEN compliant: context.principal is required")

    principal_id = principal.get("id")
    if (
        not principal_id
        or not isinstance(principal_id, str)
        or not principal_id.strip()
    ):
        raise ValueError("Request must be AuthZEN compliant: context.principal.id is required")
    principal_id = principal_id.strip()

    # Validate and extract action
    action = authzen_request.get("action", {})
    if not action or not isinstance(action, dict):
        raise ValueError("Request must be AuthZEN compliant: action is required")
    
    action_name = action.get("name")
    if not action_name or not isinstance(action_name, str) or not action_name.strip():
        raise ValueError("Request must be AuthZEN compliant: action.name is required")

    action_name = security.sanitize_string(action_name.strip(), 255)
    if action_name not in ALLOWED_ACTIONS:
        raise ValueError(f"Invalid action name: {action_name}. Allowed actions: {', '.join(sorted(ALLOWED_ACTIONS))}")
    
    # Validate and extract workflow and owner information from resoruce
    request_resource = authzen_request.get("resource", {})
    resource_properties = request_resource.get("properties", {})
    
    owner = resource_properties.get("owner")
    owner_id = None
    workflow_id = None
    if isinstance(owner, dict):
        owner_id_raw = owner.get("id")
        owner_id = str(owner_id_raw) if owner_id_raw else None
        workflow_id_raw = resource_properties.get("workflow_id") or request_resource.get("id")
        workflow_id = str(workflow_id_raw) if workflow_id_raw else None
    
    # Compute delegation chain and fetch owner attributes (PIP - Policy Information Point)
    delegation_result = None
    owner_attributes = None    
    if owner_id:        
        # Fetch owner's autobook attributes and persona from Keycloak
        owner_attributes = profile.fetch_attributes(owner_id)

        # Compute delegation chain from delegation-api
        delegation_result = compute_delegation_chain(
            owner_id=owner_id,
            principal_id=principal_id,
            workflow_id=workflow_id,
            requested_action=action_name,
        )
    
    # Build OPA input document and evaluate with OPA
    input_document = build_opa_input(
        authzen_request=authzen_request,
        delegation_result=delegation_result,
        owner_attributes=owner_attributes,
    )
    
    api_logging.log_api_request("POST", "OPA /v1/data/auto_book/allow", request_body=input_document)
    
    is_allowed = _OPA_CLIENT.evaluate_allow(input_document=input_document)
    reasons = _OPA_CLIENT.evaluate_reasons(input_document=input_document)
    
    return EvaluateResult(
        decision="allow" if is_allowed else "deny",
        reason_codes=reasons,
        advice=[],
    )


