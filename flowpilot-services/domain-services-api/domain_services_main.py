# FlowPilot Domain Services API - FastAPI Application
#
# Travel domain backend implementation. This is the system of record that owns workflow
# state and enforces authorization as a Policy Enforcement Point (PEP).
#
# IMPORTANT: This service is TRAVEL-DOMAIN SPECIFIC. It implements travel workflows
# with flights, hotels, restaurants, museums, trains, etc. Other domains (nursing,
# business events) would have their own domain-services-api implementations with
# domain-specific templates, items, and business logic.
#
# Key endpoints:
# - GET /v1/workflow-templates: List available travel trip templates
# - POST /v1/workflows: Create a new travel itinerary (workflow) from a template
# - GET /v1/workflows/{workflow_id}: Get travel itinerary metadata
# - GET /v1/workflows/{workflow_id}/items: Get itinerary items (flights, hotels, etc.)
# - POST /v1/workflows/{workflow_id}/items/{workflow_item_id}/execute: Execute item with AuthZ check
# - GET /health: Health check with workflow/template counts
#
# All endpoints (except health) require bearer token authentication.
# Domain context: Travel - workflows represent trips/itineraries with travel-specific items.

from __future__ import annotations

import argparse
import os
from typing import Any, Dict, Optional

import api_logging
import security
import uvicorn
from domain_services_core import FlowPilotService, PolicyDeniedError
from fastapi import Depends, FastAPI, HTTPException, Request
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
    "service_name": "flowpilot-api",
    "log_level": "info",
    "domain": "travel",
    # Templates
    "template_directory": "../data/trip_templates",
    # AuthZ integration
    "authz_base_url": "http://flowpilot-authz-api:8000",
    "agent_sub": "agent-runner",
    # Delegation integration
    "delegation_api_base_url": "http://flowpilot-delegation-api:8000",
    # Operational
    "request_timeout_seconds": 10,
}


