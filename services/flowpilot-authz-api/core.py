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
from typing import Any, Dict, List, Optional

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


def fetch_owner_attributes_from_keycloak(
    *,
    keycloak_base_url: str,
    keycloak_realm: str,
    keycloak_admin_username: str,
    keycloak_admin_password: str,
    owner_id: str,
    verify_tls: bool = False,
    timeout_seconds: int = 10,
) -> Dict[str, Any]:
    """
    Fetch owner's autobook attributes from Keycloak admin API.
    
    Args:
        keycloak_base_url: Keycloak base URL (e.g., https://keycloak:8443)
        keycloak_realm: Keycloak realm name
        keycloak_admin_username: Keycloak admin username
        keycloak_admin_password: Keycloak admin password
        owner_id: User ID (sub) to fetch attributes for
        verify_tls: Whether to verify TLS certificates
        timeout_seconds: Request timeout in seconds
        
    Returns:
        Dictionary with autobook attributes (autobook_consent, autobook_price, etc.)
        Returns empty dict if fetch fails (will use defaults)
    """
    try:
        # Get admin token
        token_url = f"{keycloak_base_url.rstrip('/')}/realms/master/protocol/openid-connect/token"
        token_payload = {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": keycloak_admin_username,
            "password": keycloak_admin_password,
        }
        
        token_response = requests.post(token_url, data=token_payload, timeout=timeout_seconds, verify=verify_tls)
        if token_response.status_code != 200:
            print(f"[authz-api] Failed to get Keycloak admin token: {token_response.text}", flush=True)
            return {}
        
        access_token = token_response.json().get("access_token")
        if not access_token:
            print(f"[authz-api] Token response did not contain access_token", flush=True)
            return {}
        
        # Fetch user by ID from Keycloak
        user_url = f"{keycloak_base_url.rstrip('/')}/admin/realms/{keycloak_realm}/users/{owner_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        user_response = requests.get(user_url, headers=headers, timeout=timeout_seconds, verify=verify_tls)
        if user_response.status_code != 200:
            print(f"[authz-api] Failed to fetch owner user from Keycloak: {user_response.text}", flush=True)
            return {}
        
        user_data = user_response.json()
        attributes = user_data.get("attributes") or {}
        
        # Extract autobook attributes (Keycloak returns them as lists)
        result = {}
        for attr_name in ["autobook_consent", "autobook_price", "autobook_leadtime", "autobook_risklevel"]:
            attr_value = attributes.get(attr_name)
            if isinstance(attr_value, list) and len(attr_value) > 0:
                result[attr_name] = attr_value[0]
            elif attr_value:
                result[attr_name] = attr_value
        
        return result
    except Exception as e:
        print(f"[authz-api] Exception fetching owner attributes: {e}", flush=True)
        return {}


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
        owner_attributes: Optional owner's autobook attributes (used when principal has persona="travel-agent")
    """
    request_context = (authzen_request.get("context") or {})
    request_resource = (authzen_request.get("resource") or {})
    request_action = (authzen_request.get("action") or {})

    resource_properties = coerce_dict(request_resource.get("properties"))

    # Extract principal and claims from AuthZEN context.principal
    principal = request_context.get("principal") or {}
    principal_sub = principal.get("id", "")
    principal_claims = coerce_dict(principal.get("claims", {}))
    
    # Extract owner from resource properties
    owner_props = coerce_dict(resource_properties.get("owner"))
    owner_id = owner_props.get("id") if owner_props else None
    
    # Check if principal has persona="travel-agent" - if so, use owner's attributes
    principal_persona = principal.get("persona")
    use_owner_attributes = (principal_persona == "travel-agent" and owner_id and owner_attributes)
    
    # Choose which claims to use: owner's if travel-agent persona, otherwise principal's
    if use_owner_attributes:
        # Use owner's attributes (travel-agent acting on behalf of owner)
        autobook_consent = normalize_yes_no_to_bool(owner_attributes.get("autobook_consent"), DEFAULT_AUTOBOOK_CONSENT)
        autobook_price = to_int(owner_attributes.get("autobook_price"), DEFAULT_AUTOBOOK_PRICE)
        autobook_leadtime = to_int(owner_attributes.get("autobook_leadtime"), DEFAULT_AUTOBOOK_LEADTIME)
        autobook_risklevel = to_int(owner_attributes.get("autobook_risklevel"), DEFAULT_AUTOBOOK_RISKLEVEL)
        # Build a claims dict from owner attributes for consistency
        effective_claims = {
            "autobook_consent": owner_attributes.get("autobook_consent", DEFAULT_AUTOBOOK_CONSENT),
            "autobook_price": owner_attributes.get("autobook_price", str(DEFAULT_AUTOBOOK_PRICE)),
            "autobook_leadtime": owner_attributes.get("autobook_leadtime", str(DEFAULT_AUTOBOOK_LEADTIME)),
            "autobook_risklevel": owner_attributes.get("autobook_risklevel", str(DEFAULT_AUTOBOOK_RISKLEVEL)),
        }
    else:
        # Use principal's attributes (normal case)
        autobook_consent = normalize_yes_no_to_bool(principal_claims.get("autobook_consent"), DEFAULT_AUTOBOOK_CONSENT)
        autobook_price = to_int(principal_claims.get("autobook_price"), DEFAULT_AUTOBOOK_PRICE)
        autobook_leadtime = to_int(principal_claims.get("autobook_leadtime"), DEFAULT_AUTOBOOK_LEADTIME)
        autobook_risklevel = to_int(principal_claims.get("autobook_risklevel"), DEFAULT_AUTOBOOK_RISKLEVEL)
        effective_claims = principal_claims

    opa_input = {
        "user": {
            "sub": principal_sub,  # Still use principal_sub for delegation checks in OPA
            "autobook_consent": autobook_consent,
            "autobook_price": autobook_price,
            "autobook_leadtime": autobook_leadtime,
            "autobook_risklevel": autobook_risklevel,
            "claims": effective_claims,
        },
        "action": request_action,
        "resource": {
            "workflow_id": request_resource.get("id"),  # Pass workflow_id for delegation scope matching
            "planned_price": resource_properties.get("planned_price"),
            "departure_date": resource_properties.get("departure_date"),
            "airline_risk_score": resource_properties.get("airline_risk_score"),
            "owner_id": owner_id,
        },
        "context": request_context,
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
    seen_keys: set[tuple[str, str, Optional[str]]] = set()  # Track (principal_id, delegate_id, workflow_id) to deduplicate
    
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
                    key = (d.get("principal_id"), d.get("delegate_id"), d.get("workflow_id"))
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
                    key = (d.get("principal_id"), d.get("delegate_id"), d.get("workflow_id"))
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
