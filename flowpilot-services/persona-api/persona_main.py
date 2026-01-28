# FlowPilot User Profile API (flowpilot-user-profile-api)
#
# This service provides an abstraction layer over Firebase/Firestore for user
# profile management. It allows clients to manage user personas and preferences
# without directly interacting with Firebase.
#
# Responsibilities:
# - Get user profile (authenticated user's own profile)
# - Update user profile (personas, autobook preferences)
# - List users by persona (for delegation candidate discovery)
#
# Design Goals:
# - Clean abstraction over Firebase (clients use REST, not Firebase SDK)
# - All business logic in user_profile_core.py (main.py only has FastAPI wiring)
# - Reuse shared libraries (DRY principle)
# - Defense-in-depth security (JWT validation, input sanitization)
#
# Security Model:
# - All endpoints require JWT bearer authentication
# - Users can only access/modify their own profile (based on token sub claim)
# - Only sub (UUID) and persona are processed; no PII exposure

from __future__ import annotations

import argparse
import os
from typing import Any, List, Optional

import profile  # Resolved at build time: profile_firebase.py or profile_keycloak.py
import security  # Resolved at build time: security_firebase.py or security_keycloak.py
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from persona_core import PersonaService
from personadb import PersonaDB  # Resolved at build time: personadb_firestore.py or personadb_sqlite.py
from pydantic import BaseModel, Field, validator

# ============================================================================
# Configuration Constants
# ============================================================================

# Environment flag for detailed error messages (disable in production)
INCLUDE_ERROR_DETAILS = os.environ.get("INCLUDE_ERROR_DETAILS", "1") == "1"

# ============================================================================
# Pydantic Models (Request/Response)
# ============================================================================



class UserInfo(BaseModel):
    """Basic user information from IdP."""
    id: str  # User sub/uid
    username: str  # Display name or email or uid
    email: str | None = None  # Optional email


class ListUsersResponse(BaseModel):
    """Response for GET /v1/users."""
    users: list[UserInfo]


class UserInfoWithPersona(BaseModel):
    """User info with persona context (for /v1/users/by-persona)."""
    sub: str
    email: str | None
    persona: str


class ListUsersByPersonaResponse(BaseModel):
    """Response for GET /v1/users/by-persona."""
    users: list[UserInfoWithPersona]


class PersonaResponse(BaseModel):
    """Response for persona operations."""
    persona_id: str
    user_sub: str
    title: str
    scope: list[str]
    valid_from: str
    valid_till: str
    status: str
    created_at: str
    updated_at: str
    consent: bool
    autobook_price: int
    autobook_leadtime: int
    autobook_risklevel: int


class CreatePersonaRequest(BaseModel):
    """Request body for creating a persona.
    
    Accepts dynamic policy-specific attributes.
    Standard attributes are defined below; additional attributes are accepted via model_config.
    """
    model_config = {"extra": "allow"}  # Allow additional fields
    
    title: str = Field(..., min_length=1, max_length=50, description="Persona title")
    scope: list[str] | None = Field(None, description="List of actions (can be empty)")
    valid_from: str | None = Field(None, description="When persona becomes active (ISO 8601)")
    valid_till: str | None = Field(None, description="When persona expires (ISO 8601)")
    status: str | None = Field(None, description="Status (active, inactive, suspended, expired)")


class UpdatePersonaRequest(BaseModel):
    """Request body for updating a persona.
    
    Accepts dynamic policy-specific attributes for partial updates.
    """
    model_config = {"extra": "allow"}  # Allow additional fields
    
    title: str | None = Field(None, min_length=1, max_length=50, description="Persona title")
    scope: list[str] | None = Field(None, description="List of actions")
    valid_from: str | None = Field(None, description="When persona becomes active (ISO 8601)")
    valid_till: str | None = Field(None, description="When persona expires (ISO 8601)")
    status: str | None = Field(None, description="Status (active, inactive, suspended, expired)")


