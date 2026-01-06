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

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

import security
import api_logging
from core import FlowPilotService, PolicyDeniedError
from utils import (
    load_json_object,
    merge_config,
    coerce_positive_int,
    require_non_empty_string,
)

# Environment flag for detailed error messages (disable in production)
INCLUDE_ERROR_DETAILS = os.environ.get("INCLUDE_ERROR_DETAILS", "1") == "1"

# AI Agent persona configuration
AI_AGENT_PERSONA = os.environ.get("AI_AGENT_PERSONA", "ai-agent")


DEFAULT_CONFIG: Dict[str, Any] = {
    "service_name": "flowpilot-api",
    "log_level": "info",
    "domain": "flowpilot",
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
    persona: Optional[str] = Field(
        None, max_length=255, description="Selected persona for the user"
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

    @validator("persona")
    def sanitize_persona(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return security.sanitize_string(v, 255)


class ExecuteWorkflowItemRequest(BaseModel):
    # AuthZEN: Accept principal_user object (preferred) or principal_sub (backward compatibility)
    principal_user: Optional[Dict[str, Any]] = Field(
        None, description="Principal-user object (AuthZEN format)"
    )
    principal_sub: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Principal subject (backward compatibility)",
    )
    dry_run: bool = Field(default=True, description="Dry run flag")

    @validator("principal_sub")
    def sanitize_principal_sub(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return security.sanitize_string(v, 255)

    def get_principal_user(self) -> Dict[str, Any]:
        # AuthZEN: Return principal_user if provided, otherwise construct from principal_sub
        if self.principal_user:
            # Return as-is, preserving persona and all other fields
            return self.principal_user
        if self.principal_sub:
            return {"type": "user", "id": self.principal_sub}
        raise ValueError("Either principal_user or principal_sub must be provided")


def build_config(
    config_path: Optional[str], template_directory_override: Optional[str]
) -> Dict[str, Any]:
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


def handle_get_health(request: Request) -> Dict[str, Any]:
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
) -> Dict[str, Any]:
    # List available workflow templates
    # why: allow the client to pick a workflow
    # side effect: none.
    try:
        api_logging.log_api_request(
            method="GET",
            path="/v1/workflow-templates",
            token_claims=token_claims,
            request=request,
        )
        service: FlowPilotService = request.app.state.service
        result = {"templates": service.list_workflow_templates()}
        api_logging.log_api_response(
            method="GET",
            path="/v1/workflow-templates",
            status_code=200,
            response_body=result,
        )
        return result
    except HTTPException as e:
        api_logging.log_api_response(
            method="GET",
            path="/v1/workflow-templates",
            status_code=e.status_code,
            error=str(e.detail) if hasattr(e, "detail") else str(e),
        )
        raise
    except Exception as e:
        api_logging.log_api_response(
            method="GET", path="/v1/workflow-templates", status_code=500, error=str(e)
        )
        raise


def handle_get_workflows(
    request: Request, token_claims: dict = Depends(security.verify_token)
) -> Dict[str, Any]:
    # List all workflows
    # why: allow clients to select an existing workflow for delegation
    # side effect: none.
    try:
        api_logging.log_api_request(
            method="GET",
            path="/v1/workflows",
            token_claims=token_claims,
            request=request,
        )
        service: FlowPilotService = request.app.state.service
        result = {"workflows": service.list_workflows()}
        api_logging.log_api_response(
            method="GET", path="/v1/workflows", status_code=200, response_body=result
        )
        return result
    except HTTPException as e:
        api_logging.log_api_response(
            method="GET",
            path="/v1/workflows",
            status_code=e.status_code,
            error=str(e.detail) if hasattr(e, "detail") else str(e),
        )
        raise
    except Exception as e:
        api_logging.log_api_response(
            method="GET", path="/v1/workflows", status_code=500, error=str(e)
        )
        raise


def handle_post_workflows(
    request: Request, body: CreateWorkflowRequest
) -> Dict[str, Any]:
    # Create a workflow from a template
    # assumptions: principal_sub is authenticated upstream
    # side effect: stores workflow in memory, creates delegation for AI agent.
    service: FlowPilotService = request.app.state.service
    try:
        # Already validated by Pydantic validators
        result = service.create_workflow_from_template(
            template_id=body.template_id,
            owner_sub=body.principal_sub,
            start_date=body.start_date,
            persona=body.persona,
        )
        
        # Auto-create delegation for AI agent to access the workflow
        workflow_id = result.get("workflow_id")
        agent_sub = request.app.state.config.get("agent_sub")
        
        if workflow_id and agent_sub:
            try:
                service.create_agent_delegation(
                    workflow_id=workflow_id,
                    owner_sub=body.principal_sub,
                    agent_sub=agent_sub,
                )
                print(f"[handle_post_workflows] Auto-created delegation for workflow {workflow_id} to agent {agent_sub}", flush=True)
            except Exception as delegation_error:
                # Log but don't fail workflow creation if delegation fails
                print(f"[handle_post_workflows] WARNING: Failed to create agent delegation: {delegation_error}", flush=True)
        
        return result
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
    persona: str = None,
    token_claims: dict = Depends(security.verify_token),
) -> Dict[str, Any]:
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
            raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")
        
        service.check_read_authorization(
            workflow_id=workflow_id,
            user_sub=user_sub,
            user_persona=persona,
        )
        
        return service.get_workflow(workflow_id=workflow_id)
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
    persona: str = None,
    user_sub: str = None,
    token_claims: dict = Depends(security.verify_token),
) -> Dict[str, Any]:
    # Return the items for a workflow with authorization check
    # why: enforce read access control
    # side effect: none.
    # user_sub: Optional query parameter for service-to-service calls where the service account
    #           is making the request on behalf of a user
    service: FlowPilotService = request.app.state.service
    try:
        # Validate path parameter
        workflow_id = security.validate_id(workflow_id, "workflow_id", max_length=255)
        
        # Check authorization
        # If user_sub is provided as query parameter (service-to-service call), use that
        # Otherwise, extract from token (direct user call)
        if user_sub:
            # Service-to-service call: validate the query parameter
            user_sub = security.validate_id(user_sub, "user_sub", max_length=255)
            print(f"[handle_get_workflow_items] Using user_sub from query param: {user_sub}", flush=True)
        else:
            # Direct user call: extract from token
            user_sub = token_claims.get("sub")
            if not user_sub:
                raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")
            print(f"[handle_get_workflow_items] Using user_sub from token: {user_sub}", flush=True)
        
        # If no persona provided and this is the agent service account, use configured AI agent persona
        user_persona = persona
        agent_sub = request.app.state.service._config.get("agent_sub")
        if not user_persona and agent_sub and user_sub == agent_sub:
            user_persona = AI_AGENT_PERSONA
            print(f"[handle_get_workflow_items] Agent detected, using {AI_AGENT_PERSONA} persona", flush=True)
        
        print(f"[handle_get_workflow_items] Token sub={token_claims.get('sub')}, user_sub={user_sub}, persona={user_persona}", flush=True)
        
        service.check_read_authorization(
            workflow_id=workflow_id,
            user_sub=user_sub,
            user_persona=user_persona,
        )
        
        return service.get_workflow_items(workflow_id=workflow_id)
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
) -> Dict[str, Any]:
    # Execute one itinerary item with AuthZ enforcement
    # why: FlowPilot is PEP and delegates decisions to AuthZ/***REMOVED***.
    service: FlowPilotService = request.app.state.service

    # Log request
    api_logging.log_api_request(
        method="POST",
        path=f"/v1/workflows/{workflow_id}/items/{workflow_item_id}/execute",
        request_body=body.dict() if hasattr(body, "dict") else body,
        token_claims=token_claims,
        request=request,
        path_params={"workflow_id": workflow_id, "workflow_item_id": workflow_item_id},
    )

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

        # Log response
        api_logging.log_api_response(
            method="POST",
            path=f"/v1/workflows/{workflow_id}/items/{workflow_item_id}/execute",
            status_code=200,
            response_body=result,
        )

        return result
    except security.InputValidationError as exception:
        error_detail = security.sanitize_error_message(
            str(exception), INCLUDE_ERROR_DETAILS
        )
        api_logging.log_api_response(
            method="POST",
            path=f"/v1/workflows/{workflow_id}/items/{workflow_item_id}/execute",
            status_code=400,
            error=error_detail,
        )
        raise HTTPException(status_code=400, detail=error_detail) from exception
    except PolicyDeniedError as exception:
        # Include reason_codes in the 403 response
        error_detail = {
            "detail": "Permission denied",
            "reason_codes": exception.reason_codes,
            "advice": exception.advice,
        }
        api_logging.log_api_response(
            method="POST",
            path=f"/v1/workflows/{workflow_id}/items/{workflow_item_id}/execute",
            status_code=403,
            error=str(error_detail),
        )
        raise HTTPException(status_code=403, detail=error_detail) from exception
    except PermissionError as exception:
        # Fallback for other PermissionError cases
        api_logging.log_api_response(
            method="POST",
            path=f"/v1/workflows/{workflow_id}/items/{workflow_item_id}/execute",
            status_code=403,
            error="Permission denied",
        )
        raise HTTPException(status_code=403, detail="Permission denied") from exception
    except KeyError as exception:
        api_logging.log_api_response(
            method="POST",
            path=f"/v1/workflows/{workflow_id}/items/{workflow_item_id}/execute",
            status_code=404,
            error="Resource not found",
        )
        raise HTTPException(status_code=404, detail="Resource not found") from exception
    except ValueError as exception:
        error_detail = security.sanitize_error_message(
            str(exception), INCLUDE_ERROR_DETAILS
        )
        api_logging.log_api_response(
            method="POST",
            path=f"/v1/workflows/{workflow_id}/items/{workflow_item_id}/execute",
            status_code=400,
            error=error_detail,
        )
        raise HTTPException(status_code=400, detail=error_detail) from exception


def create_app(config: Dict[str, Any]) -> FastAPI:
    #
    # Create FastAPI API endpoints and wire routes
    #
    # side effect: reads filesystem for templates and stores service in app state.
    api = FastAPI(
        title="FlowPilot API",
        version="0.9.0",
        # Limit request body size to 1MB (protects against large payload attacks)
        swagger_ui_parameters={"defaultModelsExpandDepth": -1},
    )
    api.state.config = config

    service = FlowPilotService(config=config)
    service.load_templates()
    api.state.service = service

    # Add exception handler to log authentication errors
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
