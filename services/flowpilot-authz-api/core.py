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
from typing import Any, Optional

from utils import http_post_json, build_timeouts


@dataclass(frozen=True)
class OpaConfig:
    base_url: str
    package: str
    allow_rule: str = "allow"
    reason_rule: str = "reason"
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


def build_opa_input(
    *,
    request_body: dict[str, Any],
    principal_sub: str,
    token_claims: Optional[dict[str, Any]] = None,
    profile: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Map the OpenAPI EvaluateRequest into the Rego input your policy expects.

    Policy (auto_book.rego) expects:
    - input.user.auto_book_consent
    - input.user.auto_book_max_cost_eur
    - input.user.auto_book_min_days_advance
    - input.user.auto_book_max_airline_risk
    - input.resource.planned_price
    - input.resource.departure_date
    - input.resource.airline_risk_score
    """
    request_context = (request_body.get("context") or {})
    request_resource = (request_body.get("resource") or {})
    request_action = (request_body.get("action") or {})

    profile = profile or {}
    preferences = profile.get("preferences") or {}
    policy_parameters = profile.get("policy_parameters") or {}

    # Extract resource properties for OPA
    resource_properties = request_resource.get("properties") or {}
    
    # Build user object with flattened auto_book parameters
    # Use policy_parameters first, then fall back to preferences, then defaults
    user_data: dict[str, Any] = {
        "sub": principal_sub,
        "auto_book_consent": policy_parameters.get("auto_book_consent", preferences.get("auto_book_consent", True)),
        "auto_book_max_cost_eur": policy_parameters.get("auto_book_max_cost_eur", preferences.get("auto_book_max_cost_eur", 5000)),
        "auto_book_min_days_advance": policy_parameters.get("auto_book_min_days_advance", preferences.get("auto_book_min_days_advance", 0)),
        "auto_book_max_airline_risk": policy_parameters.get("auto_book_max_airline_risk", preferences.get("auto_book_max_airline_risk", 10)),
    }
    
    if token_claims is not None:
        user_data["token"] = token_claims
    
    # Build resource object for OPA with the fields from properties
    resource_data: dict[str, Any] = {
        "planned_price": resource_properties.get("planned_price"),
        "departure_date": resource_properties.get("departure_date"),
        "airline_risk_score": resource_properties.get("airline_risk_score"),
    }

    opa_input: dict[str, Any] = {
        "user": user_data,
        "action": request_action,
        "resource": resource_data,
        "context": request_context,
    }

    return opa_input


def evaluate_request_with_opa(
    *,
    opa_client: OpaClient,
    request_body: dict[str, Any],
    principal_sub: str,
    token_claims: Optional[dict[str, Any]] = None,
    profile: Optional[dict[str, Any]] = None,
) -> EvaluateResult:
    input_document = build_opa_input(
        request_body=request_body,
        principal_sub=principal_sub,
        token_claims=token_claims,
        profile=profile,
    )

    try:
        is_allowed = opa_client.evaluate_allow(input_document=input_document)
    except Exception:
        # Fail closed
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
