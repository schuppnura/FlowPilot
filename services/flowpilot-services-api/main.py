# FlowPilot Services API - FastAPI Application
#
# Domain backend for the travel demo. This is the system of record that owns workflow
# state and enforces authorization as a Policy Enforcement Point (PEP).
#
# Key endpoints:
# - GET /v1/trip-templates: List available trip templates
# - POST /v1/trips: Create a new trip from a template
# - GET /v1/trips/{trip_id}: Get trip metadata
# - GET /v1/trips/{trip_id}/itinerary: Get trip itinerary items
# - POST /v1/trips/{trip_id}/itinerary-items/{item_id}/execute: Execute item with AuthZ check
# - GET /health: Health check with trip/template counts
#
# All endpoints (except health) require bearer token authentication.
# Domain-specific: Travel workflows with flights, hotels, restaurants, museums, trains.

from __future__ import annotations

import argparse
import os
from typing import Any, Dict, Optional

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel

from core import FlowPilotService
from sanitizer import RequestSizeLimiterMiddleware, get_max_request_size
from shared_auth import bearer_scheme, verify_token
from utils import load_json_object, merge_config, parse_positive_int, validate_non_empty_string


DEFAULT_CONFIG: Dict[str, Any] = {
    "service_name": "flowpilot-api",
    "log_level": "info",
    "domain": "flowpilot",

    # Templates
    "template_directory": "../data/trip_templates",

    # AuthZ integration
    "authz_base_url": "http://flowpilot-authz-api:8002",
    "agent_sub": "agent_flowpilot_1",

    # Operational
    "request_timeout_seconds": 10,
}


class CreateTripRequest(BaseModel):
    template_id: str
    principal_sub: str


class ExecuteItineraryItemRequest(BaseModel):
    principal_sub: str
    dry_run: bool = True


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
        "trips_in_memory": int(service.get_trip_count()),
    }


def handle_get_trip_templates(request: Request) -> Dict[str, Any]:
    # List available trip templates
    # why: allow the client to pick a workflow
    # side effect: none.
    service: FlowPilotService = request.app.state.service
    return {"templates": service.list_trip_templates()}


def handle_post_trips(request: Request, body: CreateTripRequest) -> Dict[str, Any]:
    # Create a trip from a template
    # assumptions: principal_sub is authenticated upstream
    # side effect: stores trip in memory.
    service: FlowPilotService = request.app.state.service
    try:
        template_id = validate_non_empty_string(body.template_id, "template_id")
        principal_sub = validate_non_empty_string(body.principal_sub, "principal_sub")
        return service.create_trip_from_template(template_id=template_id, owner_sub=principal_sub)
    except ValueError as exception:
        raise HTTPException(status_code=400, detail=str(exception)) from exception


def handle_get_trip(request: Request, trip_id: str) -> Dict[str, Any]:
    # Return one trip record
    # why: demo visibility and debugging
    # side effect: none.
    service: FlowPilotService = request.app.state.service
    try:
        return service.get_trip(trip_id=validate_non_empty_string(trip_id, "trip_id"))
    except KeyError as exception:
        raise HTTPException(status_code=404, detail=str(exception)) from exception
    except ValueError as exception:
        raise HTTPException(status_code=400, detail=str(exception)) from exception


def handle_get_itinerary(request: Request, trip_id: str) -> Dict[str, Any]:
    # Return the itinerary for a trip
    # why: agent-runner lists items from here
    # side effect: none.
    service: FlowPilotService = request.app.state.service
    try:
        return service.get_itinerary(trip_id=validate_non_empty_string(trip_id, "trip_id"))
    except KeyError as exception:
        raise HTTPException(status_code=404, detail=str(exception)) from exception
    except ValueError as exception:
        raise HTTPException(status_code=400, detail=str(exception)) from exception


def handle_post_execute_itinerary_item(request: Request, trip_id: str, item_id: str, body: ExecuteItineraryItemRequest) -> Dict[str, Any]:
    # Execute one itinerary item with AuthZ enforcement
    # why: FlowPilot is PEP and delegates decisions to AuthZ/***REMOVED***.
    service: FlowPilotService = request.app.state.service
    try:
        return service.execute_itinerary_item(
            trip_id=validate_non_empty_string(trip_id, "trip_id"),
            item_id=validate_non_empty_string(item_id, "item_id"),
            principal_sub=validate_non_empty_string(body.principal_sub, "principal_sub"),
            dry_run=bool(body.dry_run),
        )
    except PermissionError as exception:
        raise HTTPException(status_code=403, detail=str(exception)) from exception
    except KeyError as exception:
        raise HTTPException(status_code=404, detail=str(exception)) from exception
    except ValueError as exception:
        raise HTTPException(status_code=400, detail=str(exception)) from exception


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

    # Health check - no auth required
    api.add_api_route("/health", handle_get_health, methods=["GET"])

    # All other endpoints require authentication
    api.add_api_route("/v1/trip-templates", handle_get_trip_templates, methods=["GET"], dependencies=[Depends(bearer_scheme)])
    api.add_api_route("/v1/trips", handle_post_trips, methods=["POST"], dependencies=[Depends(bearer_scheme)])
    api.add_api_route("/v1/trips/{trip_id}", handle_get_trip, methods=["GET"], dependencies=[Depends(bearer_scheme)])
    api.add_api_route("/v1/trips/{trip_id}/itinerary", handle_get_itinerary, methods=["GET"], dependencies=[Depends(bearer_scheme)])
    api.add_api_route("/v1/trips/{trip_id}/itinerary-items/{item_id}/execute", handle_post_execute_itinerary_item, methods=["POST"], dependencies=[Depends(bearer_scheme)])

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
        limit_max_requests=10000,  # Max requests before worker restart
        limit_concurrency=100,      # Max concurrent connections
        timeout_keep_alive=5,        # Keep-alive timeout
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
