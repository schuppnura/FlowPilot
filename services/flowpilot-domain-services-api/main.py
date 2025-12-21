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
from pydantic import BaseModel, Field, validator

import security
from core import FlowPilotService
from utils import load_json_object, merge_config, parse_positive_int, validate_non_empty_string

# Environment flag for detailed error messages (disable in production)
INCLUDE_ERROR_DETAILS = os.environ.get("INCLUDE_ERROR_DETAILS", "1") == "1"


DEFAULT_CONFIG: Dict[str, Any] = {
    "service_name": "flowpilot-api",
    "log_level": "info",
    "domain": "flowpilot",

    # Templates
    "template_directory": "../data/trip_templates",

    # AuthZ integration
    "authz_base_url": "http://flowpilot-authz-api:8000",
    "agent_sub": "agent_flowpilot_1",

    # Operational
    "request_timeout_seconds": 10,
}


class CreateWorkflowRequest(BaseModel):
    template_id: str = Field(..., min_length=1, max_length=255, description="Template identifier")
    principal_sub: str = Field(..., min_length=1, max_length=255, description="Principal subject")
    start_date: str = Field(..., description="ISO 8601 date string (YYYY-MM-DD)")
    
    @validator('template_id')
    def validate_template_id(cls, v: str) -> str:
        return security.validate_id(v, "template_id", max_length=255)
    
    @validator('principal_sub')
    def sanitize_principal_sub(cls, v: str) -> str:
        return security.sanitize_string(v, max_length=255)
    
    @validator('start_date')
    def validate_start_date(cls, v: str) -> str:
        return security.validate_iso_date(v, "start_date")


class ExecuteWorkflowItemRequest(BaseModel):
    principal_sub: str = Field(..., min_length=1, max_length=255, description="Principal subject")
    dry_run: bool = Field(default=True, description="Dry run flag")
    
    @validator('principal_sub')
    def sanitize_principal_sub(cls, v: str) -> str:
        return security.sanitize_string(v, max_length=255)


def build_config(config_path: Optional[str], template_directory_override: Optional[str]) -> Dict[str, Any]:
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

    config["authz_base_url"] = os.environ.get("AUTHZ_BASE_URL", str(config["authz_base_url"]))
    config["agent_sub"] = os.environ.get("AGENT_SUB", str(config["agent_sub"]))

    config["request_timeout_seconds"] = parse_positive_int(
        os.environ.get("REQUEST_TIMEOUT_SECONDS", str(config["request_timeout_seconds"])),
        "REQUEST_TIMEOUT_SECONDS",
    )

    validate_non_empty_string(str(config.get("domain", "")), "domain")
    validate_non_empty_string(str(config.get("template_directory", "")), "template_directory")
    validate_non_empty_string(str(config.get("authz_base_url", "")), "authz_base_url")
    validate_non_empty_string(str(config.get("agent_sub", "")), "agent_sub")

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


def handle_get_workflow_templates(request: Request) -> Dict[str, Any]:
    # List available workflow templates
    # why: allow the client to pick a workflow
    # side effect: none.
    service: FlowPilotService = request.app.state.service
    return {"templates": service.list_workflow_templates()}


def handle_post_workflows(request: Request, body: CreateWorkflowRequest) -> Dict[str, Any]:
    # Create a workflow from a template
    # assumptions: principal_sub is authenticated upstream
    # side effect: stores workflow in memory.
    service: FlowPilotService = request.app.state.service
    try:
        # Already validated by Pydantic validators
        return service.create_workflow_from_template(
            template_id=body.template_id,
            owner_sub=body.principal_sub,
            start_date=body.start_date
        )
    except security.InputValidationError as exception:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(str(exception), INCLUDE_ERROR_DETAILS)
        ) from exception
    except ValueError as exception:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(str(exception), INCLUDE_ERROR_DETAILS)
        ) from exception


def handle_get_workflow(request: Request, workflow_id: str) -> Dict[str, Any]:
    # Return one workflow record
    # why: demo visibility and debugging
    # side effect: none.
    service: FlowPilotService = request.app.state.service
    try:
        # Validate path parameter
        workflow_id = security.validate_id(workflow_id, "workflow_id", max_length=255)
        return service.get_workflow(workflow_id=workflow_id)
    except security.InputValidationError as exception:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(str(exception), INCLUDE_ERROR_DETAILS)
        ) from exception
    except KeyError as exception:
        raise HTTPException(status_code=404, detail="Workflow not found") from exception
    except ValueError as exception:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(str(exception), INCLUDE_ERROR_DETAILS)
        ) from exception


