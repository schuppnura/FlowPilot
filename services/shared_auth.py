"""
Shared authentication utilities for FlowPilot services.

Provides bearer token validation using Keycloak introspection.
"""

from __future__ import annotations

import os
from typing import Any, Dict

import requests
from fastapi import HTTPException, status
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


# Global bearer scheme for FastAPI
bearer_scheme = HTTPBearer(auto_error=True)

# Global validator instance
_validator_instance = None

def get_validator():
    """Get the global validator instance."""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = create_auth_validator_from_env()
    return _validator_instance

def verify_token(credentials: HTTPAuthorizationCredentials) -> Dict[str, Any]:
    """Verify bearer token - use as FastAPI dependency."""
    validator = get_validator()
    return validator.validate_token(credentials.credentials)


def create_auth_validator_from_env() -> BearerTokenValidator:
    """
    Create a bearer token validator from environment variables.

    Environment variables:
        AUTH_ENABLED: Set to "false" to disable authentication (default: true for security)
        KEYCLOAK_URL: Keycloak base URL (default: https://localhost:8443)
        KEYCLOAK_REALM: Keycloak realm (default: flowpilot)
        KEYCLOAK_CLIENT_ID: Client ID for introspection (default: flowpilot-agent)
        KEYCLOAK_CLIENT_SECRET: Client secret for introspection

    Returns:
        Configured bearer token validator
    """
    enabled = os.environ.get("AUTH_ENABLED", "true").lower() == "true"
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