class CreateWorkflowRequest(BaseModel):
    template_id: str = Field(
        ..., min_length=1, max_length=255, description="Template identifier"
    )
    principal_sub: str = Field(
        ..., min_length=1, max_length=255, description="Principal subject"
    )
    start_date: str = Field(..., description="ISO 8601 date string (YYYY-MM-DD)")
    persona_title: str = Field(
        ..., min_length=1, max_length=255, description="Selected persona title for the user (required)"
    )
    persona_circle: str = Field(
        ..., min_length=1, max_length=255, description="Persona circle to uniquely identify persona (required)"
    )
    domain: str | None = Field(
        None, min_length=1, max_length=255, description="Domain hint for policy selection (e.g., 'travel', 'nursing')"
    )

    @validator("template_id")
    def validate_template_id(cls, v: str) -> str:
        return security.validate_id(v, "template_id", 255)

    @validator("principal_sub")
    def sanitize_principal_sub(cls, v: str) -> str:
        return security.sanitize_string(v, 255)

    @validator("start_date")
    def validate_start_date(cls, v: str) -> str:
        return security.validate_iso_date(v, "start_date")

    @validator("persona_title")
    def sanitize_persona_title(cls, v: str) -> str:
        return security.sanitize_string(v, 255)

    @validator("persona_circle")
    def sanitize_persona_circle(cls, v: str) -> str:
        return security.sanitize_string(v, 255)

    @validator("domain")
    def sanitize_domain(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return security.sanitize_string(v, 255)


class ExecuteWorkflowItemRequest(BaseModel):
    # AuthZEN: Accept principal_user object (preferred) or principal_sub (backward compatibility)
    principal_user: dict[str, Any] | None = Field(
        None, description="Principal-user object (AuthZEN format)"
    )
    principal_sub: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="Principal subject (backward compatibility)",
    )
    dry_run: bool = Field(default=True, description="Dry run flag")

    @validator("principal_sub")
    def sanitize_principal_sub(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return security.sanitize_string(v, 255)

    def get_principal_user(self) -> dict[str, Any]:
        # AuthZEN: Return principal_user if provided, otherwise construct from principal_sub
        if self.principal_user:
            # Return as-is, preserving persona and all other fields
            return self.principal_user
        if self.principal_sub:
            return {"type": "user", "id": self.principal_sub}
        raise ValueError("Either principal_user or principal_sub must be provided")


def build_config(
    config_path: str | None, template_directory_override: str | None
) -> dict[str, Any]:
    # Build runtime config from defaults, optional JSON override, and environment variables
    # side effect: reads env and file.
    config = dict(DEFAULT_CONFIG)

    if config_path:
        config = merge_config(config, load_json_object(config_path))

    config["log_level"] = os.environ.get("LOG_LEVEL", str(config["log_level"]))
    config["domain"] = os.environ.get("DOMAIN", str(config["domain"]))

    env_template_directory = os.environ.get("TEMPLATE_DIRECTORY", "").strip()
    if template_directory_override and template_directory_override.strip():
        config["template_directory"] = template_directory_override.strip()
    elif env_template_directory:
        config["template_directory"] = env_template_directory
    else:
        config["template_directory"] = str(config["template_directory"])

    config["authz_base_url"] = os.environ.get(
        "AUTHZ_BASE_URL", str(config["authz_base_url"])
    )
    config["agent_sub"] = os.environ.get("AGENT_SUB", str(config["agent_sub"]))
    config["delegation_api_base_url"] = os.environ.get(
        "DELEGATION_API_BASE_URL", str(config["delegation_api_base_url"])
    )

    config["request_timeout_seconds"] = coerce_positive_int(
        os.environ.get(
            "REQUEST_TIMEOUT_SECONDS", str(config["request_timeout_seconds"])
        ),
        "REQUEST_TIMEOUT_SECONDS",
    )

    require_non_empty_string(str(config.get("domain", "")), "domain")
    require_non_empty_string(
        str(config.get("template_directory", "")), "template_directory"
    )
    require_non_empty_string(str(config.get("authz_base_url", "")), "authz_base_url")
    require_non_empty_string(str(config.get("agent_sub", "")), "agent_sub")

    return config


def handle_get_health(request: Request) -> dict[str, Any]:
    # Return an operational health response
    # why: orchestration/smoke tests
    # side effect: none.
    service: FlowPilotService = request.app.state.service
    return {
        "status": "ok",
        "service": str(request.app.state.config.get("service_name", "flowpilot-api")),
        "templates_loaded": int(service.get_template_count()),
        "workflows_in_memory": int(service.get_workflow_count()),
    }


def handle_get_workflow_templates(
    request: Request, token_claims: dict = Depends(security.verify_token)
) -> dict[str, Any]:
    # List available workflow templates
    # why: allow the client to pick a workflow
    # side effect: none.
    service: FlowPilotService = request.app.state.service
    result = {"templates": service.list_workflow_templates()}
    return result


def handle_get_workflows(
    request: Request, token_claims: dict = Depends(security.verify_token)
) -> dict[str, Any]:
    # List all workflows
    # why: allow clients to select an existing workflow for delegation
    # side effect: none.
    service: FlowPilotService = request.app.state.service
    result = {"workflows": service.list_workflows()}
    return result


def handle_post_workflows(
    request: Request, body: CreateWorkflowRequest, token_claims: dict = Depends(security.verify_token)
) -> dict[str, Any]:
    # Create a workflow from a template
    # assumptions: principal_sub is authenticated upstream
    # side effect: stores workflow in memory, creates delegation for AI agent.
    service: FlowPilotService = request.app.state.service
    try:
        # Extract user token for authorization check
        auth_header = request.headers.get("Authorization", "")
        user_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None
        
        # Check authorization before creating workflow
        service.check_authorization(
            action="create",
            user_sub=body.principal_sub,
            user_persona_title=body.persona_title,
            user_persona_circle=body.persona_circle,
            user_token=user_token,
            domain=body.domain,
        )
        
        # Already validated by Pydantic validators and authorized
        result = service.create_workflow_from_template(
            template_id=body.template_id,
            owner_sub=body.principal_sub,
            start_date=body.start_date,
            persona_title=body.persona_title,
            persona_circle=body.persona_circle,
            domain=body.domain,
        )

        # Auto-create delegation for AI agent to access the workflow
        workflow_id = result.get("workflow_id")
        agent_sub = request.app.state.config.get("agent_sub")

        if workflow_id and agent_sub:
            # Auto-create delegation for AI agent - this is critical for agent operation
            # Extract the user's token from the Authorization header to pass through
            auth_header = request.headers.get("Authorization", "")
            user_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None

            service.create_agent_delegation(
                workflow_id=workflow_id,
                owner_sub=body.principal_sub,
                agent_sub=agent_sub,
                user_token=user_token,
            )

        return result
    except PolicyDeniedError as exception:
        error_detail = {
            "detail": "Permission denied",
            "reason_codes": exception.reason_codes,
            "advice": exception.advice,
        }
        raise HTTPException(status_code=403, detail=error_detail) from exception
    except security.InputValidationError as exception:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(
                str(exception), INCLUDE_ERROR_DETAILS
            ),
        ) from exception
    except ValueError as exception:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(
                str(exception), INCLUDE_ERROR_DETAILS
            ),
        ) from exception