def handle_get_workflow_items(request: Request, workflow_id: str) -> Dict[str, Any]:
    # Return the items for a workflow
    # why: agent-runner lists items from here
    # side effect: none.
    service: FlowPilotService = request.app.state.service
    try:
        # Validate path parameter
        workflow_id = security.validate_id(workflow_id, "workflow_id", max_length=255)
        return service.get_workflow_items(workflow_id=workflow_id)
    except security.InputValidationError as exception:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(str(exception), INCLUDE_ERROR_DETAILS)
        ) from exception
    except KeyError as exception:
        raise HTTPException(status_code=404, detail="Workflow not found") from exception
    except ValueError as exception:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(str(exception), INCLUDE_ERROR_DETAILS)
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
    try:
        # Validate path parameters
        workflow_id = security.validate_id(workflow_id, "workflow_id", max_length=255)
        workflow_item_id = security.validate_id(workflow_item_id, "workflow_item_id", max_length=255)
        # principal_sub already validated by Pydantic
        
        # Extract raw token from Authorization header
        user_token = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            user_token = auth_header[7:]  # Remove "Bearer " prefix
        
        return service.execute_workflow_item(
            workflow_id=workflow_id,
            workflow_item_id=workflow_item_id,
            principal_sub=body.principal_sub,
            dry_run=bool(body.dry_run),
            user_token=user_token,
        )
    except security.InputValidationError as exception:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(str(exception), INCLUDE_ERROR_DETAILS)
        ) from exception
    except PermissionError as exception:
        raise HTTPException(status_code=403, detail="Permission denied") from exception
    except KeyError as exception:
        raise HTTPException(status_code=404, detail="Resource not found") from exception
    except ValueError as exception:
        raise HTTPException(
            status_code=400,
            detail=security.sanitize_error_message(str(exception), INCLUDE_ERROR_DETAILS)
        ) from exception


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
    
    # Add security middlewares
    api.add_middleware(security.SecurityHeadersMiddleware)
    api.add_middleware(security.RequestSizeLimiterMiddleware, max_size=security.get_max_request_size())

    # Health check - no auth required
    api.add_api_route("/health", handle_get_health, methods=["GET"])

    # All other endpoints require authentication
    api.add_api_route("/v1/workflow-templates", handle_get_workflow_templates, methods=["GET"], dependencies=[Depends(security.verify_token)])
    api.add_api_route("/v1/workflows", handle_post_workflows, methods=["POST"], dependencies=[Depends(security.verify_token)])
    api.add_api_route("/v1/workflows/{workflow_id}", handle_get_workflow, methods=["GET"], dependencies=[Depends(security.verify_token)])
    api.add_api_route("/v1/workflows/{workflow_id}/items", handle_get_workflow_items, methods=["GET"], dependencies=[Depends(security.verify_token)])
    api.add_api_route("/v1/workflows/{workflow_id}/items/{workflow_item_id}/execute", handle_post_execute_workflow_item, methods=["POST"], dependencies=[Depends(security.verify_token)])

    return api


def parse_args() -> argparse.Namespace:
    # Parse CLI args for container entrypoints
    # why: keep configuration explicit and reproducible.
    parser = argparse.ArgumentParser(description="FlowPilot API service")
    parser.add_argument("--config", dest="config_path", default=None, help="Path to JSON config file.")
    parser.add_argument("--templates-dir", dest="templates_dir", default=None, help="Override template directory.")
    parser.add_argument("--host", dest="host", default="0.0.0.0", help="Bind host.")
    parser.add_argument("--port", dest="port", type=int, default=8003, help="Bind port.")
    parser.add_argument("--reload", dest="reload", action="store_true", help="Enable auto-reload (local dev).")
    return parser.parse_args()


def main() -> int:
    # Build config and start Uvicorn
    # side effect: runs a web server and blocks
    # returns non-zero on config errors.
    args = parse_args()
    try:
        config = build_config(config_path=args.config_path, template_directory_override=args.templates_dir)
    except ValueError as exception:
        print(f"[flowpilot-api] Configuration error: {exception}")
        return 2

    api = create_app(config=config)
    uvicorn.run(
        api,
        host=str(args.host),
        port=int(args.port),
        reload=bool(args.reload),
        log_level=str(config.get("log_level", "info")),
        # Security: Limit request body size to prevent memory exhaustion
        limit_max_requests=10000,    # Max requests before worker restart
        limit_concurrency=100,       # Max concurrent connections
        timeout_keep_alive=5,        # Keep-alive timeout
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
