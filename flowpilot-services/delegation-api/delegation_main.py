# FlowPilot Delegation API (flowpilot-delegation-api)
#
# This service implements the Delegation capability used by FlowPilot to manage
# and validate delegation relationships between principals and delegates
# (users or agents). Delegation is treated as a first-class authorization
# primitive and is evaluated before attribute-based policy checks (OPA / Rego).
#
# Delegation answers the question:
#
#   “Is subject X allowed to act on behalf of principal Y in this context?”
#
# The delegation model is relationship-based (ReBAC) and supports both direct
# and transitive delegation chains with explicit constraints and fail-closed
# semantics.
#
# ---------------------------------------------------------------------------
# Supported HTTP Endpoints
# ---------------------------------------------------------------------------
#
# Health:
#
#   GET /health
#     - Liveness/readiness check
#     - No authentication required
#
# Delegation lifecycle:
#
#   POST /v1/delegations
#     - Creates a new delegation from the authenticated principal
#       to a delegate (user or agent)
#     - Request fields include:
#         delegate_id
#         delegate_type (user | agent)
#         workflow_id (optional)
#         scope (optional, defaults applied)
#         expires_at (optional, ISO-8601 UTC)
#
#   GET /v1/delegations/{delegation_id}
#     - Retrieves a single delegation record by id
#
#   GET /v1/delegations
#     - Lists delegations
#     - Optional query parameters:
#         principal_id
#         delegate_id
#
#   DELETE /v1/delegations/{delegation_id}
#     - Revokes an existing delegation
#     - Operation is idempotent
#
# Delegation validation:
#
#   GET /v1/delegations/validate
#     - Validates whether a delegate may act on behalf of a principal
#     - Resolves delegation chains transitively (A → B → C)
#     - Query parameters:
#         principal_id   (required)
#         delegate_id    (required)
#         workflow_id    (optional)
#     - Returns:
#         valid: true | false
#         delegation_chain: ordered list of delegation edges (if valid)
#         reason: human-readable explanation
#
# ---------------------------------------------------------------------------
# Delegation Semantics
# ---------------------------------------------------------------------------
#
# • Delegations are directional: owner → delegate
# • Delegations may be:
#     - Workflow-scoped (apply only to a specific workflow)
#     - Unscoped (apply to all workflows)
# • Delegations may expire automatically via expires_at
# • Delegations may be revoked explicitly
#
# A delegation is considered valid if:
#   • It exists and is marked active
#   • It is not revoked
#   • It is not expired
#   • It matches the requested workflow scope (if any)
#   • A valid delegation chain exists within the configured hop limit
#
# Transitive delegation is supported but bounded by configuration to prevent
# privilege amplification and unbounded graph traversal.
#
# ---------------------------------------------------------------------------
# Role in the Authorization Architecture
# ---------------------------------------------------------------------------
#
# This service is consumed by flowpilot-authz-api as part of the authorization
# decision flow:
#
#   1. An AuthZEN-like request is received by the AuthZ API.
#   2. If subject != principal, delegation is validated via this service.
#   3. If delegation is invalid, authorization fails immediately.
#   4. If delegation is valid, ABAC policy evaluation (OPA) proceeds.
#
# Delegation therefore acts as a ReBAC guardrail in front of ABAC policies.
#
# ---------------------------------------------------------------------------
# Security Model
# ---------------------------------------------------------------------------
#
# • All endpoints except /health require JWT bearer authentication
# • Tokens are validated locally using JWKS
# • The principal identity is derived from the JWT `sub` claim
# • Only identifiers are processed; no PII is stored or exposed
#
# ---------------------------------------------------------------------------
# Design Goals
# ---------------------------------------------------------------------------
#
# • Minimal and explicit API surface
# • Deterministic, fail-closed authorization behavior
# • Explainable authorization via delegation chains
# • Clear separation between delegation (ReBAC) and policy (ABAC)
# • Storage abstraction allowing future migration to graph backends
#
# This service is business-agnostic and intentionally does not evaluate business policies.
# It answers only “who may act for whom, and why”.
#
# See also:
#   • README.md for architectural context and usage guidance
#   • flowpilot-delegation.openapi.yaml for the formal API contract

from __future__ import annotations

import argparse
import os
from typing import Any, Dict, List, Optional

import api_logging
import security
import uvicorn
from delegation_core import DelegationService
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from graphdb import DelegationGraphDB
from pydantic import BaseModel, Field, validator
from utils import (
    coerce_positive_int,
    load_json_object,
    merge_config,
    require_non_empty_string,
)