def handle_get_workflow(
    request: Request,
    workflow_id: str,
    persona_title: str,  # MANDATORY for authorization
    persona_circle: str,  # MANDATORY for authorization
    token_claims: dict = Depends(security.verify_token),
) -> dict[str, Any]:
    # Return one workflow record with authorization check
    # why: enforce read access control
    # side effect: none.
    service: FlowPilotService = request.app.state.service
    try:
        # Validate path parameter
        workflow_id = security.validate_id(workflow_id, "workflow_id", max_length=255)

        # Check authorization
        user_sub = token_claims.get("sub")
        if not user_sub:
            raise HTTPException(
                status_code=401, detail="Invalid token: missing sub claim"
            )
        
        # Validate persona_title and persona_circle are provided
        if not persona_title or not persona_title.strip():
            raise HTTPException(
                status_code=400, detail="persona_title query parameter is required for authorization"
            )
        if not persona_circle or not persona_circle.strip():
            raise HTTPException(
                status_code=400, detail="persona_circle query parameter is required for authorization"
            )

        # Extract raw token from request header for service-to-service calls
        auth_header = request.headers.get("authorization", "")
        user_token = auth_header[7:] if auth_header.lower().startswith("bearer ") else None

        authz_decision = service.check_authorization(
            action="read",
            workflow_id=workflow_id,
            user_sub=user_sub,
            user_persona_title=persona_title,
            user_persona_circle=persona_circle,
            user_token=user_token,
        )

        workflow_data = service.get_workflow(workflow_id=workflow_id)
        # Include authorization metadata in response for audit trail
        workflow_data["authorization"] = authz_decision
        return workflow_data
    except security.InputValidationError as exception:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(
                str(exception), INCLUDE_ERROR_DETAILS
            ),
        ) from exception
    except PolicyDeniedError as exception:
        error_detail = {
            "detail": "Permission denied",
            "reason_codes": exception.reason_codes,
            "advice": exception.advice,
        }
        raise HTTPException(status_code=403, detail=error_detail) from exception
    except KeyError as exception:
        raise HTTPException(status_code=404, detail="Workflow not found") from exception
    except ValueError as exception:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(
                str(exception), INCLUDE_ERROR_DETAILS
            ),
        ) from exception


