# Shared Security Utilities for FlowPilot Services
#
# Comprehensive security module combining authentication and input sanitization
# for FlowPilot services. Provides bearer token validation using Keycloak
# introspection and input validation middleware to protect against various
# security vulnerabilities.
#
# Authentication:
# - Bearer token validation using Keycloak introspection
# - Support for both user tokens and service-to-service authentication
#
# Input Sanitization:
# - Large payload attacks (request body size limits)
# - SQL injection attempts (dangerous pattern detection)
# - XSS (Cross-Site Scripting) attempts
# - Command injection attempts
# - Path traversal attempts
# - Excessive string lengths (per-field character limits)
# - Resource exhaustion (connection limits)

from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict

import requests
from fastapi import HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware


# =============================================================================
# Authentication - Bearer Token Validation
# =============================================================================

class BearerTokenValidator:
    # Validates bearer tokens using Keycloak token introspection.

    def __init__(
        self,
        keycloak_url: str,
        realm: str,
        client_id: str,
        client_secret: str,
        enabled: bool = True,
    ):
        # Initialize the bearer token validator.
        #
        # Args:
        #     keycloak_url: Base URL of Keycloak (e.g., https://localhost:8443)
        #     realm: Keycloak realm name
        #     client_id: Client ID for introspection
        #     client_secret: Client secret for introspection
        #     enabled: Whether to enforce authentication (False for dev/demo)
        self.enabled = enabled
        if not self.enabled:
            return

        self.introspection_url = f"{keycloak_url}/realms/{realm}/protocol/openid-connect/token/introspect"
        self.client_id = client_id
        self.client_secret = client_secret
        self.verify_ssl = os.environ.get("KEYCLOAK_VERIFY_SSL", "false").lower() == "true"

    def validate_token(self, token: str) -> Dict[str, Any]:
        # Validate a bearer token using Keycloak introspection.
        #
        # Args:
        #     token: The bearer token to validate
        #
        # Returns:
        #     Token introspection response with user info
        #
        # Raises:
        #     HTTPException: If token is invalid or introspection fails
        if not self.enabled:
            # For demo/dev mode, return a mock response
            return {"active": True, "sub": "demo_user", "client_id": "demo"}

        if not token or not token.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Empty or missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )

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
        except requests.Timeout as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Token validation timeout: Keycloak at {self.introspection_url} did not respond",
            ) from exc
        except requests.ConnectionError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Token validation connection failed: Cannot reach Keycloak at {self.introspection_url}",
            ) from exc
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Token validation service error: {type(exc).__name__}",
            ) from exc

        if response.status_code != 200:
            # Log the response for debugging but don't expose to client
            error_detail = f"Token validation failed with HTTP {response.status_code}"
            try:
                error_body = response.json()
                if "error" in error_body:
                    error_detail = f"Token validation failed: {error_body.get('error', 'unknown')}"
            except Exception:
                pass
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_detail,
                headers={"WWW-Authenticate": "Bearer"},
            )

        token_info = response.json()

        if not token_info.get("active", False):
            # Token is inactive (expired, revoked, or invalid)
            error_msg = "Invalid or expired token"
            # Provide more context if available
            if "exp" in token_info:
                error_msg = "Token has expired"
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_msg,
                headers={"WWW-Authenticate": "Bearer"},
            )

        return token_info


# Global bearer scheme for FastAPI
bearer_scheme = HTTPBearer(auto_error=True)

# Global validator instance
_validator_instance = None

def get_validator():
    # Get the global validator instance.
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = create_auth_validator_from_env()
    return _validator_instance

def verify_token(credentials: HTTPAuthorizationCredentials) -> Dict[str, Any]:
    # Verify bearer token - use as FastAPI dependency.
    #
    # Args:
    #     credentials: HTTP authorization credentials from bearer_scheme
    #
    # Returns:
    #     Token claims/info from Keycloak introspection
    #
    # Raises:
    #     HTTPException: If token is invalid or validation fails
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    validator = get_validator()
    return validator.validate_token(credentials.credentials)


