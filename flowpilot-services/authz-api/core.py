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

import copy
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from utils import http_post_json, build_timeouts, coerce_int, coerce_dict, coerce_bool

# Import profile and security for fetching owner attributes and service tokens
try:
    import profile
    import security
except ImportError:
    # Allow core.py to be imported without these if needed for testing
    profile = None
    security = None

# ============================================================================
# Configuration Constants
# ============================================================================

# Default values for autobook attributes when not present in Keycloak
DEFAULT_AUTOBOOK_CONSENT = False  # No consent by default
DEFAULT_AUTOBOOK_PRICE = 0  # Maximum cost in EUR
DEFAULT_AUTOBOOK_LEADTIME = 10000  # Minimum days in advance
DEFAULT_AUTOBOOK_RISKLEVEL = 0  # Maximum airline risk level

# Allowed action names (AuthZEN compliant)
ALLOWED_ACTIONS = {"create", "read", "write", "delete", "execute"}


def _read_env_string(name: str, default_value: str) -> str:
    # Read environment variable with default value.
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default_value
    return value.strip()


def _read_env_float(name: str, default_value: float) -> float:
    # Read float environment variable with default value.
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default_value
    try:
        return float(value.strip())
    except ValueError:
        return default_value


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
    # Build OPA client from environment variables.
    config = OpaConfig(
        base_url=_read_env_string("OPA_URL", "http://opa:8181"),
        package=_read_env_string("OPA_PACKAGE", "auto_book"),
    )
    return OpaClient(config=config)


# ============================================================================
# Module-Level Clients and Services
# ============================================================================

# OPA client instance (initialized on module load)
_OPA_CLIENT = _build_opa_client()

# Delegation API configuration
_DELEGATION_API_BASE_URL = _read_env_string(
    "DELEGATION_API_BASE_URL", "http://flowpilot-delegation-api:8000"
)
_DELEGATION_API_TIMEOUT_SECONDS = _read_env_float(
    "DELEGATION_API_TIMEOUT_SECONDS", 5.0
)


@dataclass(frozen=True)
class EvaluateResult:
    decision: str  # "allow" | "deny"
    reason_codes: list[str]
    advice: list[dict[str, Any]]


def build_opa_input(
    *,
    authzen_request: dict[str, Any],
    delegations_data: Optional[List[Dict[str, Any]]] = None,
    owner_attributes: Optional[Dict[str, Any]] = None,
) -> dict[str, Any]:
    # Build OPA input document from AuthZEN request.
    #
    # Args:
    #     authzen_request: AuthZEN-compliant request body with context.principal containing claims
    #     delegations_data: List of delegation dictionaries fetched from delegation-api (PIP data)
    #     owner_attributes: Optional owner's autobook attributes (always used if available, regardless of delegation)
    request_context = authzen_request.get("context") or {}
    request_resource = authzen_request.get("resource") or {}
    request_action = authzen_request.get("action") or {}

    resource_properties = coerce_dict(request_resource.get("properties"))

    # Extract principal from AuthZEN context.principal
    principal = request_context.get("principal") or {}
    principal_sub = principal.get("id", "")
    # Extract selected persona from principal (the persona the current user is using)
    principal_persona = principal.get("persona") or ""
    if isinstance(principal_persona, list) and principal_persona:
        principal_persona = principal_persona[0]
    principal_persona = str(principal_persona) if principal_persona else ""

    # Extract owner from resource properties
    owner_props = coerce_dict(resource_properties.get("owner"))
    owner_id = owner_props.get("id") if owner_props else None
    # Extract owner persona from resource properties (set by domain-services-api when workflow was created)
    owner_persona_from_resource = owner_props.get("persona") if owner_props else None

    # Always use owner's autobook attributes - autobook settings are always based on owner's preferences
    # Coerce with defaults (works whether owner_attributes is None or a dict)
    owner_attrs = owner_attributes or {}
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

    # Context should only contain minimal principal information (id and persona)
    # Remove claims entirely - not needed in context.principal
    # Identity is in context.principal.id, owner attributes are in resource.properties.owner
    context_principal = dict(principal)  # Shallow copy of principal
    
    # Remove claims field entirely from context.principal
    if "claims" in context_principal:
        del context_principal["claims"]
    
    context = {"principal": context_principal}

    # Build resource with properties including owner (id, persona, autobook settings)
    # All owner information belongs in resource.properties.owner (as per AuthZEN spec)
    # Get workflow_id from properties (for workflow_item) or resource.id (for workflow)
    workflow_id_value = resource_properties.get("workflow_id") or request_resource.get("id")
    resource_dict: Dict[str, Any] = {
        "workflow_id": workflow_id_value,
        "planned_price": resource_properties.get("planned_price"),
        "departure_date": resource_properties.get("departure_date"),
        "airline_risk_score": resource_properties.get("airline_risk_score"),
        "owner_id": owner_id,
    }
    
    # Include owner in resource.properties with all owner information
    if owner_id:
        resource_properties_with_owner = dict(resource_properties)  # Copy to avoid mutating original
        if "owner" not in resource_properties_with_owner:
            resource_properties_with_owner["owner"] = {}
        if not isinstance(resource_properties_with_owner["owner"], dict):
            resource_properties_with_owner["owner"] = {}
        
        # Set owner id
        resource_properties_with_owner["owner"]["id"] = owner_id
        
        # Use persona from resource properties (set by domain-services-api) if available
        # Otherwise fall back to persona from owner attributes
        owner_persona = owner_persona_from_resource
        if not owner_persona:
            owner_persona = owner_attrs.get("persona", "")
            if isinstance(owner_persona, list) and owner_persona:
                owner_persona = owner_persona[0]
        
        if owner_persona:
            resource_properties_with_owner["owner"]["persona"] = str(owner_persona)
        
        # Add autobook settings to owner
        resource_properties_with_owner["owner"]["autobook_consent"] = autobook_consent
        resource_properties_with_owner["owner"]["autobook_price"] = autobook_price
        resource_properties_with_owner["owner"]["autobook_leadtime"] = autobook_leadtime
        resource_properties_with_owner["owner"]["autobook_risklevel"] = autobook_risklevel
        
        resource_dict["properties"] = resource_properties_with_owner

    opa_input = {
        "subject": {
            "type": "agent",  # Subject is the agent (service) making the call
            "id": principal_sub,  # the actual, current user (principal)
            "persona": principal_persona,  # Selected persona of the current user
        },
        "action": request_action,
        "resource": resource_dict,
        "context": context,
    }

    # Add delegation data for OPA policy evaluation (PIP - Policy Information Point)
    # OPA will evaluate delegations declaratively to determine if delegation chain exists
    if delegations_data is not None:
        opa_input["delegations"] = delegations_data
    else:
        opa_input["delegations"] = []

    return opa_input


