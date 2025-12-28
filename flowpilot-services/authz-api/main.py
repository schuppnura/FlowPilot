# FlowPilot Authorization API (flowpilot-authz-api)
#
# This service acts as the authorization façade (PEP/PDP integration layer)
# for the FlowPilot platform. It validates AuthZEN-compliant authorization requests,
# enforces delegation (relationship-based access control), and evaluates attribute-based
# policies via Open Policy Agent (OPA). This service is stateless and does not maintain
# any in-memory storage.
#
# Conceptually, this service answers the question:
#
#   “May subject X perform action A on resource R on behalf of principal P,
#    and if not, why?”
#
# The AuthZ API deliberately separates responsibilities:
#
#   • Delegation (ReBAC): who may act for whom, resolved via authorization graphs
#   • Policy evaluation (ABAC): whether the action is allowed given attributes
#     such as consent, cost limits, lead time, and risk thresholds
#
# Delegation is evaluated first (fail-closed). Only if delegation is valid
# does the service proceed to ABAC policy evaluation in OPA.
#
# ---------------------------------------------------------------------------
# Supported HTTP Endpoints
# ---------------------------------------------------------------------------
#
# Health & diagnostics:
#
#   GET  /health
#     - Liveness/readiness check
#     - No authentication required
#
# Authorization evaluation:
#
#   POST /v1/evaluate
#     - Core authorization endpoint
#     - Accepts an AuthZEN-like request structure:
#         subject / action / resource / context / options
#     - Enforces delegation when the subject differs from the principal
#     - Calls OPA to evaluate Rego policies
#     - Returns:
#         decision: allow | deny
#         reason_codes: machine-readable denial reasons
#         advice: optional human-readable hints
#
# ---------------------------------------------------------------------------
# Security Model
# ---------------------------------------------------------------------------
#
# • All endpoints except /health require JWT bearer authentication
# • Tokens are validated locally using JWKS (no per-request network calls)
# • The principal identity is derived from the JWT `sub` claim
# • Only subject identifiers (UUIDs, agent IDs) are processed; no PII is exposed
#
# ---------------------------------------------------------------------------
# Authorization Flow (high level)
# ---------------------------------------------------------------------------
#
#   1. Validate and sanitize the incoming AuthZEN-like request
#   2. Validate the bearer token and extract user claims
#   3. If subject != principal:
#        - Validate delegation via the delegation service (ReBAC)
#   4. Build OPA input document (claims + resource + action)
#   5. Evaluate Rego policy in OPA (ABAC)
#   6. Return decision, reason codes, and optional advice
#
# ---------------------------------------------------------------------------
# Design Goals
# ---------------------------------------------------------------------------
#
# • Deterministic, fail-closed authorization behavior
# • Clear separation between delegation (ReBAC) and policy (ABAC)
# • Explainable authorization outcomes (reason codes + advice)
# • Defense-in-depth input validation and token verification
# • Zero PII exposure to downstream services and AI agents
#
# This service is business-agnostic and intentionally does not embed business policy logic.
# All authorization rules are expressed declaratively in Rego policies
# evaluated by OPA.
#
# See also:
#   • README.md for architectural context and security rationale
#   • flowpilot-authz.openapi.yaml for the formal API contract

from __future__ import annotations

import os
from typing import Any, Optional

import argparse
import uvicorn

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

import security
import api_logging
import profile
from core import evaluate_authorization_request

# ============================================================================
# Configuration Constants
# ============================================================================

# Environment flag for detailed error messages (disable in production)
INCLUDE_ERROR_DETAILS = os.environ.get("INCLUDE_ERROR_DETAILS", "1") == "1"

# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(title="FlowPilot AuthZ API", version="1.0.0")

# Add security middlewares before defining routes
app.add_middleware(security.SecurityHeadersMiddleware)
app.add_middleware(
    security.RequestSizeLimiterMiddleware, max_size=security.get_max_request_size()
)


# Custom exception handler for HTTPException to log authentication errors
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code in (401, 403):
        # Log authentication/authorization errors for debugging
        auth_header = request.headers.get("authorization", "")
        auth_preview = (
            auth_header[:50] + "..." if len(auth_header) > 50 else auth_header or "None"
        )
        print(
            f"[authz-api HTTPException {exc.status_code}] Path: {request.url.path}, Detail: {exc.detail}, Auth: {auth_preview}",
            flush=True,
        )
        # Also log full request details
        print(
            f"[authz-api HTTPException] Full request headers: {dict(request.headers)}",
            flush=True,
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc.detail) if hasattr(exc, "detail") else str(exc)},
        headers=exc.headers if hasattr(exc, "headers") else {},
    )


def get_token_claims(
    token_claims: dict[str, Any] = Depends(security.verify_token),
) -> dict[str, Any]:
    # Return JWT claims from validated token
    # verify_token will raise HTTPException if token is invalid, so if we get here, token is valid
    return token_claims


def build_error_response(
    status_code: int,
    message: str,
    code: str = "ERROR",
    details: Optional[dict[str, Any]] = None,
) -> JSONResponse:
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
        raise HTTPException(status_code=400, detail=error_detail) from exc

    # Evaluate authorization request (handles AuthZEN validation, delegation fetching, OPA evaluation)
    try:
        result = evaluate_authorization_request(sanitized_body)
    except ValueError as exc:
        # AuthZEN validation error
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        api_logging.log_api_response("POST", "/v1/evaluate", 400, error=error_detail)
        raise HTTPException(status_code=400, detail=error_detail) from exc

    response_body = {
        "decision": result.decision,
        "reason_codes": result.reason_codes,
        "advice": result.advice,
    }

    api_logging.log_api_response("POST", "/v1/evaluate", 200, response_body=response_body)

    return response_body


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
