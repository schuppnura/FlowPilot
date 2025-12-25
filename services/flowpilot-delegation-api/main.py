# FlowPilot Delegation API - FastAPI Application
#
# Service for managing delegation relationships in a graph database.
# Maintains delegation chains for authorization checks.

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, Optional

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

import security
import api_logging
from core import DelegationService
import core
from graphdb import DelegationGraphDB
from utils import load_json_object, merge_config, parse_positive_int, validate_non_empty_string

# Environment flag for detailed error messages (disable in production)
INCLUDE_ERROR_DETAILS = os.environ.get("INCLUDE_ERROR_DETAILS", "1") == "1"


DEFAULT_CONFIG: Dict[str, Any] = {
    "service_name": "flowpilot-delegation-api",
    "log_level": "info",
    "db_path": "./delegations.db",  # SQLite database file path
    "request_timeout_seconds": 10,
    "keycloak_base_url": "https://keycloak:8443",
    "keycloak_realm": "flowpilot",
    "keycloak_admin_username": "admin",
    "keycloak_admin_password": "",  # Must be set via environment variable
}


class CreateDelegationRequest(BaseModel):
    principal_id: str = Field(..., min_length=1, max_length=255, description="Principal ID (delegating authority)")
    delegate_id: str = Field(..., min_length=1, max_length=255, description="Delegate ID (receiving authority)")
    workflow_id: Optional[str] = Field(None, max_length=255, description="Optional workflow ID to scope delegation")
    expires_in_days: int = Field(default=7, ge=1, le=365, description="Days until expiration (default: 7)")
    
    @validator('principal_id')
    def sanitize_principal_id(cls, v: str) -> str:
        return security.sanitize_string(v, max_length=255)
    
    @validator('delegate_id')
    def sanitize_delegate_id(cls, v: str) -> str:
        return security.sanitize_string(v, max_length=255)
    
    @validator('workflow_id')
    def sanitize_workflow_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return security.sanitize_string(v, max_length=255)


class RevokeDelegationRequest(BaseModel):
    principal_id: str = Field(..., min_length=1, max_length=255, description="Principal ID")
    delegate_id: str = Field(..., min_length=1, max_length=255, description="Delegate ID")
    workflow_id: Optional[str] = Field(None, max_length=255, description="Optional workflow ID to scope revocation")
    
    @validator('principal_id')
    def sanitize_principal_id(cls, v: str) -> str:
        return security.sanitize_string(v, max_length=255)
    
    @validator('delegate_id')
    def sanitize_delegate_id(cls, v: str) -> str:
        return security.sanitize_string(v, max_length=255)
    
    @validator('workflow_id')
    def sanitize_workflow_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return security.sanitize_string(v, max_length=255)


def build_config(config_path: Optional[str]) -> Dict[str, Any]:
    """Build runtime config from defaults, optional JSON override, and environment variables."""
    config = dict(DEFAULT_CONFIG)
    
    if config_path:
        config = merge_config(config, load_json_object(config_path))
    
    config["log_level"] = os.environ.get("LOG_LEVEL", str(config["log_level"]))
    config["db_path"] = os.environ.get("DB_PATH", str(config["db_path"]))
    config["request_timeout_seconds"] = parse_positive_int(
        os.environ.get("REQUEST_TIMEOUT_SECONDS", str(config["request_timeout_seconds"])),
        "REQUEST_TIMEOUT_SECONDS",
    )
    
    # Keycloak configuration
    config["keycloak_base_url"] = os.environ.get("KEYCLOAK_BASE_URL", str(config["keycloak_base_url"]))
    config["keycloak_realm"] = os.environ.get("KEYCLOAK_REALM", str(config["keycloak_realm"]))
    config["keycloak_admin_username"] = os.environ.get("KEYCLOAK_ADMIN_USERNAME", str(config["keycloak_admin_username"]))
    config["keycloak_admin_password"] = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", str(config["keycloak_admin_password"]))
    config["verify_tls"] = os.environ.get("VERIFY_TLS", "false").lower() == "true"
    
    validate_non_empty_string(str(config.get("db_path", "")), "db_path")
    
    return config


