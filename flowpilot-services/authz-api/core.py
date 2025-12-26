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
import security
import profile
from utils import http_post_json, build_timeouts, coerce_int, coerce_yes_no_to_bool, coerce_date_to_rfc3339

# Default values for autobook attributes when not present in Keycloak token claims
DEFAULT_AUTOBOOK_CONSENT = "No"  # String value from Keycloak (will be coerced to boolean False)
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






def build_opa_input(
    *,
    authzen_request: dict[str, Any],
    delegations_data: Optional[List[Dict[str, Any]]] = None,
    owner_sub: Optional[str] = None,
    owner_persona: Optional[str] = None,
) -> dict[str, Any]:
    """
    Build OPA input document from AuthZEN request.
    
    Args:
        authzen_request: AuthZEN-compliant request body
        delegations_data: List of delegation dictionaries fetched from delegation-api (PIP data)
        owner_sub: Workflow owner's subject ID (from workflow, not from AuthZEN)
        owner_persona: Workflow owner's persona (from workflow, not from AuthZEN)
    """
    request_resource = (authzen_request.get("resource") or {})
    request_action = (authzen_request.get("action") or {})
    request_subject = (authzen_request.get("subject") or {})
    request_context = (authzen_request.get("context") or {})

    resource_properties = coerce_dict(request_resource.get("properties"))

    # Get the actual principal (user) from context.principal, not from subject (which is the agent/service)
    # The subject.id is the agent/service making the call, but context.principal.id is the actual user
    principal_sub = None
    principal_persona = None
    context_principal = request_context.get("principal", {})
    if isinstance(context_principal, dict):
        principal_sub = context_principal.get("id", "")
        principal_persona = context_principal.get("persona")
    
    # If no principal in context, fall back to subject (backward compatibility)
    if not principal_sub:
        principal_sub = request_subject.get("id", "")
    
    # Owner info comes from workflow properties (set by domain-services-api)
    # NOT from AuthZEN context or access token
    owner_id = owner_sub
    
    # Get owner's autobook settings using profile.py
    owner_autobook_settings = {}
    if owner_id:
        try:
            owner_autobook_settings = profile.get_autobook_settings(owner_id)
        except Exception as e:
            print(f"[authz-api] Failed to fetch owner autobook settings: {e}", flush=True)
    
    # Use owner's attributes (workflow owner is the one whose preferences matter)
    autobook_consent = coerce_yes_no_to_bool(owner_autobook_settings.get("autobook_consent"), False)
    autobook_price = coerce_int(owner_autobook_settings.get("autobook_price"), DEFAULT_AUTOBOOK_PRICE)
    autobook_leadtime = coerce_int(owner_autobook_settings.get("autobook_leadtime"), DEFAULT_AUTOBOOK_LEADTIME)
    autobook_risklevel = coerce_int(owner_autobook_settings.get("autobook_risklevel"), DEFAULT_AUTOBOOK_RISKLEVEL)
    
    # Coerce departure_date to RFC3339 format before passing to OPA
    departure_date_raw = resource_properties.get("departure_date")
    departure_date_normalized = coerce_date_to_rfc3339(departure_date_raw) if departure_date_raw else None

    opa_input = {
        "user": {
            "sub": principal_sub,  # Principal (actual user) making the request - used for anti-spoofing and delegation checks
            "persona": principal_persona,  # Principal's selected persona (from context.principal)
            "autobook_consent": autobook_consent,
            "autobook_price": autobook_price,
            "autobook_leadtime": autobook_leadtime,
            "autobook_risklevel": autobook_risklevel,
        },
        "action": request_action,
        "resource": {
            "workflow_id": request_resource.get("id"),  # Pass workflow_id for delegation scope matching
            "planned_price": resource_properties.get("planned_price"),
            "departure_date": departure_date_normalized,  # Already normalized to RFC3339
            "airline_risk_score": resource_properties.get("airline_risk_score"),
            "owner_id": owner_id,  # Workflow owner ID
            "owner_persona": owner_persona,  # Workflow owner's persona (selected when workflow was created)
        },
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
    owner_sub: Optional[str] = None,
    owner_persona: Optional[str] = None,
) -> EvaluateResult:
    input_document = build_opa_input(
        authzen_request=authzen_request,
        delegations_data=delegations_data,
        owner_sub=owner_sub,
        owner_persona=owner_persona,
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


def evaluate_authzen_request(
    *,
    opa_client: OpaClient,
    delegation_api_base_url: str,
    authzen_request: dict[str, Any],
) -> EvaluateResult:
    """
    Evaluate an AuthZEN request with OPA.
    
    This function orchestrates the full evaluation flow:
    1. Extracts principal (subject) and owner info from the request
    2. Fetches delegation data if needed
    3. Evaluates the request with OPA
    4. Returns the evaluation result
    
    Args:
        opa_client: OPA client instance
        delegation_api_base_url: Base URL for delegation API
        authzen_request: AuthZEN-compliant request body
        
    Returns:
        EvaluateResult with decision, reason_codes, and advice
        
    Raises:
        ValueError: If request is missing required fields (subject.id)
    """
    # Get the actual principal (user) from context.principal, not from subject (which is the agent/service)
    # The subject.id is the agent/service making the call, but context.principal.id is the actual user
    request_context = authzen_request.get("context", {})
    context_principal = request_context.get("principal", {})
    principal_id = None
    if isinstance(context_principal, dict):
        principal_id = context_principal.get("id", "")
    
    # If no principal in context, fall back to subject (backward compatibility)
    if not principal_id:
        request_subject = authzen_request.get("subject", {})
        principal_id = request_subject.get("id", "")
    
    if not principal_id or not isinstance(principal_id, str) or not principal_id.strip():
        raise ValueError("Request must have context.principal.id or subject.id (user making the request)")
    
    # Get owner info from resource properties (set by domain-services-api when workflow was created)
    # NOT from AuthZEN context or access token
    request_resource = authzen_request.get("resource", {})
    resource_properties = request_resource.get("properties", {})
    owner = resource_properties.get("owner")
    
    owner_sub = None
    owner_persona = None
    if owner and isinstance(owner, dict):
        owner_sub = owner.get("id")
        owner_persona = owner.get("persona")  # Persona that was selected when workflow was created
    
    # Fetch delegation data for OPA policy evaluation (PIP - Policy Information Point)
    delegations_data = None
    workflow_id_param = request_resource.get("id")
    
    if owner_sub and principal_id:
        # Get service token for delegation-api
        service_token = security.get_service_token()
        if service_token:
            try:
                # Fetch delegations (both outgoing from owner and incoming to principal)
                # This acts as PIP - providing data for OPA to evaluate
                delegations_data = fetch_delegations_for_opa(
                    base_url=delegation_api_base_url,
                    bearer_token=service_token,
                    owner_id=str(owner_sub),
                    principal_id=principal_id,
                    workflow_id=str(workflow_id_param) if workflow_id_param else None,
                )
            except Exception as delegation_error:
                # Log but don't fail - OPA can handle missing delegation data (will deny with reason code)
                print(f"[authz-api] Failed to fetch delegations: {delegation_error}", flush=True)
    
    # Evaluate request with OPA
    return evaluate_request_with_opa(
        opa_client=opa_client,
        authzen_request=authzen_request,
        delegations_data=delegations_data,
        owner_sub=owner_sub,
        owner_persona=owner_persona,
    )