def fetch_delegations_for_opa(
    *,
    bearer_token: str,
    owner_id: str,
    principal_id: str,
    workflow_id: Optional[str],
) -> List[Dict[str, Any]]:
    # Fetch delegations from delegation-api to pass to OPA for policy evaluation.
    # This acts as a PIP (Policy Information Point) - fetching data for OPA to evaluate.
    #
    # Args:
    #     bearer_token: Service token for authenticating with delegation API (already validated by caller)
    #     owner_id: Owner ID (resource owner)
    #     principal_id: Principal ID (user attempting to act)
    #     workflow_id: Optional workflow ID to scope the delegation fetch
    #
    # Returns:
    #     List of delegation dictionaries for OPA to evaluate
    #
    # Raises:
    #     RuntimeError: If delegation API returns an error
    headers = {"Authorization": f"Bearer {bearer_token.strip()}"}
    delegations: List[Dict[str, Any]] = []
    seen_keys: set[tuple[str, str, Optional[str]]] = (
        set()
    )  # Track (principal_id, delegate_id, workflow_id) to deduplicate

    # Fetch outgoing delegations from owner (filtered by workflow_id if provided)
    # The delegation API returns both workflow-specific and general (workflow_id IS NULL) delegations
    try:
        params: Dict[str, str] = {"principal_id": owner_id, "include_expired": "false"}
        if workflow_id:
            params["workflow_id"] = workflow_id

        response = requests.get(
            f"{_DELEGATION_API_BASE_URL.rstrip('/')}/v1/delegations",
            params=params,
            headers=headers,
            timeout=_DELEGATION_API_TIMEOUT_SECONDS,
            verify=False,  # Allow self-signed certs for local dev
        )

        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and "delegations" in data:
                for d in data.get("delegations", []):
                    key = (
                        d.get("principal_id"),
                        d.get("delegate_id"),
                        d.get("workflow_id"),
                    )
                    if key not in seen_keys:
                        delegations.append(d)
                        seen_keys.add(key)
    except Exception as e:
        print(f"[authz-api] Failed to fetch outgoing delegations: {e}", flush=True)

    # Fetch incoming delegations to principal (filtered by workflow_id if provided)
    # The delegation API returns both workflow-specific and general (workflow_id IS NULL) delegations
    try:
        params = {"delegate_id": principal_id, "include_expired": "false"}
        if workflow_id:
            params["workflow_id"] = workflow_id

        response = requests.get(
            f"{_DELEGATION_API_BASE_URL.rstrip('/')}/v1/delegations",
            params=params,
            headers=headers,
            timeout=_DELEGATION_API_TIMEOUT_SECONDS,
            verify=False,
        )

        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and "delegations" in data:
                for d in data.get("delegations", []):
                    key = (
                        d.get("principal_id"),
                        d.get("delegate_id"),
                        d.get("workflow_id"),
                    )
                    if key not in seen_keys:
                        delegations.append(d)
                        seen_keys.add(key)
    except Exception as e:
        print(f"[authz-api] Failed to fetch incoming delegations: {e}", flush=True)

    return delegations