def handle_get_health(request: Request) -> Dict[str, Any]:
    """Return an operational health response."""
    return {
        "status": "ok",
        "service": str(request.app.state.config.get("service_name", "flowpilot-delegation-api")),
    }


def handle_post_delegations(
    request: Request,
    body: CreateDelegationRequest,
    token_claims: dict = Depends(security.verify_token),
) -> Dict[str, Any]:
    """Create a delegation relationship."""
    service: DelegationService = request.app.state.service
    
    try:
        api_logging.log_api_request(
            method="POST",
            path="/v1/delegations",
            request_body=body.dict(),
            token_claims=token_claims,
            request=request,
        )
        
        delegation = service.create_delegation(
            principal_id=body.principal_id,
            delegate_id=body.delegate_id,
            workflow_id=body.workflow_id,
            expires_in_days=body.expires_in_days,
        )
        
        api_logging.log_api_response(
            method="POST",
            path="/v1/delegations",
            status_code=200,
            response_body=delegation,
        )
        
        return delegation
    except ValueError as exception:
        error_detail = security.sanitize_error_message(str(exception), INCLUDE_ERROR_DETAILS)
        api_logging.log_api_response(
            method="POST",
            path="/v1/delegations",
            status_code=400,
            error=error_detail,
        )
        raise HTTPException(status_code=400, detail=error_detail) from exception
    except Exception as exception:
        error_detail = security.sanitize_error_message(str(exception), INCLUDE_ERROR_DETAILS)
        api_logging.log_api_response(
            method="POST",
            path="/v1/delegations",
            status_code=500,
            error=error_detail,
        )
        raise HTTPException(status_code=500, detail=error_detail) from exception


def handle_delete_delegations(
    request: Request,
    body: RevokeDelegationRequest,
    token_claims: dict = Depends(security.verify_token),
) -> Dict[str, Any]:
    """Revoke a delegation relationship."""
    service: DelegationService = request.app.state.service
    
    try:
        api_logging.log_api_request(
            method="DELETE",
            path="/v1/delegations",
            request_body=body.dict(),
            token_claims=token_claims,
            request=request,
        )
        
        result = service.revoke_delegation(
            principal_id=body.principal_id,
            delegate_id=body.delegate_id,
            workflow_id=body.workflow_id,
        )
        
        api_logging.log_api_response(
            method="DELETE",
            path="/v1/delegations",
            status_code=200,
            response_body=result,
        )
        
        return result
    except ValueError as exception:
        error_detail = security.sanitize_error_message(str(exception), INCLUDE_ERROR_DETAILS)
        api_logging.log_api_response(
            method="DELETE",
            path="/v1/delegations",
            status_code=400,
            error=error_detail,
        )
        raise HTTPException(status_code=400, detail=error_detail) from exception
    except Exception as exception:
        error_detail = security.sanitize_error_message(str(exception), INCLUDE_ERROR_DETAILS)
        api_logging.log_api_response(
            method="DELETE",
            path="/v1/delegations",
            status_code=500,
            error=error_detail,
        )
        raise HTTPException(status_code=500, detail=error_detail) from exception


