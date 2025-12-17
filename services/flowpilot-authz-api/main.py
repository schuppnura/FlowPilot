from __future__ import annotations

import argparse
import os
from typing import Any, Dict, Optional

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from core import (
    AuthzService,
    EvaluateResponseModel,
)
from sanitizer import RequestSizeLimiterMiddleware, get_max_request_size
from shared_auth import bearer_scheme, verify_token
from utils import load_json_object, merge_config, parse_positive_float, parse_positive_int, validate_non_empty_string


DEFAULT_CONFIG: Dict[str, Any] = {
    "service_name": "authz-api",
    "log_level": "info",

    # Workflow service (FlowPilot today
    # other verticals later).
    "workflow_base_url": "http://flowpilot-api:8003",

    # ***REMOVED*** Directory (Reader gateway by default in this demo stack).
    "***REMOVED***_dir_base": "http://***REMOVED***:9393",
    "***REMOVED***_check_path": "/api/v3/directory/check",
    "***REMOVED***_timeout_connect_seconds": 2.0,
    "***REMOVED***_timeout_read_seconds": 8.0,
    "***REMOVED***_trace_default": False,

    # Workflow lookup endpoints (kept generic so other verticals can re-use authz-api).
    "workflow_owner_path_template": "/v1/trips/{workflow_id}",
    "workflow_itinerary_path_template": "/v1/trips/{workflow_id}/itinerary",

    # How to find a workflow-item identifier in the incoming resource JSON.
    "workflow_item_id_property_names": ["workflow_item_id", "item_id"],

    # Action-to-relation mapping for ***REMOVED*** (can be extended without changing code).
    "action_relation_map": {"book": "can_execute"},

    # For progressive profiling: required identity-presence fields per workflow item kind.
    # These are presence flags only. The actual PII values remain in IdP and are not stored here.
    "required_identity_fields_default": [],
    "required_identity_fields_by_item_kind": {
        "flight": ["full_name", "phone_number", "passport_number", "payment_method"],
        "hotel": ["full_name", "phone_number", "payment_method"],
        "restaurant": [],
        "museum": [],
        "train": ["full_name", "phone_number", "payment_method"],
    },

    # Operational defaults.
    "request_timeout_seconds": 10,
}


class AuthZenLikeActorModel(BaseModel):
    type: str = Field(..., description="Actor type (e.g., 'agent' or 'user').")
    id: str = Field(..., description="Actor identifier. For agents: agent_sub; for users: subject_sub.")

    model_config = {"extra": "allow"}


class AuthZenLikeActionModel(BaseModel):
    name: str = Field(..., description="Action name (e.g., 'book').")
    properties: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class AuthZenLikeResourceModel(BaseModel):
    type: str = Field(..., description="Resource type (e.g., 'workflow').")
    id: str = Field(..., description="Workflow id (e.g., trip id).")
    properties: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class AuthZenLikeContextModel(BaseModel):
    principal: Dict[str, Any] = Field(default_factory=dict, description="Principal context; principal.id must be sub UUID.")
    attributes: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class AuthZenLikeOptionsModel(BaseModel):
    dry_run: bool = Field(default=True, description="If true, simulate decisions and prefer advice over hard-deny for missing profile.")
    explain: bool = Field(default=True, description="If true, return debug advice/traces where available.")
    trace: Optional[bool] = Field(default=None, description="If set, overrides ***REMOVED*** trace behavior.")

    model_config = {"extra": "allow"}


class EvaluateRequestModel(BaseModel):
    subject: AuthZenLikeActorModel
    action: AuthZenLikeActionModel
    resource: AuthZenLikeResourceModel
    context: AuthZenLikeContextModel = Field(default_factory=AuthZenLikeContextModel)
    options: AuthZenLikeOptionsModel = Field(default_factory=AuthZenLikeOptionsModel)

    model_config = {"extra": "allow"}


class PatchPolicyParametersModel(BaseModel):
    parameters: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class PatchIdentityPresenceModel(BaseModel):
    presence: Dict[str, bool] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


