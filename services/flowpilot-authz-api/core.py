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

from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from utils import http_post_json, build_timeouts, to_int

# Default values for autobook attributes when not present in Keycloak token claims
DEFAULT_AUTOBOOK_CONSENT = "No"  # String value from Keycloak (will be normalized to False)
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
        result = self._post_data(path=f"{self._config.package}/{self._config.allow_rule}", input_document=input_document)
        # OPA data API: {"result": <value>}
        return bool(result.get("result", False))

    def evaluate_reasons(self, input_document: dict[str, Any]) -> list[str]:
        result = self._post_data(path=f"{self._config.package}/{self._config.reason_rule}", input_document=input_document)
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


def coerce_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def normalize_yes_no_to_bool(value: Any, default: bool) -> bool:
    """
    Convert common string/primitive representations to boolean.
    True: "yes", "y", "true", "1", "on" (case-insensitive)
    False: any other present value
    Default applied only when value is None/empty.
    """
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return default
        return normalized in {"yes", "y", "true", "t", "1", "on"}

    return bool(value)


def build_opa_input(
    *,
    authzen_request: dict[str, Any],
) -> dict[str, Any]:
    """
    Build OPA input document from AuthZEN request.
    
    Args:
        authzen_request: AuthZEN-compliant request body with context.principal containing claims
    """
    request_context = (authzen_request.get("context") or {})
    request_resource = (authzen_request.get("resource") or {})
    request_action = (authzen_request.get("action") or {})

    resource_properties = coerce_dict(request_resource.get("properties"))

    # Extract principal and claims from AuthZEN context.principal
    principal = request_context.get("principal") or {}
    principal_sub = principal.get("id", "")
    principal_claims = coerce_dict(principal.get("claims", {}))

    return {
        "user": {
            "sub": principal_sub,
            "autobook_consent": normalize_yes_no_to_bool(principal_claims.get("autobook_consent"), DEFAULT_AUTOBOOK_CONSENT),
            "autobook_price": to_int(principal_claims.get("autobook_price"), DEFAULT_AUTOBOOK_PRICE),
            "autobook_leadtime": to_int(principal_claims.get("autobook_leadtime"), DEFAULT_AUTOBOOK_LEADTIME), 
            "autobook_risklevel": to_int(principal_claims.get("autobook_risklevel"), DEFAULT_AUTOBOOK_RISKLEVEL),
            "claims": principal_claims,
        },
        "action": request_action,
        "resource": {
            "planned_price": resource_properties.get("planned_price"),
            "departure_date": resource_properties.get("departure_date"),
            "airline_risk_score": resource_properties.get("airline_risk_score"),
        },
        "context": request_context,
    }


def validate_delegation(
    *,
    base_url: str,
    bearer_token: str,
    principal_id: str,
    delegate_id: str,
    workflow_id: Optional[str],
    timeout_seconds: int = 5,
) -> Dict[str, Any]:
    """
    Call the delegation-api validate endpoint with clear errors so authz-api can fail closed deterministically.
    
    Args:
        base_url: Base URL of the delegation API service
        bearer_token: Service token for authenticating with delegation API
        principal_id: Principal ID (user who owns the resource/workflow)
        delegate_id: Delegate ID (user or agent attempting to act)
        workflow_id: Optional workflow ID to scope the delegation check
        timeout_seconds: Request timeout in seconds
        
    Returns:
        Dictionary with 'valid' boolean and 'delegation_chain' list
        
    Raises:
        ValueError: If base_url or bearer_token is invalid
        RuntimeError: If delegation API returns an error or unexpected response
    """
    if not base_url or not base_url.strip():
        raise ValueError("base_url must be a non-empty string")
    if not bearer_token or not bearer_token.strip():
        raise ValueError("bearer_token must be a non-empty string")

    params: Dict[str, str] = {"principal_id": principal_id, "delegate_id": delegate_id}
    if workflow_id is not None and workflow_id.strip():
        params["workflow_id"] = workflow_id.strip()

    headers = {"Authorization": f"Bearer {bearer_token.strip()}"}
    response = requests.get(
        f"{base_url.rstrip('/')}/v1/delegations/validate",
        params=params,
        headers=headers,
        timeout=timeout_seconds,
        verify=False,  # Allow self-signed certs for local dev
    )

    if response.status_code != 200:
        raise RuntimeError(f"Delegation validate failed ({response.status_code}): {response.text}")

    data = response.json()
    if not isinstance(data, dict) or "valid" not in data:
        raise RuntimeError(f"Unexpected response from delegation-api: {data}")

    return data


def evaluate_request_with_opa(
    *,
    opa_client: OpaClient,
    authzen_request: dict[str, Any],
) -> EvaluateResult:
    input_document = build_opa_input(
        authzen_request=authzen_request,
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