def handle_get_delegations_validate(
    request: Request,
    principal_id: str,
    delegate_id: str,
    workflow_id: Optional[str] = None,
    token_claims: dict = Depends(security.verify_token),
) -> Dict[str, Any]:
    """Validate a delegation relationship."""
    service: DelegationService = request.app.state.service
    
    try:
        api_logging.log_api_request(
            method="GET",
            path="/v1/delegations/validate",
            token_claims=token_claims,
            request=request,
            path_params={"principal_id": principal_id, "delegate_id": delegate_id, "workflow_id": workflow_id},
        )
        
        result = service.validate_delegation(
            principal_id=principal_id,
            delegate_id=delegate_id,
            workflow_id=workflow_id,
        )
        
        api_logging.log_api_response(
            method="GET",
            path="/v1/delegations/validate",
            status_code=200,
            response_body=result,
        )
        
        return result
    except ValueError as exception:
        error_detail = security.sanitize_error_message(str(exception), INCLUDE_ERROR_DETAILS)
        api_logging.log_api_response(
            method="GET",
            path="/v1/delegations/validate",
            status_code=400,
            error=error_detail,
        )
        raise HTTPException(status_code=400, detail=error_detail) from exception
    except Exception as exception:
        error_detail = security.sanitize_error_message(str(exception), INCLUDE_ERROR_DETAILS)
        api_logging.log_api_response(
            method="GET",
            path="/v1/delegations/validate",
            status_code=500,
            error=error_detail,
        )
        raise HTTPException(status_code=500, detail=error_detail) from exception


def handle_get_delegations(
    request: Request,
    principal_id: Optional[str] = None,
    delegate_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    include_expired: bool = False,
    token_claims: dict = Depends(security.verify_token),
) -> Dict[str, Any]:
    """List delegations."""
    service: DelegationService = request.app.state.service
    
    try:
        api_logging.log_api_request(
            method="GET",
            path="/v1/delegations",
            token_claims=token_claims,
            request=request,
        )
        
        delegations = service.list_delegations(
            principal_id=principal_id,
            delegate_id=delegate_id,
            workflow_id=workflow_id,
            include_expired=include_expired,
        )
        
        result = {"delegations": delegations}
        api_logging.log_api_response(
            method="GET",
            path="/v1/delegations",
            status_code=200,
            response_body=result,
        )
        
        return result
    except ValueError as exception:
        error_detail = security.sanitize_error_message(str(exception), INCLUDE_ERROR_DETAILS)
        api_logging.log_api_response(
            method="GET",
            path="/v1/delegations",
            status_code=400,
            error=error_detail,
        )
        raise HTTPException(status_code=400, detail=error_detail) from exception
    except Exception as exception:
        error_detail = security.sanitize_error_message(str(exception), INCLUDE_ERROR_DETAILS)
        api_logging.log_api_response(
            method="GET",
            path="/v1/delegations",
            status_code=500,
            error=error_detail,
        )
        raise HTTPException(status_code=500, detail=error_detail) from exception


def handle_get_users_by_persona(
    request: Request,
    persona: str = Query(..., description="Persona to filter users by (e.g., 'travel-agent')"),
    token_claims: dict = Depends(security.verify_token),
) -> Dict[str, Any]:
    """List users who have a specific persona."""
    config: Dict[str, Any] = request.app.state.config
    
    try:
        api_logging.log_api_request(
            method="GET",
            path="/v1/users",
            token_claims=token_claims,
            request=request,
            path_params={"persona": persona},
        )
        
        keycloak_base_url = str(config.get("keycloak_base_url", ""))
        keycloak_realm = str(config.get("keycloak_realm", ""))
        keycloak_admin_username = str(config.get("keycloak_admin_username", ""))
        keycloak_admin_password = str(config.get("keycloak_admin_password", ""))
        verify_tls = bool(config.get("verify_tls", False))
        
        if not keycloak_base_url or not keycloak_realm or not keycloak_admin_username or not keycloak_admin_password:
            raise ValueError("Keycloak configuration is incomplete")
        
        users = core.DelegationService.list_users_by_persona(
            keycloak_base_url=keycloak_base_url,
            keycloak_realm=keycloak_realm,
            keycloak_admin_username=keycloak_admin_username,
            keycloak_admin_password=keycloak_admin_password,
            persona=persona,
            verify_tls=verify_tls,
        )
        
        result = {"users": users}
        api_logging.log_api_response(
            method="GET",
            path="/v1/users",
            status_code=200,
            response_body=result,
        )
        
        return result
    except ValueError as exception:
        error_detail = security.sanitize_error_message(str(exception), INCLUDE_ERROR_DETAILS)
        api_logging.log_api_response(
            method="GET",
            path="/v1/users",
            status_code=400,
            error=error_detail,
        )
        raise HTTPException(status_code=400, detail=error_detail) from exception
    except Exception as exception:
        error_detail = security.sanitize_error_message(str(exception), INCLUDE_ERROR_DETAILS)
        api_logging.log_api_response(
            method="GET",
            path="/v1/users",
            status_code=500,
            error=error_detail,
        )
        raise HTTPException(status_code=500, detail=error_detail) from exception


