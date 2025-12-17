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

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel

from core import execute_workflow_run, normalize_workflow_id
from sanitizer import RequestSizeLimiterMiddleware, get_max_request_size
from shared_auth import bearer_scheme, verify_token
from utils import load_json_object, merge_config, parse_positive_int, validate_non_empty_string


DEFAULT_CONFIG: Dict[str, Any] = {
    "service_name": "agent-runner-api",
    "log_level": "info",

    # Workflow (domain) API base. In this demo stack it points to the FlowPilot API.
    "workflow_base_url": "http://flowpilot-api:8003",

    # Workflow item listing and execution endpoints. Defaults map to the FlowPilot trip itinerary model.
    "workflow_items_path_template": "/v1/trips/{workflow_id}/itinerary",
    "workflow_item_execute_path_template": "/v1/trips/{workflow_id}/itinerary-items/{workflow_item_id}/execute",

    # Operational timeouts.
    "request_timeout_seconds": 10,
}


class WorkflowRunRequest(BaseModel):
    workflow_id: Optional[str] = None
    trip_id: Optional[str] = None
    principal_sub: str
    dry_run: bool = True


def build_config(config_path: Optional[str]) -> Dict[str, Any]:
    # Build runtime config from defaults, optional JSON override, and env vars
    # side effect: reads env and file.
    config = dict(DEFAULT_CONFIG)

    if config_path:
        config = merge_config(config, load_json_object(config_path))

    config["log_level"] = os.environ.get("LOG_LEVEL", str(config["log_level"]))
    config["workflow_base_url"] = os.environ.get("WORKFLOW_BASE_URL", os.environ.get("FLOWPILOT_BASE_URL", str(config["workflow_base_url"])))
    config["workflow_items_path_template"] = os.environ.get("WORKFLOW_ITEMS_PATH_TEMPLATE", str(config["workflow_items_path_template"]))
    config["workflow_item_execute_path_template"] = os.environ.get(
        "WORKFLOW_ITEM_EXECUTE_PATH_TEMPLATE",
        str(config["workflow_item_execute_path_template"]),
    )

    config["request_timeout_seconds"] = parse_positive_int(
        os.environ.get("REQUEST_TIMEOUT_SECONDS", str(config["request_timeout_seconds"])),
        "REQUEST_TIMEOUT_SECONDS",
    )

    validate_non_empty_string(str(config.get("workflow_base_url", "")), "workflow_base_url")
    validate_non_empty_string(str(config.get("workflow_items_path_template", "")), "workflow_items_path_template")
    validate_non_empty_string(str(config.get("workflow_item_execute_path_template", "")), "workflow_item_execute_path_template")

    return config


def handle_get_health(_request: Request) -> Dict[str, str]:
    # Provide a simple health response for smoke tests
    # assumption: no downstream checks here by design.
    return {"status": "ok"}


def handle_post_workflow_runs(request: Request, body: WorkflowRunRequest) -> Dict[str, Any]:
    # Execute a workflow by iterating items and delegating execution to domain service endpoints (domain is PEP).
    config: Dict[str, Any] = request.app.state.config

    try:
        workflow_id = normalize_workflow_id(trip_id=body.trip_id, workflow_id=body.workflow_id)
        principal_sub = validate_non_empty_string(body.principal_sub, "principal_sub")
        result = execute_workflow_run(config=config, workflow_id=workflow_id, principal_sub=principal_sub, dry_run=bool(body.dry_run))
    except ValueError as exception:
        raise HTTPException(status_code=400, detail=str(exception)) from exception

    return result


def handle_post_agent_runs(request: Request, body: WorkflowRunRequest) -> Dict[str, Any]:
    # Backward-compatible alias for older clients
    # why: preserve existing scripts and desktop app wiring.
    return handle_post_workflow_runs(request, body)


def create_app(config: Dict[str, Any]) -> FastAPI:
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
    
    # Add request size limiting middleware
    api.add_middleware(RequestSizeLimiterMiddleware, max_size=get_max_request_size())

    # Health check - no auth required
    api.add_api_route("/health", handle_get_health, methods=["GET"])
    
    # All other endpoints require authentication
    api.add_api_route("/v1/workflow-runs", handle_post_workflow_runs, methods=["POST"], dependencies=[Depends(bearer_scheme)])
    api.add_api_route("/v1/agent-runs", handle_post_agent_runs, methods=["POST"], dependencies=[Depends(bearer_scheme)])

    return api


def parse_args() -> argparse.Namespace:
    # Parse CLI args for container entrypoints
    # assumption: used only for bootstrapping, not business logic.
    parser = argparse.ArgumentParser(description="Agent Runner API service")
    parser.add_argument("--config", dest="config_path", default=None, help="Path to JSON config file.")
    parser.add_argument("--host", dest="host", default="0.0.0.0", help="Bind host.")
    parser.add_argument("--port", dest="port", type=int, default=8004, help="Bind port.")
    parser.add_argument("--reload", dest="reload", action="store_true", help="Enable auto-reload (local dev).")
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
    uvicorn.run(
        api,
        host=str(args.host),
        port=int(args.port),
        reload=bool(args.reload),
        log_level=str(config.get("log_level", "info")),
        # Security: Limit request body size to prevent memory exhaustion
        limit_max_requests=10000,  # Max requests before worker restart
        limit_concurrency=100,      # Max concurrent connections
        timeout_keep_alive=5,        # Keep-alive timeout
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