def create_auth_validator_from_env() -> BearerTokenValidator:
    # Create a bearer token validator from environment variables.
    #
    # Environment variables:
    #     AUTH_ENABLED: Set to "false" to disable authentication (default: true for security)
    #     KEYCLOAK_URL: Keycloak base URL (default: https://localhost:8443)
    #     KEYCLOAK_REALM: Keycloak realm (default: flowpilot)
    #     KEYCLOAK_CLIENT_ID: Client ID for introspection (default: flowpilot-agent)
    #     KEYCLOAK_CLIENT_SECRET: Client secret for introspection (REQUIRED)
    #
    # Returns:
    #     Configured bearer token validator
    enabled = os.environ.get("AUTH_ENABLED", "true").lower() == "true"
    keycloak_url = os.environ.get("KEYCLOAK_URL", "https://localhost:8443")
    realm = os.environ.get("KEYCLOAK_REALM", "flowpilot")
    client_id = os.environ.get("KEYCLOAK_CLIENT_ID", "flowpilot-agent")
    client_secret = os.environ.get("KEYCLOAK_CLIENT_SECRET", "")

    if enabled and not client_secret:
        raise ValueError("KEYCLOAK_CLIENT_SECRET environment variable is required when AUTH_ENABLED=true")

    return BearerTokenValidator(
        keycloak_url=keycloak_url,
        realm=realm,
        client_id=client_id,
        client_secret=client_secret,
        enabled=enabled,
    )


# =============================================================================
# Input Sanitization - Pattern Detection and Validation
# =============================================================================

# SQL injection patterns to detect
SQL_INJECTION_PATTERNS = [
    r"(\bUNION\b.*\bSELECT\b)",  # UNION SELECT
    r"(\bDROP\b.*\bTABLE\b)",     # DROP TABLE
    r"(\bEXEC\b.*\()",             # EXEC(
    r"(\bINSERT\b.*\bINTO\b)",    # INSERT INTO
    r"(\bDELETE\b.*\bFROM\b)",    # DELETE FROM
    r"(\bUPDATE\b.*\bSET\b)",     # UPDATE SET
    r"(--)",                         # SQL comment
    r"(;\s*\w+)",                   # Statement terminator followed by command
    r"(\bOR\b.*=.*)",              # OR 1=1 style
    r"(\bAND\b.*=.*)",             # AND 1=1 style
    r"('.*OR.*'=')",                # String-based OR
]

# XSS (Cross-Site Scripting) patterns
XSS_PATTERNS = [
    r"<script[^>]*>.*?</script>",   # Script tags
    r"javascript:",                  # javascript: protocol
    r"on\w+\s*=",                   # Event handlers (onclick, onerror, etc.)
    r"<iframe[^>]*>",                # iframes
    r"<embed[^>]*>",                 # embed tags
    r"<object[^>]*>",                # object tags
    r"<img[^>]*onerror",             # img with onerror
    r"<svg[^>]*onload",              # svg with onload
    r"expression\s*\(",             # CSS expression
    r"vbscript:",                    # vbscript: protocol
    r"data:text/html",               # data URL with HTML
]

# Command injection patterns
COMMAND_INJECTION_PATTERNS = [
    r"[;&|]\s*\w+",                 # Command chaining (;, &, |)
    r"\$\([^)]+\)",                 # Command substitution $()
    r"`[^`]+`",                      # Backtick command substitution
    r"\|\s*\w+",                    # Pipe to command
    r">\s*[/\w]",                   # Output redirection
    r"<\s*[/\w]",                   # Input redirection
    r"&&\s*\w+",                     # AND command chaining
    r"\|\|\s*\w+",                  # OR command chaining
]

# Path traversal patterns
PATH_TRAVERSAL_PATTERNS = [
    r"\.\./",                        # Parent directory
    r"\..\\",                        # Parent directory (Windows)
    r"%2e%2e/",                      # URL encoded ..
    r"%2e%2e\\",                      # URL encoded .. (Windows)
    r"\.\.%2f",                      # Mixed encoding
    r"\.\.%5c",                      # Mixed encoding (Windows)
]

# Compile patterns for performance
SQL_INJECTION_REGEX = re.compile("|".join(SQL_INJECTION_PATTERNS), re.IGNORECASE)
XSS_REGEX = re.compile("|".join(XSS_PATTERNS), re.IGNORECASE)
COMMAND_INJECTION_REGEX = re.compile("|".join(COMMAND_INJECTION_PATTERNS))
PATH_TRAVERSAL_REGEX = re.compile("|".join(PATH_TRAVERSAL_PATTERNS), re.IGNORECASE)

# Maximum string field length (characters)
MAX_STRING_LENGTH = 10000


