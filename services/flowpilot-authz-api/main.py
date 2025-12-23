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
from typing import Any, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials

import security
import api_logging
from core import OpaClient, OpaConfig, evaluate_request_with_opa

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


def get_token_claims(token_claims: dict[str, Any] = Depends(security.verify_token)) -> dict[str, Any]:
    # Return JWT claims from validated token
    # verify_token will raise HTTPException if token is invalid, so if we get here, token is valid
    return token_claims


def validate_authzen_request(request_body: dict[str, Any]) -> None:
    """
    Validate that the request body conforms to AuthZEN structure.
    
    Required fields:
    - subject: {type: str, id: str}
    - action: {name: str}
    - resource: {type: str, id: str}
    - context: {principal: {id: str, claims: dict}}
    
    Raises HTTPException with 400 status if validation fails.
    """
    # Validate subject
    subject = request_body.get("subject")
    if not subject or not isinstance(subject, dict):
        raise HTTPException(
            status_code=400,
            detail="Request must be AuthZEN compliant: subject is required and must be an object"
        )
    if not isinstance(subject.get("type"), str) or not subject.get("type").strip():
        raise HTTPException(
            status_code=400,
            detail="Request must be AuthZEN compliant: subject.type is required"
        )
    if not isinstance(subject.get("id"), str) or not subject.get("id").strip():
        raise HTTPException(
            status_code=400,
            detail="Request must be AuthZEN compliant: subject.id is required"
        )
    
    # Validate action
    action = request_body.get("action")
    if not action or not isinstance(action, dict):
        raise HTTPException(
            status_code=400,
            detail="Request must be AuthZEN compliant: action is required and must be an object"
        )
    if not isinstance(action.get("name"), str) or not action.get("name").strip():
        raise HTTPException(
            status_code=400,
            detail="Request must be AuthZEN compliant: action.name is required"
        )
    
    # Validate resource
    resource = request_body.get("resource")
    if not resource or not isinstance(resource, dict):
        raise HTTPException(
            status_code=400,
            detail="Request must be AuthZEN compliant: resource is required and must be an object"
        )
    if not isinstance(resource.get("type"), str) or not resource.get("type").strip():
        raise HTTPException(
            status_code=400,
            detail="Request must be AuthZEN compliant: resource.type is required"
        )
    if not isinstance(resource.get("id"), str) or not resource.get("id").strip():
        raise HTTPException(
            status_code=400,
            detail="Request must be AuthZEN compliant: resource.id is required"
        )
    
    # Validate context.principal
    context = request_body.get("context")
    if not context or not isinstance(context, dict):
        raise HTTPException(
            status_code=400,
            detail="Request must be AuthZEN compliant: context is required and must be an object"
        )
    
    principal = context.get("principal")
    if not principal or not isinstance(principal, dict):
        raise HTTPException(
            status_code=400,
            detail="Request must be AuthZEN compliant: context.principal is required and must be an object"
        )
    
    principal_id = principal.get("id")
    if not isinstance(principal_id, str) or not principal_id.strip():
        raise HTTPException(
            status_code=400,
            detail="Request must be AuthZEN compliant: context.principal.id is required"
        )
    
    if "claims" not in principal:
        raise HTTPException(
            status_code=400,
            detail="Request must be AuthZEN compliant: context.principal.claims is required"
        )
    
    if not isinstance(principal.get("claims"), dict):
        raise HTTPException(
            status_code=400,
            detail="Request must be AuthZEN compliant: context.principal.claims must be an object"
        )


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
    api_logging.log_api_request("POST", "/v1/evaluate", request_body, token_claims, None, request)
    
    # Sanitize input
    try:
        sanitized_body = security.sanitize_request_json_payload(request_body)
    except security.InputValidationError as exc:
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        api_logging.log_api_response("POST", "/v1/evaluate", 400, None, error_detail)
        raise HTTPException(status_code=400, detail=error_detail) from exc

    # Validate AuthZEN compliance
    try:
        validate_authzen_request(sanitized_body)
    except HTTPException as exc:
        # Log validation error before re-raising
        api_logging.log_api_response("POST", "/v1/evaluate", 400, None, str(exc.detail) if hasattr(exc, 'detail') else str(exc))
        raise

    # Evaluate with OPA
    result = evaluate_request_with_opa(
        opa_client=OPA_CLIENT,
        authzen_request=sanitized_body,
    )

    response_body = {
        "decision": result.decision,
        "reason_codes": result.reason_codes,
        "advice": result.advice,
    }
    
    api_logging.log_api_response("POST", "/v1/evaluate", 200, response_body)
    return response_body


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
