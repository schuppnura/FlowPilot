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
# • For service-to-service calls, the token authenticates the service (e.g., AI agent)
# • The user identity (UUID + persona) is passed in context.principal, NOT extracted from token
# • Only subject identifiers (UUIDs) and personas are processed; no PII is exposed
#
# ---------------------------------------------------------------------------
# Authorization Flow (high level)
# ---------------------------------------------------------------------------
#
#   1. Validate and sanitize the incoming AuthZEN request
#   2. Validate the bearer token (authenticates the calling service)
#   3. Extract principal (user) identity from context.principal (id + persona)
#   4. Extract owner identity from resource.properties.owner
#   5. Fetch delegation data from delegation-api (if owner != principal)
#   6. Fetch owner attributes from Keycloak for policy evaluation
#   7. Build OPA input document (subject, action, resource, delegations)
#   8. Evaluate Rego policy in OPA (ABAC + ReBAC)
#   9. Return decision, reason codes, and optional advice
#
# Note: context.principal does NOT contain claims - only id and persona.
#       Owner attributes are fetched from Keycloak and added to resource.properties.owner.
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

import argparse
import os
import time
from typing import Any, Optional

import api_logging
import security
import uvicorn
from authz_core import evaluate_authorization_request
from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import jwt

# ============================================================================
# Configuration Constants
# ============================================================================

# Environment flag for detailed error messages (disable in production)
INCLUDE_ERROR_DETAILS = os.environ.get("INCLUDE_ERROR_DETAILS", "1") == "1"

# FlowPilot token signing configuration
SIGNING_KEY_PATH = os.environ.get("SIGNING_KEY_PATH", "/secrets/signing-key")
FLOWPILOT_PUBLIC_KEY_PATH = os.environ.get("FLOWPILOT_PUBLIC_KEY_PATH", "/secrets/signing-key-pub")
FLOWPILOT_TOKEN_ISSUER = os.environ.get("FLOWPILOT_TOKEN_ISSUER", "https://flowpilot-authz-api")
FLOWPILOT_TOKEN_AUDIENCE = os.environ.get("FLOWPILOT_TOKEN_AUDIENCE", "flowpilot")
FLOWPILOT_TOKEN_EXPIRY_SECONDS = int(os.environ.get("FLOWPILOT_TOKEN_EXPIRY_SECONDS", "900"))  # 15 minutes

# Cached signing key
_SIGNING_KEY: str | None = None
_SIGNING_KEY_ID = "flowpilot-v1"

# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(title="FlowPilot AuthZ API", version="1.0.0")

# Add CORS middleware
cors_config = security.get_cors_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_config["allow_origins"],
    allow_credentials=cors_config["allow_credentials"],
    allow_methods=cors_config["allow_methods"],
    allow_headers=cors_config["allow_headers"],
)

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




def build_error_response(
    status_code: int,
    message: str,
    code: str = "ERROR",
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {"message": message, "code": code}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status_code, content=body)


def _get_signing_key() -> str:
    """Load FlowPilot signing key from file system or environment variable (cached)."""
    global _SIGNING_KEY
    if _SIGNING_KEY:
        return _SIGNING_KEY

    # First try environment variable (for Cloud Run secret mounting)
    env_key = os.environ.get("SIGNING_KEY_CONTENT")
    if env_key:
        _SIGNING_KEY = env_key
        return _SIGNING_KEY

    # Fall back to file system (for local development)
    try:
        with open(SIGNING_KEY_PATH) as f:
            _SIGNING_KEY = f.read()
        return _SIGNING_KEY
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="Token signing key not configured (neither SIGNING_KEY_CONTENT env var nor file at SIGNING_KEY_PATH)"
        )


@app.get("/health")
def get_health() -> dict[str, Any]:
    return {"status": "ok"}


@app.post("/v1/token/exchange")
def post_token_exchange(
    request: Request,
    token_claims: dict[str, Any] = Depends(security.verify_firebase_token),
) -> dict[str, Any]:
    """
    Exchange Firebase ID token for pseudonymous FlowPilot access token.
    
    This endpoint accepts a Firebase ID token (which may contain PII like email, name)
    and returns a minimal access token containing only the user's subject identifier (sub).
    
    The returned access token should be used for all backend API calls, enabling
    privacy-preserving authorization where only the user's UUID is transmitted.
    
    Request:
        Authorization: Bearer <Firebase ID token>
    
    Response:
        {
            "access_token": "<FlowPilot JWT>",
            "token_type": "Bearer",
            "expires_in": 900
        }
    
    The returned access token contains only:
        - sub: User UUID
        - iss: FlowPilot issuer URL
        - aud: FlowPilot audience
        - exp, iat: Expiry and issued-at timestamps
    """
    # Extract user ID from validated Firebase token
    user_sub = token_claims.get("sub")
    if not user_sub:
        raise HTTPException(status_code=400, detail="Missing sub claim in token")

    # Create minimal access token (pseudonymous - sub only)
    now = int(time.time())
    access_token_payload = {
        "sub": user_sub,
        "iss": FLOWPILOT_TOKEN_ISSUER,
        "aud": FLOWPILOT_TOKEN_AUDIENCE,
        "exp": now + FLOWPILOT_TOKEN_EXPIRY_SECONDS,
        "iat": now,
        "token_type": "access",
    }

    # Sign with FlowPilot's private key
    signing_key = _get_signing_key()
    access_token = jwt.encode(
        access_token_payload,
        signing_key,
        algorithm="RS256",
        headers={"kid": _SIGNING_KEY_ID}
    )

    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": FLOWPILOT_TOKEN_EXPIRY_SECONDS,
    }


@app.post("/v1/evaluate")
def post_evaluate(
    request: Request,
    request_body: dict[str, Any] = Body(...),
    token_claims: dict[str, Any] = Depends(security.verify_token),
) -> dict[str, Any]:
    # Sanitize all input before processing
    try:
        sanitized_body = security.sanitize_request_json_payload(request_body)
    except security.InputValidationError as exc:
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        raise HTTPException(status_code=400, detail=error_detail) from exc

    # Evaluate authorization request (handles AuthZEN validation, delegation fetching, OPA evaluation)
    try:
        result = evaluate_authorization_request(sanitized_body)
    except ValueError as exc:
        # AuthZEN validation error
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        raise HTTPException(status_code=400, detail=error_detail) from exc

    response_body = {
        "decision": result.decision,
        "reason_codes": result.reason_codes,
        "advice": result.advice,
    }

    return response_body


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FlowPilot AuthZ API")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    args = parser.parse_args()

    # Uvicorn server configuration (can be overridden via environment variables)
    uvicorn_max_requests = int(os.environ.get("UVICORN_MAX_REQUESTS", "10000"))
    uvicorn_max_concurrency = int(os.environ.get("UVICORN_MAX_CONCURRENCY", "100"))
    uvicorn_keepalive_timeout = int(os.environ.get("UVICORN_KEEPALIVE_TIMEOUT", "5"))

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        # Security: Limit request body size to prevent memory exhaustion
        limit_max_requests=uvicorn_max_requests,
        limit_concurrency=uvicorn_max_concurrency,
        timeout_keep_alive=uvicorn_keepalive_timeout,
    )