# ============================================================================
# Configuration Constants
# ============================================================================

# Environment flag for detailed error messages (disable in production)
INCLUDE_ERROR_DETAILS = os.environ.get("INCLUDE_ERROR_DETAILS", "1") == "1"

# Delegation expiry configuration (can be overridden via environment variables)
DELEGATION_DEFAULT_EXPIRY_DAYS = int(
    os.environ.get("DELEGATION_DEFAULT_EXPIRY_DAYS", "7")
)
DELEGATION_MIN_EXPIRY_DAYS = int(os.environ.get("DELEGATION_MIN_EXPIRY_DAYS", "1"))
DELEGATION_MAX_EXPIRY_DAYS = int(os.environ.get("DELEGATION_MAX_EXPIRY_DAYS", "365"))

# Delegation allowed actions (can be overridden via environment variables)
_DELEGATION_ALLOWED_ACTIONS_STR = os.environ.get(
    "DELEGATION_ALLOWED_ACTIONS", "read,execute"
)
DELEGATION_ALLOWED_ACTIONS = {
    action.strip()
    for action in _DELEGATION_ALLOWED_ACTIONS_STR.split(",")
    if action.strip()
}

# Default configuration values
DEFAULT_CONFIG: dict[str, Any] = {
    "service_name": "flowpilot-delegation-api",
    "log_level": "info",
    "db_path": "./delegations.db",  # SQLite database file path
    "request_timeout_seconds": 10,
}

# ============================================================================
# Request/Response Models
# ============================================================================


