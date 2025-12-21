"""
FlowPilot AuthZ API (OPA-backed, no ***REMOVED***).

This module implements the REST endpoints defined in flowpilot-authz.openapi.yaml.

IMPORTANT: This service is DOMAIN-AGNOSTIC. It provides generic authorization
evaluation that works with any domain (travel, nursing, business events, etc.).
The domain-specific policy logic lives in the OPA policies, not in this API.

OPA integration
- This service calls an OPA server over HTTP.
- Configure with env vars:
  - OPA_URL (default: http://opa:8181)
  - OPA_PACKAGE (default: auto_book) - This is travel-specific by default, but
    can be configured to any policy package for other domains.

Where to set these:
- In docker-compose.yml under the flowpilot-authz-api service:
    environment:
      - OPA_URL=http://opa:8181
      - OPA_PACKAGE=auto_book  # Change to domain-specific package for other domains
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Optional

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials

import security
from core import OpaClient, OpaConfig, evaluate_request_with_opa

app = FastAPI(title="FlowPilot AuthZ API", version="1.0.0")

# Add security middlewares before defining routes
app.add_middleware(security.SecurityHeadersMiddleware)
app.add_middleware(security.RequestSizeLimiterMiddleware, max_size=security.get_max_request_size())

# Environment flag for detailed error messages (disable in production)
INCLUDE_ERROR_DETAILS = os.environ.get("INCLUDE_ERROR_DETAILS", "1") == "1"


def read_env_string(name: str, default_value: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default_value
    return value.strip()


def build_opa_client() -> OpaClient:
    config = OpaConfig(
        base_url=read_env_string("OPA_URL", "http://opa:8181"),
        package=read_env_string("OPA_PACKAGE", "auto_book"),
    )
    return OpaClient(config=config)


OPA_CLIENT = build_opa_client()


# In-memory profile store (for demo purposes)
# In production, this would be backed by a database or identity provider
class InMemoryProfileStore:
    def __init__(self):
        self._profiles: dict[str, dict[str, Any]] = {}
        self._default_policy_parameters = {
            "auto_book_consent": False,  # Default to false - must be set in Keycloak
            "auto_book_max_cost_eur": 5000,
            "auto_book_min_days_advance": 0,
            "auto_book_max_airline_risk": 10,
        }
    
    def get_profile(self, principal_sub: str) -> dict[str, Any]:
        if principal_sub not in self._profiles:
            # Auto-create profile with defaults
            self._profiles[principal_sub] = {
                "principal_sub": principal_sub,
                "policy_parameters": dict(self._default_policy_parameters),
            }
        return self._profiles[principal_sub]
    
    def update_policy_parameters(self, principal_sub: str, parameters: dict[str, Any]) -> dict[str, Any]:
        profile = self.get_profile(principal_sub)
        profile["policy_parameters"].update(parameters)
        return profile


PROFILE_STORE = InMemoryProfileStore()


def get_token_claims(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security.verify_token)) -> dict[str, Any]:
    # Return JWT claims from validated token
    return credentials if credentials else {}


def resolve_principal_sub(
    request_body: dict[str, Any],
    token_claims: Optional[dict[str, Any]],
) -> str:
    # 1) Prefer explicit context.principal.id in the request
    context = request_body.get("context") or {}
    principal = context.get("principal") or {}
    principal_id = principal.get("id")
    if isinstance(principal_id, str) and principal_id.strip():
        return principal_id.strip()

    # 2) Fall back to JWT sub
    if token_claims is not None:
        sub = token_claims.get("sub")
        if isinstance(sub, str) and sub.strip():
            return sub.strip()

    # 3) Fail closed: require a principal
    raise HTTPException(status_code=400, detail={"message": "principal_sub missing", "code": "INVALID_REQUEST"})


def build_error_response(status_code: int, message: str, code: str = "ERROR", details: Optional[dict[str, Any]] = None) -> JSONResponse:
    body: dict[str, Any] = {"message": message, "code": code}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status_code, content=body)


@app.get("/health")
def get_health() -> dict[str, Any]:
    return {"status": "ok"}


@app.post("/v1/evaluate")
def post_evaluate(
    request_body: dict[str, Any] = Body(...),
    token_claims: dict[str, Any] = Depends(get_token_claims),
) -> dict[str, Any]:
    try:
        # Sanitize all input before processing
        sanitized_body = security.sanitize_request_json_payload(request_body)
        
        principal_sub = resolve_principal_sub(request_body=sanitized_body, token_claims=token_claims)
    except security.InputValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        ) from exc
    except HTTPException as exc:
        raise exc

    # Extract user token from context if provided
    user_token_claims: Optional[dict[str, Any]] = None
    context = sanitized_body.get("context", {})
    user_token = context.get("user_token")
    if user_token and isinstance(user_token, str):
        try:
            # Decode and validate the user token
            user_token_claims = security.verify_token_string(user_token)
        except Exception:
            # If token is invalid, continue without user claims
            pass
    
    # Load user profile with policy parameters
    profile = PROFILE_STORE.get_profile(principal_sub)

    # Use user token claims if available, otherwise fall back to agent token claims
    effective_token_claims = user_token_claims if user_token_claims else token_claims

    result = evaluate_request_with_opa(
        opa_client=OPA_CLIENT,
        request_body=sanitized_body,
        principal_sub=principal_sub,
        token_claims=effective_token_claims,
        profile=profile,
    )

    return {
        "decision": result.decision,
        "reason_codes": result.reason_codes,
        "advice": result.advice,
    }


@app.get("/v1/profiles/{principal_sub}")
def get_profile(principal_sub: str, token_claims: dict[str, Any] = Depends(get_token_claims)) -> dict[str, Any]:
    try:
        # Validate path parameter
        principal_sub = security.sanitize_string(principal_sub, max_length=255)
    except security.InputValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        ) from exc
    
    profile = PROFILE_STORE.get_profile(principal_sub)
    return {
        "principal_sub": principal_sub,
        "policy_parameters": profile.get("policy_parameters", {}),
        "identity_presence": {"present": True, "source": "token" if token_claims else "unknown"},
    }


@app.get("/v1/policy-parameters/{principal_sub}")
def get_policy_parameters(principal_sub: str, token_claims: dict[str, Any] = Depends(get_token_claims)) -> dict[str, Any]:
    try:
        # Validate path parameter
        principal_sub = security.sanitize_string(principal_sub, max_length=255)
    except security.InputValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        ) from exc
    
    profile = PROFILE_STORE.get_profile(principal_sub)
    return {"principal_sub": principal_sub, "policy_parameters": profile.get("policy_parameters", {})}


@app.patch("/v1/profiles/{principal_sub}/policy-parameters")
def update_policy_parameters(
    principal_sub: str,
    request_body: dict[str, Any] = Body(...),
    token_claims: dict[str, Any] = Depends(get_token_claims),
) -> dict[str, Any]:
    try:
        # Validate path parameter and sanitize body
        principal_sub = security.sanitize_string(principal_sub, max_length=255)
        sanitized_body = security.sanitize_request_json_payload(request_body)
        parameters = sanitized_body.get("parameters", {})
        if not isinstance(parameters, dict):
            raise security.InputValidationError("parameters must be a dictionary")
    except security.InputValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        ) from exc
    
    profile = PROFILE_STORE.update_policy_parameters(principal_sub, parameters)
    return {"principal_sub": principal_sub, "policy_parameters": profile.get("policy_parameters", {})}


@app.get("/v1/identity-presence/{principal_sub}")
def get_identity_presence(principal_sub: str, token_claims: dict[str, Any] = Depends(get_token_claims)) -> dict[str, Any]:
    try:
        # Validate path parameter
        principal_sub = security.sanitize_string(principal_sub, max_length=255)
    except security.InputValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        ) from exc
    
    return {"principal_sub": principal_sub, "identity_presence": {"present": True, "source": "token" if token_claims else "unknown"}}


@app.post("/v1/graph/workflows")
def post_graph_workflows(
    request_body: dict[str, Any] = Body(...),
    token_claims: dict[str, Any] = Depends(get_token_claims),
) -> dict[str, Any]:
    # Minimal stub: acknowledge graph creation so the rest of the system can evolve.
    try:
        # Sanitize input
        sanitized_body = security.sanitize_request_json_payload(request_body)
        workflow_id = sanitized_body.get("workflow_id") or str(uuid.uuid4())
    except security.InputValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        ) from exc
    
    return {"status": "created", "workflow_id": workflow_id}


@app.post("/v1/graph/workflows/{workflow_id}/items")
def post_graph_workflow_items(
    workflow_id: str,
    request_body: dict[str, Any] = Body(...),
    token_claims: dict[str, Any] = Depends(get_token_claims),
) -> dict[str, Any]:
    try:
        # Validate path parameter and sanitize body
        workflow_id = security.validate_id(workflow_id, "workflow_id", max_length=255)
        sanitized_body = security.sanitize_request_json_payload(request_body)
        item_id = sanitized_body.get("item_id") or str(uuid.uuid4())
    except security.InputValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        ) from exc
    
    return {"status": "created", "workflow_id": workflow_id, "item_id": item_id}


@app.post("/v1/graph/workflow-items")
def post_graph_workflow_items_legacy(
    request_body: dict[str, Any] = Body(...),
    token_claims: dict[str, Any] = Depends(get_token_claims),
) -> dict[str, Any]:
    # Legacy endpoint for domain-services-api compatibility
    try:
        # Sanitize input
        sanitized_body = security.sanitize_request_json_payload(request_body)
        workflow_item_id = sanitized_body.get("workflow_item_id") or str(uuid.uuid4())
        workflow_id = sanitized_body.get("workflow_id", "unknown")
    except security.InputValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        ) from exc
    
    return {"status": "created", "workflow_id": workflow_id, "workflow_item_id": workflow_item_id}


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="FlowPilot AuthZ API")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    args = parser.parse_args()

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        # Security: Limit request body size to prevent memory exhaustion
        limit_max_requests=10000,
        limit_concurrency=100,
        timeout_keep_alive=5,
    )