def create_app(config: Dict[str, Any]) -> FastAPI:
    """Create FastAPI API endpoints and wire routes."""
    api = FastAPI(
        title="FlowPilot Delegation API",
        version="1.0.0",
        swagger_ui_parameters={"defaultModelsExpandDepth": -1},
    )
    api.state.config = config
    
    # Initialize graph database
    db_path = str(config.get("db_path", "./delegations.db"))
    graphdb = DelegationGraphDB(db_path=db_path)
    service = DelegationService(graphdb=graphdb)
    api.state.service = service
    
    # Add exception handler
    @api.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if exc.status_code == 401:
            auth_header = request.headers.get("authorization", "")
            token_preview = auth_header[:50] + "..." if len(auth_header) > 50 else auth_header
            print(f"[HTTPException 401] Path: {request.url.path}, Detail: {exc.detail}, Auth header: {token_preview}", flush=True)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
    
    # Add security middlewares
    api.add_middleware(security.SecurityHeadersMiddleware)
    api.add_middleware(security.RequestSizeLimiterMiddleware, max_size=security.get_max_request_size())
    
    # Health check - no auth required
    api.add_api_route("/health", handle_get_health, methods=["GET"])
    
    # All other endpoints require authentication
    api.add_api_route("/v1/delegations", handle_post_delegations, methods=["POST"], dependencies=[Depends(security.verify_token)])
    api.add_api_route("/v1/delegations", handle_delete_delegations, methods=["DELETE"], dependencies=[Depends(security.verify_token)])
    api.add_api_route("/v1/delegations", handle_get_delegations, methods=["GET"], dependencies=[Depends(security.verify_token)])
    api.add_api_route("/v1/delegations/validate", handle_get_delegations_validate, methods=["GET"], dependencies=[Depends(security.verify_token)])
    api.add_api_route("/v1/users", handle_get_users_by_persona, methods=["GET"], dependencies=[Depends(security.verify_token)])
    
    return api


def parse_args() -> argparse.Namespace:
    """Parse CLI args for container entrypoints."""
    parser = argparse.ArgumentParser(description="FlowPilot Delegation API service")
    parser.add_argument("--config", dest="config_path", default=None, help="Path to JSON config file.")
    parser.add_argument("--host", dest="host", default="0.0.0.0", help="Bind host.")
    parser.add_argument("--port", dest="port", type=int, default=8005, help="Bind port.")
    parser.add_argument("--reload", dest="reload", action="store_true", help="Enable auto-reload (local dev).")
    return parser.parse_args()


def main() -> int:
    """Build config and start Uvicorn."""
    args = parse_args()
    try:
        config = build_config(config_path=args.config_path)
    except ValueError as exception:
        print(f"[flowpilot-delegation-api] Configuration error: {exception}")
        return 2
    
    api = create_app(config=config)
    uvicorn.run(
        api,
        host=str(args.host),
        port=int(args.port),
        reload=bool(args.reload),
        log_level=str(config.get("log_level", "info")),
        limit_max_requests=10000,
        limit_concurrency=100,
        timeout_keep_alive=5,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

