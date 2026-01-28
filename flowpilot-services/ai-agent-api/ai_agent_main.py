# FlowPilot AI Agent API - FastAPI Application
#
# Domain-agnostic workflow execution service that executes workflow items item-by-item.
# This agent runner is part of the FlowPilot reference architecture demonstrating
# agentic workflows with authorization and delegation.
#
# Key endpoints:
# - POST /v1/workflow-runs: Execute a complete workflow with authorization checks
# - POST /v1/agent-runs: Backward-compatible alias for older clients
# - GET /health: Health check endpoint
#
# All endpoints (except health) require bearer token authentication.

from __future__ import annotations

import argparse
import os
from typing import Any, Dict, Optional

import api_logging
import security
import uvicorn
from ai_agent_core import (
    check_workflow_execution_authorization,
    execute_workflow_run,
    normalize_workflow_id,
)
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from utils import (
    coerce_positive_int,
    load_json_object,
    merge_config,
    require_non_empty_string,
)

# Environment flag for detailed error messages (disable in production)
INCLUDE_ERROR_DETAILS = os.environ.get("INCLUDE_ERROR_DETAILS", "1") == "1"


DEFAULT_CONFIG: dict[str, Any] = {
    "service_name": "agent-runner-api",
    "log_level": "info",
    # Workflow (domain) API base. In this demo stack it points to the FlowPilot API.
    "workflow_base_url": "http://flowpilot-api:8003",
    # AuthZ API base URL for authorization checks
    "authz_base_url": "http://flowpilot-authz-api:8000",
    # Note: agent_sub is no longer configured - it's extracted from service token at runtime
    # Workflow item listing and execution endpoints. These are domain-agnostic and work with any workflow backend.
    "workflow_items_path_template": "/v1/workflows/{workflow_id}/items",
    "workflow_item_execute_path_template": "/v1/workflows/{workflow_id}/items/{workflow_item_id}/execute",
    # Operational timeouts.
    "request_timeout_seconds": 10,
}


class WorkflowRunRequest(BaseModel):
    workflow_id: str = Field(
        ..., min_length=1, max_length=255, description="Workflow identifier"
    )
    principal_sub: str = Field(
        ..., min_length=1, max_length=255, description="Principal subject"
    )
    dry_run: bool = Field(default=True, description="Dry run flag")
    persona: str = Field(
        ..., min_length=1, max_length=255, description="Selected persona for the user (required)"
    )

    @validator("workflow_id")
    def validate_workflow_id(cls, v: str) -> str:
        return security.validate_id(v, "workflow_id", 255)

    @validator("principal_sub")
    def sanitize_principal_sub(cls, v: str) -> str:
        return security.sanitize_string(v, 255)

    @validator("persona")
    def sanitize_persona(cls, v: str) -> str:
        return security.sanitize_string(v, 255)


def build_config(config_path: str | None) -> dict[str, Any]:
    # Build runtime config from defaults, optional JSON override, and env vars
    # side effect: reads env and file.
    config = dict(DEFAULT_CONFIG)

    if config_path:
        config = merge_config(config, load_json_object(config_path))

    config["log_level"] = os.environ.get("LOG_LEVEL", str(config["log_level"]))
    config["workflow_base_url"] = os.environ.get(
        "WORKFLOW_BASE_URL",
        os.environ.get("FLOWPILOT_BASE_URL", str(config["workflow_base_url"])),
    )
    config["authz_base_url"] = os.environ.get(
        "AUTHZ_BASE_URL", str(config["authz_base_url"])
    )
    # Note: AGENT_SUB env var is deprecated - agent identity is extracted from service token
    config["workflow_items_path_template"] = os.environ.get(
        "WORKFLOW_ITEMS_PATH_TEMPLATE", str(config["workflow_items_path_template"])
    )
    config["workflow_item_execute_path_template"] = os.environ.get(
        "WORKFLOW_ITEM_EXECUTE_PATH_TEMPLATE",
        str(config["workflow_item_execute_path_template"]),
    )

    config["request_timeout_seconds"] = coerce_positive_int(
        os.environ.get(
            "REQUEST_TIMEOUT_SECONDS", str(config["request_timeout_seconds"])
        ),
        "REQUEST_TIMEOUT_SECONDS",
    )

    require_non_empty_string(
        str(config.get("workflow_base_url", "")), "workflow_base_url"
    )
    require_non_empty_string(str(config.get("authz_base_url", "")), "authz_base_url")
    # Note: agent_sub is no longer a config parameter - extracted from service token at runtime
    require_non_empty_string(
        str(config.get("workflow_items_path_template", "")),
        "workflow_items_path_template",
    )
    require_non_empty_string(
        str(config.get("workflow_item_execute_path_template", "")),
        "workflow_item_execute_path_template",
    )

    return config


def handle_get_health(_request: Request) -> dict[str, str]:
    # Provide a simple health response for smoke tests
    # assumption: no downstream checks here by design.
    return {"status": "ok"}