class ListPersonasResponse(BaseModel):
    """Response for listing personas."""
    personas: list[PersonaResponse]


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="FlowPilot User Profile API",
    version="1.0.0",
    description="User profile management abstraction over Firebase/Firestore"
)

# Add CORS middleware
cors_config = security.get_cors_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_config["allow_origins"],
    allow_credentials=cors_config["allow_credentials"],
    allow_methods=cors_config["allow_methods"],
    allow_headers=cors_config["allow_headers"],
)

# Add security middlewares
app.add_middleware(security.SecurityHeadersMiddleware)
app.add_middleware(
    security.RequestSizeLimiterMiddleware, max_size=security.get_max_request_size()
)

# Initialize persona database and service
_persona_db = PersonaDB()
_persona_service = PersonaService(_persona_db)


# Custom exception handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code in (401, 403):
        auth_header = request.headers.get("authorization", "")
        auth_preview = (
            auth_header[:50] + "..." if len(auth_header) > 50 else auth_header or "None"
        )
        print(
            f"[user-profile-api HTTPException {exc.status_code}] Path: {request.url.path}, Detail: {exc.detail}, Auth: {auth_preview}",
            flush=True,
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc.detail) if hasattr(exc, "detail") else str(exc)},
    )


def is_service_account_token(token_claims: dict[str, Any]) -> bool:
    """Check if token is from a service account.
    
    Service accounts are identified by:
    - client_id/azp = "flowpilot-agent" (Keycloak service account)
    - email contains "gserviceaccount.com" (GCP service account)
    """
    client_id = token_claims.get("azp") or token_claims.get("client_id")
    email = token_claims.get("email", "")
    return client_id == "flowpilot-agent" or "gserviceaccount.com" in email


def extract_persona_attributes(
    sanitized_body: dict[str, Any],
    user_sub: str | None = None,
    persona_id: str | None = None,
) -> dict[str, Any]:
    """Extract standard and custom persona attributes from request body.
    
    Separates standard attributes (title, scope, etc.) from policy-specific
    custom attributes and builds kwargs dict for service calls.
    
    Args:
        sanitized_body: Sanitized request body
        user_sub: Optional user subject ID to include in kwargs
        persona_id: Optional persona ID to include in kwargs
    
    Returns:
        Dictionary with all attributes ready for service call
    """
    standard_attrs = {"title", "scope", "valid_from", "valid_till", "status"}
    
    # Build kwargs with optional identifiers
    kwargs: dict[str, Any] = {}
    if user_sub:
        kwargs["user_sub"] = user_sub
    if persona_id:
        kwargs["persona_id"] = persona_id
    
    # Extract standard attributes
    for attr in standard_attrs:
        if attr in sanitized_body:
            kwargs[attr] = sanitized_body[attr]
    
    # Extract all custom attributes (anything not in standard_attrs)
    for key, value in sanitized_body.items():
        if key not in standard_attrs:
            kwargs[key] = value
    
    return kwargs


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/health")
def get_health() -> dict[str, str]:
    """Health check endpoint (no authentication required)."""
    return {"status": "ok", "service": "flowpilot-user-profile-api"}


@app.get("/v1/users", response_model=ListUsersResponse)
def get_all_users(
    request: Request,
    token_claims: dict[str, Any] = Depends(security.verify_token),
) -> dict[str, Any]:
    """
    List all users from the identity provider (Firebase Auth).
    
    Returns all users regardless of personas.
    """
    try:
        # Get all users from IdP (returns {id, username, email})
        users_list = profile.list_all_users()
        
        # Return as-is (matches UserInfo model: id, username, email)
        return {"users": users_list}

    except Exception as exc:
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        raise HTTPException(status_code=500, detail=error_detail) from exc