def handle_get_workflow_items(
    request: Request,
    workflow_id: str,
    persona_title: str,  # MANDATORY for authorization
    persona_circle: str,  # MANDATORY for authorization
    user_sub: str = None,
    token_claims: dict = Depends(security.verify_token),
) -> dict[str, Any]:
    # Return the items for a workflow with authorization check
    # why: enforce read access control
    # side effect: none.
    # user_sub: Optional query parameter for service-to-service calls where the service account
    #           is making the request on behalf of a user
    service: FlowPilotService = request.app.state.service
    try:
        # Validate path parameter
        workflow_id = security.validate_id(workflow_id, "workflow_id", max_length=255)
        
        # Validate persona_title and persona_circle are provided
        if not persona_title or not persona_title.strip():
            raise HTTPException(
                status_code=400, detail="persona_title query parameter is required for authorization"
            )
        if not persona_circle or not persona_circle.strip():
            raise HTTPException(
                status_code=400, detail="persona_circle query parameter is required for authorization"
            )

        # Check authorization
        # If user_sub is provided as query parameter (service-to-service call), use that
        # Otherwise, extract from token (direct user call)
        if user_sub:
            # Service-to-service call: validate the query parameter
            user_sub = security.validate_id(user_sub, "user_sub", max_length=255)
        else:
            # Direct user call: extract from token
            user_sub = token_claims.get("sub")
            if not user_sub:
                raise HTTPException(
                    status_code=401, detail="Invalid token: missing sub claim"
                )

        # Extract raw token from request header for service-to-service calls
        auth_header = request.headers.get("authorization", "")
        user_token = auth_header[7:] if auth_header.lower().startswith("bearer ") else None

        authz_decision = service.check_authorization(
            action="read",
            workflow_id=workflow_id,
            user_sub=user_sub,
            user_persona_title=persona_title,
            user_persona_circle=persona_circle,
            user_token=user_token,
        )

        workflow_items_data = service.get_workflow_items(workflow_id=workflow_id)
        # Include authorization metadata in response for audit trail
        workflow_items_data["authorization"] = authz_decision
        return workflow_items_data
    except security.InputValidationError as exception:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(
                str(exception), INCLUDE_ERROR_DETAILS
            ),
        ) from exception
    except PolicyDeniedError as exception:
        error_detail = {
            "detail": "Permission denied",
            "reason_codes": exception.reason_codes,
            "advice": exception.advice,
        }
        raise HTTPException(status_code=403, detail=error_detail) from exception
    except KeyError as exception:
        raise HTTPException(status_code=404, detail="Workflow not found") from exception
    except ValueError as exception:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(
                str(exception), INCLUDE_ERROR_DETAILS
            ),
        ) from exception


def handle_post_execute_workflow_item(
    request: Request,
    workflow_id: str,
    workflow_item_id: str,
    body: ExecuteWorkflowItemRequest,
    token_claims: dict = Depends(security.verify_token),
) -> dict[str, Any]:
    # Execute one itinerary item with AuthZ enforcement
    # why: FlowPilot is PEP and delegates decisions to AuthZ/OPA.
    service: FlowPilotService = request.app.state.service

    try:
        # Validate path parameters
        workflow_id = security.validate_id(workflow_id, "workflow_id", max_length=255)
        workflow_item_id = security.validate_id(
            workflow_item_id, "workflow_item_id", max_length=255
        )

        # AuthZEN: Get principal_user object from request
        principal_user = body.get_principal_user()

        result = service.execute_workflow_item(
            workflow_id=workflow_id,
            workflow_item_id=workflow_item_id,
            principal_user=principal_user,
            dry_run=bool(body.dry_run),
        )

        return result
    except security.InputValidationError as exception:
        error_detail = security.sanitize_error_message(
            str(exception), INCLUDE_ERROR_DETAILS
        )
        raise HTTPException(status_code=400, detail=error_detail) from exception
    except PolicyDeniedError as exception:
        # Include reason_codes in the 403 response
        error_detail = {
            "detail": "Permission denied",
            "reason_codes": exception.reason_codes,
            "advice": exception.advice,
        }
        raise HTTPException(status_code=403, detail=error_detail) from exception
    except PermissionError as exception:
        # Fallback for other PermissionError cases
        raise HTTPException(status_code=403, detail="Permission denied") from exception
    except KeyError as exception:
        raise HTTPException(status_code=404, detail="Resource not found") from exception
    except ValueError as exception:
        error_detail = security.sanitize_error_message(
            str(exception), INCLUDE_ERROR_DETAILS
        )
        raise HTTPException(status_code=400, detail=error_detail) from exception


