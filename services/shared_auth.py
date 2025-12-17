"""
Shared authentication utilities for FlowPilot services.

Provides bearer token validation using Keycloak introspection.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests
from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


class BearerTokenValidator:
    """Validates bearer tokens using Keycloak token introspection."""

    def __init__(
        self,
        keycloak_url: str,
        realm: str,
        client_id: str,
        client_secret: str,
        enabled: bool = True,
    ):
        """
        Initialize the bearer token validator.

        Args:
            keycloak_url: Base URL of Keycloak (e.g., https://localhost:8443)
            realm: Keycloak realm name
            client_id: Client ID for introspection
            client_secret: Client secret for introspection
            enabled: Whether to enforce authentication (False for dev/demo)
        """
        self.enabled = enabled
        if not self.enabled:
            return

        self.introspection_url = f"{keycloak_url}/realms/{realm}/protocol/openid-connect/token/introspect"
        self.client_id = client_id
        self.client_secret = client_secret
        self.verify_ssl = os.environ.get("KEYCLOAK_VERIFY_SSL", "false").lower() == "true"

    def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate a bearer token using Keycloak introspection.

        Args:
            token: The bearer token to validate

        Returns:
            Token introspection response with user info

        Raises:
            HTTPException: If token is invalid or introspection fails
        """
        if not self.enabled:
            # For demo/dev mode, return a mock response
            return {"active": True, "sub": "demo_user", "client_id": "demo"}

        try:
            response = requests.post(
                self.introspection_url,
                data={
                    "token": token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=5,
                verify=self.verify_ssl,
            )
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Token validation service unavailable",
            ) from exc

        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token validation failed",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token_info = response.json()

        if not token_info.get("active", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return token_info


class BearerAuthMiddleware:
    """FastAPI dependency for bearer token authentication."""

    def __init__(self, validator: BearerTokenValidator, require_auth: bool = True):
        """
        Initialize the auth middleware.

        Args:
            validator: Token validator instance
            require_auth: Whether to require authentication (set to False for health endpoints)
        """
        self.validator = validator
        self.require_auth = require_auth
        self.bearer_scheme = HTTPBearer(auto_error=require_auth)

    async def __call__(
        self, request: Request, credentials: Optional[HTTPAuthorizationCredentials] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Validate bearer token from request.

        Args:
            request: FastAPI request
            credentials: HTTP bearer credentials

        Returns:
            Token info if valid, None if auth not required

        Raises:
            HTTPException: If authentication fails
        """
        # Skip auth for health check
        if request.url.path in ["/health", "/docs", "/openapi.json", "/redoc"]:
            return None

        if not self.require_auth:
            return None

        if credentials is None:
            credentials = await self.bearer_scheme(request)

        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return self.validator.validate_token(credentials.credentials)


def create_auth_validator_from_env() -> BearerTokenValidator:
    """
    Create a bearer token validator from environment variables.

    Environment variables:
        AUTH_ENABLED: Set to "true" to enable authentication (default: false for demo)
        KEYCLOAK_URL: Keycloak base URL (default: https://localhost:8443)
        KEYCLOAK_REALM: Keycloak realm (default: flowpilot)
        KEYCLOAK_CLIENT_ID: Client ID for introspection (default: flowpilot-agent)
        KEYCLOAK_CLIENT_SECRET: Client secret for introspection

    Returns:
        Configured bearer token validator
    """
    enabled = os.environ.get("AUTH_ENABLED", "false").lower() == "true"
    keycloak_url = os.environ.get("KEYCLOAK_URL", "https://localhost:8443")
    realm = os.environ.get("KEYCLOAK_REALM", "flowpilot")
    client_id = os.environ.get("KEYCLOAK_CLIENT_ID", "flowpilot-agent")
    client_secret = os.environ.get("KEYCLOAK_CLIENT_SECRET", "DbUpdfiTCgA1GnYlgPduhQDv84R3t65q")

    return BearerTokenValidator(
        keycloak_url=keycloak_url,
        realm=realm,
        client_id=client_id,
        client_secret=client_secret,
        enabled=enabled,
    )