@app.get("/v1/users/by-persona", response_model=ListUsersByPersonaResponse)
def get_users_by_persona(
    request: Request,
    title: str = Query(..., description="Persona title to filter by"),
    token_claims: dict[str, Any] = Depends(security.verify_token),
) -> dict[str, Any]:
    """
    List users who have a specific persona title.
    
    Delegates to profile.list_users_by_persona() for DRY principle.
    """
    try:
        # Sanitize title input
        sanitized_title = security.sanitize_string(title, 50)
        
        # Get users from profile module
        users_list = profile.list_users_by_persona(sanitized_title)
        
        # Convert to expected format (profile returns id/username/email, we need sub/email/persona)
        users = [
            {
                "sub": user["id"],
                "email": user.get("email"),
                "persona": sanitized_title,
            }
            for user in users_list
        ]
        
        return {"users": users}

    except Exception as exc:
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        raise HTTPException(status_code=500, detail=error_detail) from exc


# ============================================================================
# Persona Management Endpoints
# ============================================================================

@app.post("/v1/personas", response_model=PersonaResponse, status_code=201)
def create_persona(
    request: Request,
    body: CreatePersonaRequest,
    token_claims: dict[str, Any] = Depends(security.verify_token),
) -> dict[str, Any]:
    """
    Create a new persona for the authenticated user.
    """
    user_sub = token_claims.get("sub")
    if not user_sub:
        raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")

    try:
        # Sanitize input
        sanitized_body = security.sanitize_request_json_payload(body.dict(exclude_none=True))

        # Extract all attributes (standard + custom) using helper
        create_kwargs = extract_persona_attributes(sanitized_body, user_sub=user_sub)
        
        # Create persona using service with dynamic attributes
        persona = _persona_service.create_persona(**create_kwargs)
        return persona

    except security.InputValidationError as exc:
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        raise HTTPException(status_code=400, detail=error_detail) from exc
    except ValueError as exc:
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        raise HTTPException(status_code=400, detail=error_detail) from exc
    except Exception as exc:
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        raise HTTPException(status_code=500, detail=error_detail) from exc


@app.get("/v1/personas/{persona_id}", response_model=PersonaResponse)
def get_persona(
    request: Request,
    persona_id: str,
    token_claims: dict[str, Any] = Depends(security.verify_token),
) -> dict[str, Any]:
    """
    Get a persona by ID.
    
    The persona must belong to the authenticated user (unless called by a service account).
    """
    user_sub = token_claims.get("sub")
    if not user_sub:
        raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")

    # Sanitize persona_id
    sanitized_persona_id = security.sanitize_string(persona_id, 255)

    try:
        # Check if this is a service account request
        if is_service_account_token(token_claims):
            # Service account - no ownership check
            persona = _persona_service.get_persona_by_id_no_auth(sanitized_persona_id)
            if not persona:
                raise ValueError(f"Persona {sanitized_persona_id} not found")
        else:
            # Regular user - verify ownership
            persona = _persona_service.get_persona(sanitized_persona_id, user_sub)

        return persona

    except ValueError as exc:
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        raise HTTPException(status_code=404, detail=error_detail) from exc
    except Exception as exc:
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        raise HTTPException(status_code=500, detail=error_detail) from exc


@app.get("/v1/personas", response_model=ListPersonasResponse)
def list_personas(
    request: Request,
    status: str | None = Query(None, description="Filter by status"),
    token_claims: dict[str, Any] = Depends(security.verify_token),
) -> dict[str, Any]:
    """
    List all personas for the authenticated user.
    """
    user_sub = token_claims.get("sub")
    if not user_sub:
        raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")

    try:
        # Sanitize status if provided
        sanitized_status = security.sanitize_string(status, 50) if status else None

        # Get personas from service
        personas = _persona_service.list_personas(user_sub, status=sanitized_status)

        return {"personas": personas}

    except Exception as exc:
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        raise HTTPException(status_code=500, detail=error_detail) from exc