class CreateDelegationRequest(BaseModel):
    principal_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Principal ID (delegating authority)",
    )
    delegate_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Delegate ID (receiving authority)",
    )
    workflow_id: str | None = Field(
        None, max_length=255, description="Optional workflow ID to scope delegation"
    )
    scope: list[str] | None = Field(
        None,
        description='List of actions (e.g. ["read"] or ["read", "execute"]). Defaults to ["execute"]',
    )
    expires_in_days: int = Field(
        default=DELEGATION_DEFAULT_EXPIRY_DAYS,
        ge=DELEGATION_MIN_EXPIRY_DAYS,
        le=DELEGATION_MAX_EXPIRY_DAYS,
        description=f"Days until expiration (default: {DELEGATION_DEFAULT_EXPIRY_DAYS}, min: {DELEGATION_MIN_EXPIRY_DAYS}, max: {DELEGATION_MAX_EXPIRY_DAYS})",
    )

    @validator("principal_id")
    def sanitize_principal_id(cls, v: str) -> str:
        return security.sanitize_string(v, 255)

    @validator("delegate_id")
    def sanitize_delegate_id(cls, v: str) -> str:
        return security.sanitize_string(v, 255)

    @validator("workflow_id")
    def sanitize_workflow_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return security.sanitize_string(v, 255)

    @validator("scope")
    def validate_scope(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        # Validate that scope contains only allowed actions
        for action in v:
            if action not in DELEGATION_ALLOWED_ACTIONS:
                raise ValueError(
                    f"Invalid action in scope: {action}. Allowed: {DELEGATION_ALLOWED_ACTIONS}"
                )
        return v


class RevokeDelegationRequest(BaseModel):
    principal_id: str = Field(
        ..., min_length=1, max_length=255, description="Principal ID"
    )
    delegate_id: str = Field(
        ..., min_length=1, max_length=255, description="Delegate ID"
    )
    workflow_id: str | None = Field(
        None, max_length=255, description="Optional workflow ID to scope revocation"
    )

    @validator("principal_id")
    def sanitize_principal_id(cls, v: str) -> str:
        return security.sanitize_string(v, 255)

    @validator("delegate_id")
    def sanitize_delegate_id(cls, v: str) -> str:
        return security.sanitize_string(v, 255)

    @validator("workflow_id")
    def sanitize_workflow_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return security.sanitize_string(v, 255)


def build_config(config_path: str | None) -> dict[str, Any]:
    # Build runtime config from defaults, optional JSON override, and environment variables.
    config = dict(DEFAULT_CONFIG)

    if config_path:
        config = merge_config(config, load_json_object(config_path))

    config["log_level"] = os.environ.get("LOG_LEVEL", str(config["log_level"]))
    config["db_path"] = os.environ.get("DB_PATH", str(config["db_path"]))
    config["request_timeout_seconds"] = coerce_positive_int(
        os.environ.get(
            "REQUEST_TIMEOUT_SECONDS", str(config["request_timeout_seconds"])
        ),
        "REQUEST_TIMEOUT_SECONDS",
    )

    require_non_empty_string(str(config.get("db_path", "")), "db_path")

    return config


def handle_get_health(request: Request) -> dict[str, Any]:
    # Return an operational health response.
    return {
        "status": "ok",
        "service": str(
            request.app.state.config.get("service_name", "flowpilot-delegation-api")
        ),
    }


def handle_post_delegations(
    request: Request,
    response: Response,
    body: CreateDelegationRequest,
    token_claims: dict = Depends(security.verify_token),
) -> dict[str, Any]:
    # Create a delegation relationship.
    # Returns 201 if created, 200 if identical delegation already exists.
    # Returns 400 if delegation exists with different parameters (conflict).
    service: DelegationService = request.app.state.service

    try:

        # Extract delegator_id from JWT to validate they can only delegate what they have
        # Skip validation in these cases:
        #   1. delegator_id matches principal_id (owner creating their own delegation)
        #   2. Token is from a service account (persona=service) acting on behalf of owner
        #   3. No delegator_id provided
        delegator_id = token_claims.get("sub") if token_claims else None
        persona = token_claims.get("persona") if token_claims else None

        # Check if this is a service account token (Cloud Run identity token has persona=service)
        is_service_account = persona == "service"

        # Only validate subdelegations (non-service-account, non-owner delegations)
        effective_delegator_id = None
        if (
            delegator_id
            and delegator_id != body.principal_id
            and not is_service_account
        ):
            # This is a subdelegation - validate that delegator has permissions
            effective_delegator_id = delegator_id

        delegation = service.create_delegation(
            principal_id=body.principal_id,
            delegate_id=body.delegate_id,
            workflow_id=body.workflow_id,
            expires_in_days=body.expires_in_days,
            scope=body.scope,
            delegator_id=effective_delegator_id,
        )

        # Set HTTP status code based on whether delegation was created or already existed
        was_created = delegation.pop("was_created", True)  # Remove internal metadata
        response.status_code = 201 if was_created else 200

        return delegation
    except ValueError as exception:
        error_detail = security.sanitize_error_message(
            str(exception), INCLUDE_ERROR_DETAILS
        )
        raise HTTPException(status_code=400, detail=error_detail) from exception
    except Exception as exception:
        error_detail = security.sanitize_error_message(
            str(exception), INCLUDE_ERROR_DETAILS
        )
        raise HTTPException(status_code=500, detail=error_detail) from exception


def handle_delete_delegations(
    request: Request,
    body: RevokeDelegationRequest,
    token_claims: dict = Depends(security.verify_token),
) -> dict[str, Any]:
    # Revoke a delegation relationship.
    service: DelegationService = request.app.state.service

    try:

        result = service.revoke_delegation(
            principal_id=body.principal_id,
            delegate_id=body.delegate_id,
            workflow_id=body.workflow_id,
        )


        return result
    except ValueError as exception:
        error_detail = security.sanitize_error_message(
            str(exception), INCLUDE_ERROR_DETAILS
        )
        raise HTTPException(status_code=400, detail=error_detail) from exception
    except Exception as exception:
        error_detail = security.sanitize_error_message(
            str(exception), INCLUDE_ERROR_DETAILS
        )
        raise HTTPException(status_code=500, detail=error_detail) from exception


def handle_get_delegations_validate(
    request: Request,
    principal_id: str,
    delegate_id: str,
    workflow_id: str | None = None,
    token_claims: dict = Depends(security.verify_token),
) -> dict[str, Any]:
    # Validate a delegation relationship.
    service: DelegationService = request.app.state.service

    try:

        result = service.validate_delegation(
            principal_id=principal_id,
            delegate_id=delegate_id,
            workflow_id=workflow_id,
        )

        return result
    except ValueError as exception:
        error_detail = security.sanitize_error_message(
            str(exception), INCLUDE_ERROR_DETAILS
        )
        raise HTTPException(status_code=400, detail=error_detail) from exception
    except Exception as exception:
        error_detail = security.sanitize_error_message(
            str(exception), INCLUDE_ERROR_DETAILS
        )
        raise HTTPException(status_code=500, detail=error_detail) from exception


def handle_get_delegations(
    request: Request,
    principal_id: str | None = None,
    delegate_id: str | None = None,
    workflow_id: str | None = None,
    include_expired: bool = False,
    token_claims: dict = Depends(security.verify_token),
) -> dict[str, Any]:
    # List delegations.
    service: DelegationService = request.app.state.service

    try:

        delegations = service.list_delegations(
            principal_id=principal_id,
            delegate_id=delegate_id,
            workflow_id=workflow_id,
            include_expired=include_expired,
        )
        result = {"delegations": delegations}

        return result
    except ValueError as exception:
        error_detail = security.sanitize_error_message(
            str(exception), INCLUDE_ERROR_DETAILS
        )
        raise HTTPException(status_code=400, detail=error_detail) from exception
    except Exception as exception:
        error_detail = security.sanitize_error_message(
            str(exception), INCLUDE_ERROR_DETAILS
        )
        raise HTTPException(status_code=500, detail=error_detail) from exception


# GET /v1/users endpoint has been moved to flowpilot-user-profile-api
# This service now focuses solely on delegation relationship management


def create_app(config: dict[str, Any]) -> FastAPI:
    # Create FastAPI API endpoints and wire routes.
    api = FastAPI(
        title="FlowPilot Delegation API",
        version="1.0.0",
        swagger_ui_parameters={"defaultModelsExpandDepth": -1},
    )
    api.state.config = config

    # Initialize PostgreSQL graph database
    graphdb = DelegationGraphDB()  # Uses env vars for connection

    service = DelegationService(graphdb=graphdb)
    api.state.service = service

    # Add exception handler
    @api.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if exc.status_code == 401:
            auth_header = request.headers.get("authorization", "")
            token_preview = (
                auth_header[:50] + "..." if len(auth_header) > 50 else auth_header
            )
            print(
                f"[HTTPException 401] Path: {request.url.path}, Detail: {exc.detail}, Auth header: {token_preview}",
                flush=True,
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    # Add CORS middleware
    cors_config = security.get_cors_config()
    api.add_middleware(
        CORSMiddleware,
        allow_origins=cors_config["allow_origins"],
        allow_credentials=cors_config["allow_credentials"],
        allow_methods=cors_config["allow_methods"],
        allow_headers=cors_config["allow_headers"],
    )

    # Add security middlewares
    api.add_middleware(security.SecurityHeadersMiddleware)
    api.add_middleware(
        security.RequestSizeLimiterMiddleware, max_size=security.get_max_request_size()
    )

    # Health check - no auth required
    api.add_api_route("/health", handle_get_health, methods=["GET"])

    # All other endpoints require authentication
    api.add_api_route(
        "/v1/delegations",
        handle_post_delegations,
        methods=["POST"],
        dependencies=[Depends(security.verify_token)],
    )
    api.add_api_route(
        "/v1/delegations",
        handle_delete_delegations,
        methods=["DELETE"],
        dependencies=[Depends(security.verify_token)],
    )
    api.add_api_route(
        "/v1/delegations",
        handle_get_delegations,
        methods=["GET"],
        dependencies=[Depends(security.verify_token)],
    )
    api.add_api_route(
        "/v1/delegations/validate",
        handle_get_delegations_validate,
        methods=["GET"],
        dependencies=[Depends(security.verify_token)],
    )
    # /v1/users endpoint moved to flowpilot-user-profile-api

    return api


def parse_args() -> argparse.Namespace:
    # Parse CLI args for container entrypoints.
    parser = argparse.ArgumentParser(description="FlowPilot Delegation API service")
    parser.add_argument(
        "--config", dest="config_path", default=None, help="Path to JSON config file."
    )
    parser.add_argument("--host", dest="host", default="0.0.0.0", help="Bind host.")
    parser.add_argument(
        "--port", dest="port", type=int, default=8005, help="Bind port."
    )
    parser.add_argument(
        "--reload",
        dest="reload",
        action="store_true",
        help="Enable auto-reload (local dev).",
    )
    return parser.parse_args()


def main() -> int:
    # Build config and start Uvicorn.
    args = parse_args()
    try:
        config = build_config(config_path=args.config_path)
    except ValueError as exception:
        print(f"[flowpilot-delegation-api] Configuration error: {exception}")
        return 2

    api = create_app(config=config)

    # Uvicorn server configuration (can be overridden via environment variables)
    uvicorn_max_requests = int(os.environ.get("UVICORN_MAX_REQUESTS", "10000"))
    uvicorn_max_concurrency = int(os.environ.get("UVICORN_MAX_CONCURRENCY", "100"))
    uvicorn_keepalive_timeout = int(os.environ.get("UVICORN_KEEPALIVE_TIMEOUT", "5"))

    uvicorn.run(
        api,
        host=str(args.host),
        port=int(args.port),
        reload=bool(args.reload),
        log_level=str(config.get("log_level", "info")),
        limit_max_requests=uvicorn_max_requests,
        limit_concurrency=uvicorn_max_concurrency,
        timeout_keep_alive=uvicorn_keepalive_timeout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