def evaluate_request_with_opa(
    *,
    opa_client: OpaClient,
    authzen_request: dict[str, Any],
    delegations_data: Optional[List[Dict[str, Any]]] = None,
    owner_attributes: Optional[Dict[str, Any]] = None,
) -> EvaluateResult:
    input_document = build_opa_input(
        authzen_request=authzen_request,
        delegations_data=delegations_data,
        owner_attributes=owner_attributes,
    )

    try:
        is_allowed = opa_client.evaluate_allow(input_document=input_document)
    except Exception:
        is_allowed = False

    try:
        reasons = opa_client.evaluate_reasons(input_document=input_document)
    except Exception:
        reasons = []

    return EvaluateResult(
        decision="allow" if is_allowed else "deny",
        reason_codes=reasons,
        advice=[],
    )


def validate_authzen_request(authzen_request: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    # Validate that a request is AuthZEN compliant.
    #
    # Args:
    #     authzen_request: The request body to validate
    #
    # Returns:
    #     Tuple of (principal_id, validated_context) where:
    #     - principal_id: The principal ID from context.principal.id
    #     - validated_context: The context dict with principal
    #
    # Raises:
    #     ValueError: If the request is not AuthZEN compliant
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

    # Validate action
    action = authzen_request.get("action", {})
    if not action or not isinstance(action, dict):
        raise ValueError("Request must be AuthZEN compliant: action is required")
    
    action_name = action.get("name")
    if not action_name or not isinstance(action_name, str) or not action_name.strip():
        raise ValueError("Request must be AuthZEN compliant: action.name is required")
    
    # Sanitize and validate action name
    if security:
        action_name = security.sanitize_string(action_name.strip(), 255)
    else:
        action_name = action_name.strip()
    
    if action_name not in ALLOWED_ACTIONS:
        raise ValueError(f"Invalid action name: {action_name}. Allowed actions: {', '.join(sorted(ALLOWED_ACTIONS))}")

    return principal_id.strip(), context


def _extract_owner_id(authzen_request: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    # Extract owner_id and workflow_id from AuthZEN request.
    #
    # Returns:
    #     Tuple of (owner_id, workflow_id) or (None, None) if not found
    request_resource = authzen_request.get("resource", {})
    resource_properties = request_resource.get("properties", {})
    owner = resource_properties.get("owner")
    
    if not isinstance(owner, dict):
        return None, None
    
    owner_id = owner.get("id")
    # Get workflow_id from properties (for workflow_item resources) or from resource.id (for workflow resources)
    workflow_id = resource_properties.get("workflow_id") or request_resource.get("id")
    
    return (str(owner_id) if owner_id else None), (str(workflow_id) if workflow_id else None)


def _fetch_delegations(owner_id: str, principal_id: str, workflow_id: Optional[str]) -> Optional[List[Dict[str, Any]]]:
    # Fetch delegation data from delegation-api.
    if not security:
        return None
    
    service_token = security.get_service_token()
    if not service_token:
        return None
    
    try:
        return fetch_delegations_for_opa(
            bearer_token=service_token,
            owner_id=owner_id,
            principal_id=principal_id,
            workflow_id=workflow_id,
        )
    except Exception as e:
        print(f"[authz-api] Failed to fetch delegations: {e}", flush=True)
        return None


def _fetch_owner_attributes(owner_id: str) -> Optional[Dict[str, Any]]:
    # Fetch owner's autobook attributes and persona from Keycloak.
    if not profile:
        return None
    
    try:
        return profile.fetch_attributes(owner_id)
    except Exception as e:
        print(f"[authz-api] Failed to fetch owner attributes: {e}", flush=True)
        return None


def evaluate_authorization_request(
    authzen_request: dict[str, Any],
) -> EvaluateResult:
    # Evaluate an authorization request end-to-end.
    #
    # This function handles the complete authorization flow:
    # 1. Validates AuthZEN compliance
    # 2. Fetches delegation data (if resource has owner)
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
    
    principal_id, context = validate_authzen_request(authzen_request)
    
    # Extract owner and workflow information
    owner_id, workflow_id = _extract_owner_id(authzen_request)
    
    # Fetch delegation data and owner attributes (PIP - Policy Information Point)
    delegations_data = None
    owner_attributes = None
    
    if owner_id:
        delegations_data = _fetch_delegations(owner_id, principal_id, workflow_id)
        owner_attributes = _fetch_owner_attributes(owner_id)
    
    # Evaluate request with OPA
    return evaluate_request_with_opa(
        opa_client=_OPA_CLIENT,
        authzen_request=authzen_request,
        delegations_data=delegations_data,
        owner_attributes=owner_attributes,
    )