@app.get("/v1/users/{user_sub}/personas", response_model=ListPersonasResponse)
def list_personas_for_user(
    request: Request,
    user_sub: str,
    status: str | None = Query(None, description="Filter by status"),
    token_claims: dict[str, Any] = Depends(security.verify_token),
) -> dict[str, Any]:
    """
    List all personas for a specific user (service accounts only).
    """
    # This endpoint is only accessible by service accounts
    if not is_service_account_token(token_claims):
        raise HTTPException(status_code=403, detail="Forbidden: Service account required")

    # Sanitize user_sub
    sanitized_user_sub = security.sanitize_string(user_sub, 255)

    try:
        # Sanitize status if provided
        sanitized_status = security.sanitize_string(status, 50) if status else None

        # Get personas from service
        personas = _persona_service.list_personas(sanitized_user_sub, status=sanitized_status)

        return {"personas": personas}

    except Exception as exc:
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        raise HTTPException(status_code=500, detail=error_detail) from exc


@app.put("/v1/personas/{persona_id}", response_model=PersonaResponse)
def update_persona(
    request: Request,
    persona_id: str,
    body: UpdatePersonaRequest,
    token_claims: dict[str, Any] = Depends(security.verify_token),
) -> dict[str, Any]:
    """
    Update a persona (partial update).
    
    The persona must belong to the authenticated user.
    """
    user_sub = token_claims.get("sub")
    if not user_sub:
        raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")

    # Sanitize persona_id
    sanitized_persona_id = security.sanitize_string(persona_id, 255)

    try:
        # Sanitize input
        sanitized_body = security.sanitize_request_json_payload(body.dict(exclude_none=True))

        # Extract all attributes (standard + custom) using helper
        update_kwargs = extract_persona_attributes(
            sanitized_body,
            user_sub=user_sub,
            persona_id=sanitized_persona_id,
        )
        
        # Update persona using service with dynamic attributes
        persona = _persona_service.update_persona(**update_kwargs)
        return persona

    except security.InputValidationError as exc:
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        raise HTTPException(status_code=400, detail=error_detail) from exc
    except ValueError as exc:
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        raise HTTPException(status_code=400, detail=error_detail) from exc
    except Exception as exc:
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        raise HTTPException(status_code=500, detail=error_detail) from exc


@app.delete("/v1/personas/{persona_id}", status_code=204, response_class=JSONResponse)
def delete_persona(
    request: Request,
    persona_id: str,
    token_claims: dict[str, Any] = Depends(security.verify_token),
):
    """
    Delete a persona.
    
    The persona must belong to the authenticated user.
    """
    user_sub = token_claims.get("sub")
    if not user_sub:
        raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")

    # Sanitize persona_id
    sanitized_persona_id = security.sanitize_string(persona_id, 255)

    try:
        # Delete persona using service
        _persona_service.delete_persona(sanitized_persona_id, user_sub)

        # Return empty JSONResponse with 204 status (no body)
        return JSONResponse(status_code=204)

    except ValueError as exc:
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        raise HTTPException(status_code=404, detail=error_detail) from exc
    except Exception as exc:
        error_detail = security.sanitize_error_message(str(exc), INCLUDE_ERROR_DETAILS)
        raise HTTPException(status_code=500, detail=error_detail) from exc



# ============================================================================
# Application Entry Point
# ============================================================================

def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="FlowPilot User Profile API")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8006, help="Bind port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev)")
    return parser.parse_args()


def main() -> int:
    """Start the Uvicorn server."""
    args = parse_args()

    uvicorn_max_requests = int(os.environ.get("UVICORN_MAX_REQUESTS", "10000"))
    uvicorn_max_concurrency = int(os.environ.get("UVICORN_MAX_CONCURRENCY", "100"))
    uvicorn_keepalive_timeout = int(os.environ.get("UVICORN_KEEPALIVE_TIMEOUT", "5"))

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
        limit_max_requests=uvicorn_max_requests,
        limit_concurrency=uvicorn_max_concurrency,
        timeout_keep_alive=uvicorn_keepalive_timeout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