def create_app(config: dict[str, Any]) -> FastAPI:
    #
    # Create FastAPI API endpoints and wire routes
    #
    # side effect: reads filesystem for templates and stores service in app state.
    api = FastAPI(
        title="FlowPilot API",
        version="0.9.1",  # Updated: persona parameter now required
        # Limit request body size to 1MB (protects against large payload attacks)
        swagger_ui_parameters={"defaultModelsExpandDepth": -1},
    )
    api.state.config = config

    service = FlowPilotService(config=config)
    service.load_templates()
    api.state.service = service

    # Add exception handler to log all HTTP exceptions
    @api.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        # Log all non-200 HTTP exceptions for debugging
        auth_header = request.headers.get("authorization", "")
        token_preview = (
            auth_header[:50] + "..." if len(auth_header) > 50 else auth_header
        )
        print(
            f"[HTTPException {exc.status_code}] Path: {request.url.path}, Detail: {exc.detail}, Auth header: {token_preview}",
            flush=True,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
    
    # Add global exception handler to log all unhandled exceptions
    @api.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        import traceback
        error_traceback = traceback.format_exc()
        print(
            f"[UNHANDLED EXCEPTION] Path: {request.url.path}, Error: {str(exc)}\n{error_traceback}",
            flush=True,
        )
        error_detail = str(exc) if INCLUDE_ERROR_DETAILS else "Internal server error"
        return JSONResponse(
            status_code=500,
            content={"detail": error_detail},
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
        "/v1/workflow-templates",
        handle_get_workflow_templates,
        methods=["GET"],
        dependencies=[Depends(security.verify_token)],
    )
    api.add_api_route(
        "/v1/workflows",
        handle_get_workflows,
        methods=["GET"],
        dependencies=[Depends(security.verify_token)],
    )
    api.add_api_route(
        "/v1/workflows",
        handle_post_workflows,
        methods=["POST"],
        dependencies=[Depends(security.verify_token)],
    )
    api.add_api_route(
        "/v1/workflows/{workflow_id}",
        handle_get_workflow,
        methods=["GET"],
        dependencies=[Depends(security.verify_token)],
    )
    api.add_api_route(
        "/v1/workflows/{workflow_id}/items",
        handle_get_workflow_items,
        methods=["GET"],
        dependencies=[Depends(security.verify_token)],
    )
    api.add_api_route(
        "/v1/workflows/{workflow_id}/items/{workflow_item_id}/execute",
        handle_post_execute_workflow_item,
        methods=["POST"],
        dependencies=[Depends(security.verify_token)],
    )

    return api


def parse_args() -> argparse.Namespace:
    # Parse CLI args for container entrypoints
    # why: keep configuration explicit and reproducible.
    parser = argparse.ArgumentParser(description="FlowPilot API service")
    parser.add_argument(
        "--config", dest="config_path", default=None, help="Path to JSON config file."
    )
    parser.add_argument(
        "--templates-dir",
        dest="templates_dir",
        default=None,
        help="Override template directory.",
    )
    parser.add_argument("--host", dest="host", default="0.0.0.0", help="Bind host.")
    parser.add_argument(
        "--port", dest="port", type=int, default=8003, help="Bind port."
    )
    parser.add_argument(
        "--reload",
        dest="reload",
        action="store_true",
        help="Enable auto-reload (local dev).",
    )
    return parser.parse_args()


def main() -> int:
    # Build config and start Uvicorn
    # side effect: runs a web server and blocks
    # returns non-zero on config errors.
    args = parse_args()
    try:
        config = build_config(
            config_path=args.config_path, template_directory_override=args.templates_dir
        )
    except ValueError as exception:
        print(f"[flowpilot-api] Configuration error: {exception}")
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
        # Security: Limit request body size to prevent memory exhaustion
        limit_max_requests=uvicorn_max_requests,  # Max requests before worker restart
        limit_concurrency=uvicorn_max_concurrency,  # Max concurrent connections
        timeout_keep_alive=uvicorn_keepalive_timeout,  # Keep-alive timeout
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
