"""
Core authorization logic for FlowPilot AuthZ API using OPA (no ***REMOVED***).

Design goals
- Keep policy evaluation simple: call a plain OPA server (HTTP) running in "server mode".
- Keep the AuthZ API responsible for:
  - authenticating callers (via shared security.py)
  - shaping input for the Rego policy
  - mapping OPA outputs into the OpenAPI response schema

Assumptions
- An OPA server is reachable at OPA_URL (default: http://opa:8181).
- The Rego policy package is "auto_book" (configurable via OPA_PACKAGE).
- Policy rules used:
  - data.<package>.allow  -> boolean
  - data.<package>.reason -> set/list of strings (optional)
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from utils import http_post_json, build_timeouts, coerce_int, coerce_dict, coerce_bool

# Default values for autobook attributes when not present in Keycloak token claims
DEFAULT_AUTOBOOK_CONSENT = (
    "No"  # String value from Keycloak (will be normalized to False)
)
DEFAULT_AUTOBOOK_PRICE = 0  # Maximum cost in EUR
DEFAULT_AUTOBOOK_LEADTIME = 10000  # Minimum days in advance
DEFAULT_AUTOBOOK_RISKLEVEL = 0  # Maximum airline risk level


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
    """
    Build OPA input document from AuthZEN request.

    Args:
        authzen_request: AuthZEN-compliant request body with context.principal containing claims
        delegations_data: List of delegation dictionaries fetched from delegation-api (PIP data)
        owner_attributes: Optional owner's autobook attributes (always used if available, regardless of delegation)
    """
    request_context = authzen_request.get("context") or {}
    request_resource = authzen_request.get("resource") or {}
    request_action = authzen_request.get("action") or {}

    resource_properties = coerce_dict(request_resource.get("properties"))

    # Extract principal from AuthZEN context.principal
    principal = request_context.get("principal") or {}
    principal_sub = principal.get("id", "")

    # Extract owner from resource properties
    owner_props = coerce_dict(resource_properties.get("owner"))
    owner_id = owner_props.get("id") if owner_props else None

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

    # Build context with owner information (id, persona, autobook settings)
    # Autobook settings belong to the resource owner, not the principal
    # Use copy.deepcopy to ensure all nested structures (like principal.claims) are preserved
    context_with_owner = copy.deepcopy(request_context)  # Deep copy to preserve all claims and nested structures
    
    # Get persona from owner attributes (may be a list, take first if so)
    owner_persona = owner_attrs.get("persona", "")
    if isinstance(owner_persona, list) and owner_persona:
        owner_persona = owner_persona[0]
    elif not owner_persona:
        owner_persona = ""
    
    context_with_owner["owner"] = {
        "id": owner_id,  # the original creator of the workflow
        "persona": str(owner_persona),
        "autobook_consent": autobook_consent,
        "autobook_price": autobook_price,
        "autobook_leadtime": autobook_leadtime,
        "autobook_risklevel": autobook_risklevel,
    }

    opa_input = {
        "subject": {
            "type": "user",
            "id": principal_sub,  # the actual, current user
        },
        "action": request_action,
        "resource": {
            "workflow_id": request_resource.get("id"),
            "planned_price": resource_properties.get("planned_price"),
            "departure_date": resource_properties.get("departure_date"),
            "airline_risk_score": resource_properties.get("airline_risk_score"),
            "owner_id": owner_id,
        },
        "context": context_with_owner,
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
    base_url: str,
    bearer_token: str,
    owner_id: str,
    principal_id: str,
    workflow_id: Optional[str],
    timeout_seconds: int = 5,
) -> List[Dict[str, Any]]:
    """
    Fetch delegations from delegation-api to pass to OPA for policy evaluation.
    This acts as a PIP (Policy Information Point) - fetching data for OPA to evaluate.

    Args:
        base_url: Base URL of the delegation API service
        bearer_token: Service token for authenticating with delegation API
        owner_id: Owner ID (resource owner)
        principal_id: Principal ID (user attempting to act)
        workflow_id: Optional workflow ID to scope the delegation fetch
        timeout_seconds: Request timeout in seconds

    Returns:
        List of delegation dictionaries for OPA to evaluate

    Raises:
        ValueError: If base_url or bearer_token is invalid
        RuntimeError: If delegation API returns an error
    """
    if not base_url or not base_url.strip():
        raise ValueError("base_url must be a non-empty string")
    if not bearer_token or not bearer_token.strip():
        raise ValueError("bearer_token must be a non-empty string")

    headers = {"Authorization": f"Bearer {bearer_token.strip()}"}
    delegations: List[Dict[str, Any]] = []
    seen_keys: set[tuple[str, str, Optional[str]]] = (
        set()
    )  # Track (principal_id, delegate_id, workflow_id) to deduplicate

    # Fetch ALL outgoing delegations from owner (without workflow filter to get both specific and general)
    # OPA policy will filter by workflow_id during evaluation
    try:
        params: Dict[str, str] = {"principal_id": owner_id, "include_expired": "false"}
        # Don't filter by workflow_id here - fetch all delegations and let OPA filter

        response = requests.get(
            f"{base_url.rstrip('/')}/v1/delegations",
            params=params,
            headers=headers,
            timeout=timeout_seconds,
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

    # Fetch ALL incoming delegations to principal (without workflow filter)
    # OPA policy will filter by workflow_id during evaluation
    try:
        params = {"delegate_id": principal_id, "include_expired": "false"}
        # Don't filter by workflow_id here - fetch all delegations and let OPA filter

        response = requests.get(
            f"{base_url.rstrip('/')}/v1/delegations",
            params=params,
            headers=headers,
            timeout=timeout_seconds,
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