class RequestSizeLimiterMiddleware(BaseHTTPMiddleware):
    # Middleware to limit request body size.
    #
    # Protects against resource exhaustion attacks via large payloads.

    def __init__(self, app, max_size: int = 1_048_576):  # 1 MB default
        # Initialize the request size limiter.
        #
        # Args:
        #     app: FastAPI application
        #     max_size: Maximum request body size in bytes (default: 1MB)
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check request size before processing.
        # Get content length from headers
        content_length = request.headers.get("content-length")

        if content_length:
            content_length = int(content_length)
            if content_length > self.max_size:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={
                        "detail": f"Request body too large. Maximum size: {self.max_size} bytes",
                        "max_size_bytes": self.max_size,
                        "max_size_mb": round(self.max_size / 1_048_576, 2),
                    },
                )

        response = await call_next(request)
        return response


def detect_sql_injection(value: str) -> bool:
    # Detect potential SQL injection attempts.
    #
    # Args:
    #     value: String to check for SQL injection patterns
    #
    # Returns:
    #     True if suspicious patterns detected, False otherwise
    if not isinstance(value, str):
        return False
    return bool(SQL_INJECTION_REGEX.search(value))


def detect_xss(value: str) -> bool:
    # Detect potential XSS (Cross-Site Scripting) attempts.
    #
    # Args:
    #     value: String to check for XSS patterns
    #
    # Returns:
    #     True if suspicious patterns detected, False otherwise
    if not isinstance(value, str):
        return False
    return bool(XSS_REGEX.search(value))


def detect_command_injection(value: str) -> bool:
    # Detect potential command injection attempts.
    #
    # Args:
    #     value: String to check for command injection patterns
    #
    # Returns:
    #     True if suspicious patterns detected, False otherwise
    if not isinstance(value, str):
        return False
    return bool(COMMAND_INJECTION_REGEX.search(value))


def detect_path_traversal(value: str) -> bool:
    # Detect potential path traversal attempts.
    #
    # Args:
    #     value: String to check for path traversal patterns
    #
    # Returns:
    #     True if suspicious patterns detected, False otherwise
    if not isinstance(value, str):
        return False
    return bool(PATH_TRAVERSAL_REGEX.search(value))


def sanitize_string(value: str, max_length: int = MAX_STRING_LENGTH) -> str:
    # Sanitize and validate string input.
    #
    # Args:
    #     value: String to sanitize
    #     max_length: Maximum allowed length
    #
    # Returns:
    #     Sanitized string
    #
    # Raises:
    #     ValueError: If input is too long or contains suspicious patterns
    if not isinstance(value, str):
        return value

    # Check length first (fast check)
    if len(value) > max_length:
        raise ValueError(f"Input too long. Maximum length: {max_length} characters")

    # Check for injection attacks
    if detect_sql_injection(value):
        raise ValueError("Input contains potentially dangerous SQL patterns")

    if detect_xss(value):
        raise ValueError("Input contains potentially dangerous XSS patterns")

    if detect_command_injection(value):
        raise ValueError("Input contains potentially dangerous command injection patterns")

    if detect_path_traversal(value):
        raise ValueError("Input contains potentially dangerous path traversal patterns")

    return value


def sanitize_dict(data: dict[str, Any], max_length: int = MAX_STRING_LENGTH) -> dict[str, Any]:
    # Recursively sanitize all string values in a dictionary.
    #
    # Args:
    #     data: Dictionary to sanitize
    #     max_length: Maximum string length
    #
    # Returns:
    #     Sanitized dictionary
    #
    # Raises:
    #     ValueError: If any string is invalid
    sanitized = {}
    for key, value in data.items():
        if isinstance(value, str):
            sanitized[key] = sanitize_string(value, max_length)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value, max_length)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_string(item, max_length) if isinstance(item, str)
                else sanitize_dict(item, max_length) if isinstance(item, dict)
                else item
                for item in value
            ]
        else:
            sanitized[key] = value
    return sanitized


def get_max_request_size() -> int:
    # Get maximum request size from environment variable.
    #
    # Returns:
    #     Maximum request size in bytes (default: 1MB)
    max_size_mb = int(os.environ.get("MAX_REQUEST_SIZE_MB", "1"))
    return max_size_mb * 1_048_576


def get_max_string_length() -> int:
    # Get maximum string length from environment variable.
    #
    # Returns:
    #     Maximum string length in characters (default: 10000)
    return int(os.environ.get("MAX_STRING_LENGTH", str(MAX_STRING_LENGTH)))
