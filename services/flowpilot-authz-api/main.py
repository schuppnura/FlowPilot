"""
FlowPilot AuthZ API (OPA-backed, no ***REMOVED***).

This module implements the REST endpoints defined in flowpilot-authz.openapi.yaml.

OPA integration
- This service calls an OPA server over HTTP.
- Configure with env vars:
  - OPA_URL (default: http://opa:8181)
  - OPA_PACKAGE (default: auto_book)

Where to set these:
- In docker-compose.yml under the flowpilot-authz-api service:
    environment:
      - OPA_URL=http://opa:8181
      - OPA_PACKAGE=auto_book
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Optional

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import security
from core import OpaClient, OpaConfig, evaluate_request_with_opa

app = FastAPI(title="FlowPilot AuthZ API", version="1.0.0")

bearer_scheme = HTTPBearer(auto_error=True)


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


def get_token_claims(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict[str, Any]:
    # For development: skip token validation if AUTH_ENABLED=false
    auth_enabled = os.getenv("AUTH_ENABLED", "true").lower() == "true"
    if not auth_enabled:
        return {"sub": "demo_user", "active": True}
    
    return security.verify_token(credentials)


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
        principal_sub = resolve_principal_sub(request_body=request_body, token_claims=token_claims)
    except HTTPException as exc:
        raise exc

    # Optional: in future load profile/preferences from your IdP or a profile service.
    profile: dict[str, Any] = {
        "preferences": {},
        "policy_parameters": {},
    }

    result = evaluate_request_with_opa(
        opa_client=OPA_CLIENT,
        request_body=request_body,
        principal_sub=principal_sub,
        token_claims=token_claims,
        profile=profile,
    )

    return {
        "decision": result.decision,
        "reason_codes": result.reason_codes,
        "advice": result.advice,
    }


@app.get("/v1/profiles/{principal_sub}")
def get_profile(principal_sub: str, token_claims: dict[str, Any] = Depends(get_token_claims)) -> dict[str, Any]:
    # Placeholder until you wire this to Keycloak / a profile service.
    return {
        "principal_sub": principal_sub,
        "policy_parameters": {},
        "identity_presence": {"present": True, "source": "token" if token_claims else "unknown"},
    }


@app.get("/v1/policy-parameters/{principal_sub}")
def get_policy_parameters(principal_sub: str, token_claims: dict[str, Any] = Depends(get_token_claims)) -> dict[str, Any]:
    return {"principal_sub": principal_sub, "policy_parameters": {}}


@app.get("/v1/identity-presence/{principal_sub}")
def get_identity_presence(principal_sub: str, token_claims: dict[str, Any] = Depends(get_token_claims)) -> dict[str, Any]:
    return {"principal_sub": principal_sub, "identity_presence": {"present": True, "source": "token" if token_claims else "unknown"}}


@app.post("/v1/graph/workflows")
def post_graph_workflows(
    request_body: dict[str, Any] = Body(...),
    token_claims: dict[str, Any] = Depends(get_token_claims),
) -> dict[str, Any]:
    # Minimal stub: acknowledge graph creation so the rest of the system can evolve.
    workflow_id = request_body.get("workflow_id") or str(uuid.uuid4())
    return {"status": "created", "workflow_id": workflow_id}


@app.post("/v1/graph/workflows/{workflow_id}/items")
def post_graph_workflow_items(
    workflow_id: str,
    request_body: dict[str, Any] = Body(...),
    token_claims: dict[str, Any] = Depends(get_token_claims),
) -> dict[str, Any]:
    item_id = request_body.get("item_id") or str(uuid.uuid4())
    return {"status": "created", "workflow_id": workflow_id, "item_id": item_id}


@app.post("/v1/graph/workflow-items")
def post_graph_workflow_items_legacy(
    request_body: dict[str, Any] = Body(...),
    token_claims: dict[str, Any] = Depends(get_token_claims),
) -> dict[str, Any]:
    # Legacy endpoint for services-api compatibility
    workflow_item_id = request_body.get("workflow_item_id") or str(uuid.uuid4())
    workflow_id = request_body.get("workflow_id", "unknown")
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
    )