def build_config(config_path: Optional[str]) -> Dict[str, Any]:
    # Build runtime config from defaults, optional JSON override, and environment variables
    # side effect: reads env and file.
    config = dict(DEFAULT_CONFIG)

    if config_path:
        config = merge_config(config, load_json_object(config_path))

    config["log_level"] = os.environ.get("LOG_LEVEL", str(config.get("log_level", "info")))

    config["workflow_base_url"] = os.environ.get("WORKFLOW_BASE_URL", str(config["workflow_base_url"]))
    config["***REMOVED***_dir_base"] = os.environ.get("***REMOVED***_DIR_BASE", str(config["***REMOVED***_dir_base"]))
    config["***REMOVED***_check_path"] = os.environ.get("***REMOVED***_CHECK_PATH", str(config["***REMOVED***_check_path"]))

    config["***REMOVED***_timeout_connect_seconds"] = parse_positive_float(
        os.environ.get("***REMOVED***_TIMEOUT_CONNECT_SECONDS", str(config["***REMOVED***_timeout_connect_seconds"])),
        "***REMOVED***_TIMEOUT_CONNECT_SECONDS",
    )
    config["***REMOVED***_timeout_read_seconds"] = parse_positive_float(
        os.environ.get("***REMOVED***_TIMEOUT_READ_SECONDS", str(config["***REMOVED***_timeout_read_seconds"])),
        "***REMOVED***_TIMEOUT_READ_SECONDS",
    )

    config["request_timeout_seconds"] = parse_positive_int(
        os.environ.get("REQUEST_TIMEOUT_SECONDS", str(config["request_timeout_seconds"])),
        "REQUEST_TIMEOUT_SECONDS",
    )

    validate_non_empty_string(str(config.get("workflow_base_url", "")), "workflow_base_url")
    validate_non_empty_string(str(config.get("***REMOVED***_dir_base", "")), "***REMOVED***_dir_base")
    validate_non_empty_string(str(config.get("***REMOVED***_check_path", "")), "***REMOVED***_check_path")

    return config


def handle_get_health(request: Request) -> Dict[str, Any]:
    # Return health and basic service stats
    # why: smoke tests and operational debugging
    # side effect: none.
    service: AuthzService = request.app.state.service
    return {
        "status": "ok",
        "service": str(request.app.state.config.get("service_name", "authz-api")),
        "profiles_in_memory": int(service.get_profile_count()),
    }


def handle_post_evaluate(request: Request, body: EvaluateRequestModel) -> EvaluateResponseModel:
    # Evaluate authorization request
    # why: central PDP adapter around ***REMOVED*** + progressive profiling
    # side effect: network I/O.
    service: AuthzService = request.app.state.service
    try:
        response = service.evaluate_request(request_model=body)
        return EvaluateResponseModel(**response)
    except ValueError as exception:
        raise HTTPException(status_code=400, detail=str(exception)) from exception
    except PermissionError as exception:
        raise HTTPException(status_code=403, detail=str(exception)) from exception


def handle_get_policy_parameters(request: Request, principal_sub: str) -> Dict[str, Any]:
    # Return non-PII policy parameters (preferences) for a principal
    # why: build policy context without PII.
    service: AuthzService = request.app.state.service
    try:
        principal_sub = validate_non_empty_string(principal_sub, "principal_sub")
        return {"principal_sub": principal_sub, "parameters": service.get_policy_parameters(principal_sub)}
    except ValueError as exception:
        raise HTTPException(status_code=400, detail=str(exception)) from exception


def handle_patch_policy_parameters(request: Request, principal_sub: str, body: PatchPolicyParametersModel) -> Dict[str, Any]:
    # Patch non-PII policy parameters (preferences)
    # why: desktop app can enrich preferences over time
    # side effect: in-memory mutation.
    service: AuthzService = request.app.state.service
    try:
        principal_sub = validate_non_empty_string(principal_sub, "principal_sub")
        updated = service.patch_policy_parameters(principal_sub=principal_sub, patch=body.parameters)
        return {"principal_sub": principal_sub, "parameters": updated}
    except ValueError as exception:
        raise HTTPException(status_code=400, detail=str(exception)) from exception