def handle_post_workflow_runs(
    request: Request,
    body: WorkflowRunRequest,
    token_claims: dict = Depends(security.verify_token),
) -> dict[str, Any]:
    # Execute a workflow by iterating items and delegating execution to domain service endpoints (domain is PEP).
    # AuthZEN: Extract user token, decode to get principal info, check authorization before starting.
    config: dict[str, Any] = request.app.state.config

    try:
        # Extract user token from Authorization header (the client's token)
        user_token = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            user_token = auth_header[7:]  # Remove "Bearer " prefix

        # Decode user token to extract principal information (AuthZEN: disassemble token)
        principal_user: dict[str, Any] | None = None
        if user_token:
            try:
                user_claims = security.verify_token_string(user_token)
                # Create principal-user object (AuthZEN format)
                # Note: Excluding PII (email, preferred_username) for privacy
                # Note: Autobook attributes are fetched by authz-api for the resource owner, not passed here
                # Note: No claims field needed - identity is in principal_user.id

                # Include persona from request body if provided (selected persona)
                # The token contains all personas, but the request body has the selected one
                principal_user = {
                    "type": "user",
                    "id": user_claims.get(
                        "sub", body.principal_sub
                    ),  # Use token sub, fallback to body
                }

                # Add selected persona to principal_user (now required)
                principal_user["persona"] = body.persona
            except Exception:
                # If token decode fails, use principal_sub from body (backward compatibility)
                principal_user = {
                    "type": "user",
                    "id": body.principal_sub,
                }
        else:
            # No token provided, use principal_sub from body
            principal_user = {"type": "user", "id": body.principal_sub}

        workflow_id = normalize_workflow_id(workflow_id=body.workflow_id)

        # Use fixed agent identity (no longer need service token since we pass user token)
        # The agent acts on behalf of the user with the user's token
        agent_sub = "agent-runner"

        # AuthZEN: Check authorization before starting workflow execution (anti-spoofing)
        authz_result = check_workflow_execution_authorization(
            config=config,
            workflow_id=workflow_id,
            principal_user=principal_user,
            agent_sub=agent_sub,
        )

        if authz_result.get("decision") != "allow":
            raise HTTPException(
                status_code=403,
                detail=f"Workflow execution not authorized: {authz_result.get('reason_codes', [])}",
            )

        # Execute workflow with principal-user object (AuthZEN: pass principal info, not token)
        # Pass user token for service-to-service calls (agent acts on behalf of user)
        result = execute_workflow_run(
            config=config,
            workflow_id=workflow_id,
            principal_user=principal_user,
            dry_run=bool(body.dry_run),
            user_token=user_token,
        )

        return result
    except HTTPException as exc:
        raise
    except security.InputValidationError as exception:
        error_detail = security.sanitize_error_message(
            str(exception), INCLUDE_ERROR_DETAILS
        )
        raise HTTPException(status_code=400, detail=error_detail) from exception
    except ValueError as exception:
        error_detail = security.sanitize_error_message(
            str(exception), INCLUDE_ERROR_DETAILS
        )
        raise HTTPException(status_code=400, detail=error_detail) from exception
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS),
        ) from exc


def handle_post_agent_runs(
    request: Request,
    body: WorkflowRunRequest,
    token_claims: dict = Depends(security.verify_token),
) -> dict[str, Any]:
    # Backward-compatible alias for older clients
    # why: preserve existing scripts and desktop app wiring.
    return handle_post_workflow_runs(request, body, token_claims)


def create_app(config: dict[str, Any]) -> FastAPI:
    #
    # Create FastAPI API endpoints and wire routes
    #
    # side effect: registers routes and handlers.
    # Note: Request body size is limited by uvicorn's --limit-max-requests parameter
    api = FastAPI(
        title="Agent Runner API",
        version="0.7.1",
        # Limit request body size to 1MB (protects against large payload attacks)
        # Can be overridden per endpoint if needed
        swagger_ui_parameters={"defaultModelsExpandDepth": -1},
    )
    api.state.config = config

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

    # Exception handler for request validation errors
    @api.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        # Log the validation error
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors(), "body": exc.body},
        )

    # Exception handler for HTTPException (400, 403, etc.)
    @api.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        # Log HTTP exceptions
        return JSONResponse(
            status_code=exc.status_code,
            content=(
                {"detail": exc.detail}
                if hasattr(exc, "detail")
                else {"detail": str(exc)}
            ),
        )

    # Health check - no auth required
    api.add_api_route("/health", handle_get_health, methods=["GET"])

    # All other endpoints require authentication
    api.add_api_route(
        "/v1/workflow-runs",
        handle_post_workflow_runs,
        methods=["POST"],
        dependencies=[Depends(security.verify_token)],
    )
    api.add_api_route(
        "/v1/agent-runs",
        handle_post_agent_runs,
        methods=["POST"],
        dependencies=[Depends(security.verify_token)],
    )

    return api


def parse_args() -> argparse.Namespace:
    # Parse CLI args for container entrypoints
    # assumption: used only for bootstrapping, not business logic.
    parser = argparse.ArgumentParser(description="Agent Runner API service")
    parser.add_argument(
        "--config", dest="config_path", default=None, help="Path to JSON config file."
    )
    parser.add_argument("--host", dest="host", default="0.0.0.0", help="Bind host.")
    parser.add_argument(
        "--port", dest="port", type=int, default=8004, help="Bind port."
    )
    parser.add_argument(
        "--reload",
        dest="reload",
        action="store_true",
        help="Enable auto-reload (local dev).",
    )
    return parser.parse_args()


def main() -> int:
    # Build config and run the server
    # side effect: starts web server and blocks
    # returns non-zero on config errors.
    args = parse_args()
    try:
        config = build_config(args.config_path)
    except ValueError as exception:
        print(f"[agent-runner] Configuration error: {exception}")
        return 2

    api = create_app(config)

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
        # Security: Limit request body size to prevent memory exhaustion
        limit_max_requests=uvicorn_max_requests,  # Max requests before worker restart
        limit_concurrency=uvicorn_max_concurrency,  # Max concurrent connections
        timeout_keep_alive=uvicorn_keepalive_timeout,  # Keep-alive timeout
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
