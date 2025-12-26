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

import argparse
import uvicorn

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials

import security
import api_logging
from core import OpaClient, OpaConfig, evaluate_request_with_opa, fetch_delegations_for_opa
import core


app = FastAPI(title="FlowPilot AuthZ API", version="1.0.0")

# Add security middlewares before defining routes
app.add_middleware(security.SecurityHeadersMiddleware)
app.add_middleware(security.RequestSizeLimiterMiddleware, max_size=security.get_max_request_size())

# Custom exception handler for HTTPException to log authentication errors
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code in (401, 403):
        # Log authentication/authorization errors for debugging
        auth_header = request.headers.get("authorization", "")
        auth_preview = auth_header[:50] + "..." if len(auth_header) > 50 else auth_header or "None"
        print(f"[authz-api HTTPException {exc.status_code}] Path: {request.url.path}, Detail: {exc.detail}, Auth: {auth_preview}", flush=True)
        # Also log full request details
        print(f"[authz-api HTTPException] Full request headers: {dict(request.headers)}", flush=True)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc.detail) if hasattr(exc, 'detail') else str(exc)},
        headers=exc.headers if hasattr(exc, 'headers') else {}
    )

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
DELEGATION_API_BASE_URL = read_env_string("DELEGATION_API_BASE_URL", "http://delegation-api:8000")
KEYCLOAK_BASE_URL = read_env_string("KEYCLOAK_BASE_URL", "https://keycloak:8443")
KEYCLOAK_REALM = read_env_string("KEYCLOAK_REALM", "flowpilot")


def get_token_claims(token_claims: dict[str, Any] = Depends(security.verify_token)) -> dict[str, Any]:
    # Return JWT claims from validated token
    # verify_token will raise HTTPException if token is invalid, so if we get here, token is valid
    return token_claims


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
    request: Request,
    request_body: dict[str, Any] = Body(...),
    token_claims: dict[str, Any] = Depends(get_token_claims),
) -> dict[str, Any]:
    
    api_logging.log_api_request("POST", "/v1/evaluate", request_body=request_body, token_claims=token_claims, request=request)
    
    # Sanitize all input before processing
    try:
        sanitized_body = security.sanitize_request_json_payload(request_body)
    except security.InputValidationError as exc:
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        api_logging.log_api_response("POST", "/v1/evaluate", 400, error=error_detail)
        raise HTTPException(
            status_code=400,
            detail=error_detail
        ) from exc

    # Evaluate the AuthZEN request (business logic is in core.py)
    try:
        result = core.evaluate_authzen_request(
            opa_client=OPA_CLIENT,
            delegation_api_base_url=DELEGATION_API_BASE_URL,
            authzen_request=sanitized_body,
        )
    except ValueError as exc:
        # Handle validation errors from core logic
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        api_logging.log_api_response("POST", "/v1/evaluate", 400, error=error_detail)
        raise HTTPException(
            status_code=400,
            detail=error_detail
        ) from exc

    response_body = {
        "decision": result.decision,
        "reason_codes": result.reason_codes,
        "advice": result.advice,
    }
    
    # Log response
    api_logging.log_api_response("POST", "/v1/evaluate", 200, response_body=response_body)
    
    return response_body


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
    request: Request,
    request_body: dict[str, Any] = Body(...),
    token_claims: dict[str, Any] = Depends(get_token_claims),
) -> dict[str, Any]:
    # Minimal stub: acknowledge graph creation so the rest of the system can evolve.
    try:
        api_logging.log_api_request("POST", "/v1/graph/workflows", request_body=request_body, token_claims=token_claims, request=request)
        
        # Sanitize input
        sanitized_body = security.sanitize_request_json_payload(request_body)
        workflow_id = sanitized_body.get("workflow_id") or str(uuid.uuid4())
        
        result = {"status": "created", "workflow_id": workflow_id}
        
        api_logging.log_api_response("POST", "/v1/graph/workflows", 200, response_body=result)
        
        return result
    except security.InputValidationError as exc:
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        api_logging.log_api_response("POST", "/v1/graph/workflows", 400, error=error_detail)
        raise HTTPException(
            status_code=400,
            detail=error_detail
        ) from exc
    except HTTPException as exc:
        api_logging.log_api_response("POST", "/v1/graph/workflows", exc.status_code, error=str(exc.detail) if hasattr(exc, 'detail') else str(exc))
        raise


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