def handle_get_identity_presence(request: Request, principal_sub: str) -> Dict[str, Any]:
    # Return identity-presence flags (no values)
    # why: support progressive profiling without leaking PII values.
    service: AuthzService = request.app.state.service
    try:
        principal_sub = validate_non_empty_string(principal_sub, "principal_sub")
        return {"principal_sub": principal_sub, "presence": service.get_identity_presence(principal_sub)}
    except ValueError as exception:
        raise HTTPException(status_code=400, detail=str(exception)) from exception


def handle_patch_identity_presence(request: Request, principal_sub: str, body: PatchIdentityPresenceModel) -> Dict[str, Any]:
    # Patch identity-presence flags
    # why: demo enrichment workflow driven by UI or back-office
    # side effect: in-memory mutation.
    service: AuthzService = request.app.state.service
    try:
        principal_sub = validate_non_empty_string(principal_sub, "principal_sub")
        updated = service.patch_identity_presence(principal_sub=principal_sub, patch=body.presence)
        return {"principal_sub": principal_sub, "presence": updated}
    except ValueError as exception:
        raise HTTPException(status_code=400, detail=str(exception)) from exception


def handle_get_profile(request: Request, principal_sub: str) -> Dict[str, Any]:
    # Return combined profile view (preferences + presence)
    # why: convenient for demo clients
    # side effect: none.
    service: AuthzService = request.app.state.service
    try:
        principal_sub = validate_non_empty_string(principal_sub, "principal_sub")
        return service.get_profile(principal_sub=principal_sub)
    except ValueError as exception:
        raise HTTPException(status_code=400, detail=str(exception)) from exception


def create_app(config: Dict[str, Any]) -> FastAPI:
    # Create FastAPI app and wire routes
    # why: keep web layer thin and delegate to core service
    # side effect: allocates in-memory stores.
    api = FastAPI(
        title="AuthZ API",
        version="1.0.0",
        # Limit request body size to 1MB (protects against large payload attacks)
        swagger_ui_parameters={"defaultModelsExpandDepth": -1},
    )
    api.state.config = config
    api.state.service = AuthzService(config=config)
    
    # Add request size limiting middleware
    api.add_middleware(RequestSizeLimiterMiddleware, max_size=get_max_request_size())

    # Health check - no auth required
    api.add_api_route("/health", handle_get_health, methods=["GET"])

    # All other endpoints require authentication
    api.add_api_route("/v1/evaluate", handle_post_evaluate, methods=["POST"], dependencies=[Depends(bearer_scheme)])

    api.add_api_route("/v1/profiles/{principal_sub}", handle_get_profile, methods=["GET"], dependencies=[Depends(bearer_scheme)])
    api.add_api_route("/v1/profiles/{principal_sub}/policy-parameters", handle_get_policy_parameters, methods=["GET"], dependencies=[Depends(bearer_scheme)])
    api.add_api_route("/v1/profiles/{principal_sub}/policy-parameters", handle_patch_policy_parameters, methods=["PATCH"], dependencies=[Depends(bearer_scheme)])
    api.add_api_route("/v1/profiles/{principal_sub}/identity-presence", handle_get_identity_presence, methods=["GET"], dependencies=[Depends(bearer_scheme)])
    api.add_api_route("/v1/profiles/{principal_sub}/identity-presence", handle_patch_identity_presence, methods=["PATCH"], dependencies=[Depends(bearer_scheme)])

    return api


def parse_args() -> argparse.Namespace:
    # Parse CLI args for container entrypoint
    # why: keep configuration explicit and reproducible.
    parser = argparse.ArgumentParser(description="AuthZ API service (***REMOVED***-backed)")
    parser.add_argument("--config", dest="config_path", default=None, help="Path to JSON config file.")
    parser.add_argument("--host", dest="host", default="0.0.0.0", help="Bind host.")
    parser.add_argument("--port", dest="port", type=int, default=8002, help="Bind port.")
    parser.add_argument("--reload", dest="reload", action="store_true", help="Enable auto-reload (local dev).")
    return parser.parse_args()


def main() -> int:
    # Start the AuthZ API server
    # side effect: runs a web server and blocks
    # returns non-zero on config errors.
    args = parse_args()
    try:
        config = build_config(config_path=args.config_path)
    except ValueError as exception:
        print(f"[authz-api] Configuration error: {exception}")
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
