# FlowPilot Security Library - Firebase Auth Version
#
# This module provides JWT validation using Firebase Admin SDK instead of Keycloak JWKS.
# All other security functions remain the same.

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from typing import Any, Optional
from collections.abc import Callable

import firebase_admin
import jwt as pyjwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from jose import JWTError
from jose import jwt as jose_jwt
from starlette.middleware.base import BaseHTTPMiddleware

# Constants
DEFAULT_MAX_REQUEST_SIZE_BYTES = 1_048_576  # 1 MB
DEFAULT_MAX_STRING_LENGTH = 10_000

# Optional: enable signature/payload scanning (off by default to avoid false positives)
ENABLE_PAYLOAD_SIGNATURE_SCAN = (
    os.environ.get("ENABLE_PAYLOAD_SIGNATURE_SCAN", "0") == "1"
)


class InputValidationError(ValueError):
    # Raised when request input fails validation/sanitization.
    pass


#
# ---------------------------------------------------------------------------
# Request-size protection middleware
# ---------------------------------------------------------------------------
#


class RequestSizeLimiterMiddleware(BaseHTTPMiddleware):
    # Middleware to limit request body size.
    #
    # Protects against resource exhaustion attacks via large payloads.
    def __init__(self, app, max_size: int = DEFAULT_MAX_REQUEST_SIZE_BYTES):
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                content_length_int = int(content_length)
            except ValueError:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "Invalid Content-Length header"},
                )

            if content_length_int > self.max_size:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={
                        "detail": f"Request body too large. Maximum size: {self.max_size} bytes",
                        "max_size_bytes": self.max_size,
                        "max_size_mb": round(self.max_size / 1_048_576, 2),
                    },
                )

        return await call_next(request)


def get_max_request_size() -> int:
    # Get maximum request size from environment variable.
    max_size_mb = int(os.environ.get("MAX_REQUEST_SIZE_MB", "1"))
    return max_size_mb * 1_048_576


def get_max_string_length() -> int:
    # Get maximum string length from environment variable.
    return int(os.environ.get("MAX_STRING_LENGTH", str(DEFAULT_MAX_STRING_LENGTH)))


def get_cors_config() -> dict[str, Any]:
    """
    Get CORS configuration from environment variables.
    
    Returns dict suitable for passing to CORSMiddleware constructor.
    
    Environment variables:
    - CORS_ALLOWED_ORIGINS: Comma-separated list of allowed origins (default: "*")
    - CORS_ALLOW_CREDENTIALS: "true" or "false" (default: "true")
    - CORS_ALLOW_METHODS: Comma-separated list (default: "*")
    - CORS_ALLOW_HEADERS: Comma-separated list (default: "*")
    
    Examples:
    - Development: CORS_ALLOWED_ORIGINS="*"
    - Production: CORS_ALLOWED_ORIGINS="https://app.example.com,https://admin.example.com"
    """
    origins_str = os.environ.get("CORS_ALLOWED_ORIGINS", "*")
    origins = [o.strip() for o in origins_str.split(",")] if origins_str != "*" else ["*"]

    allow_credentials = os.environ.get("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"

    methods_str = os.environ.get("CORS_ALLOW_METHODS", "*")
    methods = [m.strip() for m in methods_str.split(",")] if methods_str != "*" else ["*"]

    headers_str = os.environ.get("CORS_ALLOW_HEADERS", "*")
    headers = [h.strip() for h in headers_str.split(",")] if headers_str != "*" else ["*"]

    return {
        "allow_origins": origins,
        "allow_credentials": allow_credentials,
        "allow_methods": methods,
        "allow_headers": headers,
    }


#
# ---------------------------------------------------------------------------
# Input validation / sanitization helpers
# ---------------------------------------------------------------------------
#

# Conservative control char check (allow tab/newline/carriage return)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# These patterns are intentionally conservative and are only used if
# ENABLE_PAYLOAD_SIGNATURE_SCAN=1. They are not "protection"; they are
# best treated as "signals" for telemetry or early rejection on endpoints
# that should never receive free-form strings.
SQL_INJECTION_PATTERNS = [
    r"\bunion\b\s+\bselect\b",
    r"\bor\b\s+1\s*=\s*1\b",
    r"\bdrop\b\s+\btable\b",
]
XSS_PATTERNS = [
    r"<\s*script\b",
    r"\bon\w+\s*=",
    r"javascript:",
]
COMMAND_INJECTION_PATTERNS = [
    r";\s*\b(cat|curl|wget|bash|sh)\b",
    r"\|\s*\b(cat|curl|wget|bash|sh)\b",
]
PATH_TRAVERSAL_PATTERNS = [
    r"\.\./",
    r"\.\.\\",
]

_SQL_RE = (
    re.compile("|".join(SQL_INJECTION_PATTERNS), re.IGNORECASE)
    if SQL_INJECTION_PATTERNS
    else None
)
_XSS_RE = re.compile("|".join(XSS_PATTERNS), re.IGNORECASE) if XSS_PATTERNS else None
_CMD_RE = (
    re.compile("|".join(COMMAND_INJECTION_PATTERNS), re.IGNORECASE)
    if COMMAND_INJECTION_PATTERNS
    else None
)
_TRAV_RE = (
    re.compile("|".join(PATH_TRAVERSAL_PATTERNS), re.IGNORECASE)
    if PATH_TRAVERSAL_PATTERNS
    else None
)


def _detect_payload_signatures(value: str) -> str | None:
    if not ENABLE_PAYLOAD_SIGNATURE_SCAN:
        return None
    if not isinstance(value, str):
        return None

    if _SQL_RE and _SQL_RE.search(value):
        return "sql_signature"
    if _XSS_RE and _XSS_RE.search(value):
        return "xss_signature"
    if _CMD_RE and _CMD_RE.search(value):
        return "command_signature"
    if _TRAV_RE and _TRAV_RE.search(value):
        return "path_traversal_signature"
    return None


def sanitize_string(value: str, max_length: int = DEFAULT_MAX_STRING_LENGTH) -> str:
    # Sanitize and validate string input.
    #
    # Best-practice stance:
    # - Enforce hard length limits.
    # - Reject unsafe control characters (incl. NUL).
    # - Optionally perform conservative "signature" detection (opt-in).
    if not isinstance(value, str):
        return value

    if len(value) > max_length:
        raise InputValidationError(
            f"Input too long. Maximum length: {max_length} characters"
        )

    if _CONTROL_CHARS.search(value):
        raise InputValidationError("Input contains invalid control characters")

    signature = _detect_payload_signatures(value)
    if signature:
        raise InputValidationError(
            f"Input contains potentially dangerous content ({signature})"
        )

    return value


def sanitize_dict(
    data: dict[str, Any], max_length: int = DEFAULT_MAX_STRING_LENGTH
) -> dict[str, Any]:
    # Recursively sanitize all string values in a dictionary.
    #
    # Note: This does not "secure" downstream usage by itself. You must still:
    # - Parameterize DB queries
    # - Avoid shell invocation with user input
    # - Avoid unsafe template injection
    if not isinstance(data, dict):
        raise InputValidationError("Expected object")

    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            sanitized[key] = sanitize_string(value, max_length)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value, max_length)
        elif isinstance(value, list):
            sanitized_list: list[Any] = []
            for item in value:
                if isinstance(item, str):
                    sanitized_list.append(sanitize_string(item, max_length))
                elif isinstance(item, dict):
                    sanitized_list.append(sanitize_dict(item, max_length))
                else:
                    sanitized_list.append(item)
            sanitized[key] = sanitized_list
        else:
            sanitized[key] = value

    return sanitized


def sanitize_request_json_payload(payload: Any) -> Any:
    # Convenience for endpoints:
    # - If payload is dict/list, sanitize recursively; otherwise return as-is.
    max_len = get_max_string_length()
    if isinstance(payload, dict):
        return sanitize_dict(payload, max_len)
    if isinstance(payload, list):
        sanitized_list: list[Any] = []
        for item in payload:
            if isinstance(item, dict):
                sanitized_list.append(sanitize_dict(item, max_len))
            elif isinstance(item, str):
                sanitized_list.append(sanitize_string(item, max_len))
            else:
                sanitized_list.append(item)
        return sanitized_list
    if isinstance(payload, str):
        return sanitize_string(payload, max_len)
    return payload


def sanitize_error_message(message: str, include_details: bool = False) -> str:
    # Sanitize error messages to avoid leaking sensitive information.
    #
    # In production, set include_details=False to hide internal errors.
    if not include_details:
        # Generic error messages for common patterns
        if "database" in message.lower() or "sql" in message.lower():
            return "Database error occurred"
        if "file" in message.lower() or "path" in message.lower():
            return "File system error occurred"
        if "network" in message.lower() or "connection" in message.lower():
            return "Network error occurred"
        if "environment" in message.lower() or "config" in message.lower():
            return "Configuration error occurred"

    # Truncate very long messages
    if len(message) > 200:
        message = message[:200] + "..."

    return message


def safe_parse_json_bytes(body_bytes: bytes) -> Any:
    # Strict JSON parse helper with clear errors.
    try:
        return json.loads(body_bytes.decode("utf-8"))
    except Exception as exc:
        raise InputValidationError("Invalid JSON payload") from exc


#
# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------
#


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    # Add security headers to all responses.
    #
    # Best practice headers to prevent common web vulnerabilities.
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent XSS in older browsers
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Strict transport security (if using HTTPS)
        # Uncomment if deployed with HTTPS:
        # response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Content Security Policy (restrictive default)
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )

        # Prevent referrer leakage
        response.headers["Referrer-Policy"] = "no-referrer"

        # Permissions policy (disable unnecessary features)
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=()"
        )

        return response


#
# ---------------------------------------------------------------------------
# Validation helpers for IDs and common patterns
# ---------------------------------------------------------------------------
#

# Common ID patterns (alphanumeric, hyphens, underscores)
_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
# ISO 8601 date pattern (YYYY-MM-DD)
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_id(value: str, field_name: str = "id", max_length: int = 255) -> str:
    # Validate an ID field (alphanumeric, hyphens, underscores only).
    if not isinstance(value, str) or not value.strip():
        raise InputValidationError(f"{field_name} must be a non-empty string")

    value = value.strip()

    if len(value) > max_length:
        raise InputValidationError(
            f"{field_name} too long (max {max_length} characters)"
        )

    if not _ID_PATTERN.match(value):
        raise InputValidationError(
            f"{field_name} contains invalid characters (only alphanumeric, hyphen, underscore allowed)"
        )

    return value


def validate_uuid(value: str, field_name: str = "id") -> str:
    # Validate a UUID field.
    if not isinstance(value, str) or not value.strip():
        raise InputValidationError(f"{field_name} must be a non-empty string")

    value = value.strip().lower()

    if not _UUID_PATTERN.match(value):
        raise InputValidationError(f"{field_name} is not a valid UUID")

    return value


def validate_iso_date(value: str, field_name: str = "date") -> str:
    # Validate an ISO 8601 date string (YYYY-MM-DD).
    if not isinstance(value, str) or not value.strip():
        raise InputValidationError(f"{field_name} must be a non-empty string")

    value = value.strip()

    if not _DATE_PATTERN.match(value):
        raise InputValidationError(
            f"{field_name} must be in ISO 8601 format (YYYY-MM-DD)"
        )

    # Additional validation: check if it's a valid date
    try:
        year, month, day = map(int, value.split("-"))
        if not (1900 <= year <= 2100):
            raise ValueError("Year out of range")
        if not (1 <= month <= 12):
            raise ValueError("Month out of range")
        if not (1 <= day <= 31):
            raise ValueError("Day out of range")
    except (ValueError, AttributeError) as exc:
        raise InputValidationError(f"{field_name} is not a valid date") from exc

    return value


# ============================================================================
# Firebase Admin SDK Initialization (for token exchange endpoint only)
# ============================================================================

_firebase_app: firebase_admin.App | None = None


def _initialize_firebase() -> None:
    # Initialize Firebase Admin SDK
    global _firebase_app

    if _firebase_app is not None:
        return

    # Firebase Admin SDK uses Application Default Credentials (ADC) on Cloud Run
    # No explicit credentials needed when running on GCP
    try:
        _firebase_app = firebase_admin.initialize_app()
    except ValueError:
        # Already initialized
        _firebase_app = firebase_admin.get_app()


# ============================================================================
# FlowPilot Token Validation (primary authorization method)
# ============================================================================

_FLOWPILOT_PUBLIC_KEY: str | None = None


def _get_flowpilot_public_key() -> str:
    """Load FlowPilot public key from file system or environment variable (cached)."""
    global _FLOWPILOT_PUBLIC_KEY
    if _FLOWPILOT_PUBLIC_KEY:
        return _FLOWPILOT_PUBLIC_KEY

    # First try environment variable (for Cloud Run secret mounting)
    env_key = os.environ.get("SIGNING_KEY_PUB_CONTENT")
    if env_key:
        _FLOWPILOT_PUBLIC_KEY = env_key
        return _FLOWPILOT_PUBLIC_KEY

    # Fall back to file system (for local development)
    pub_key_path = os.environ.get("FLOWPILOT_PUBLIC_KEY_PATH", "/secrets/signing-key-pub")
    try:
        with open(pub_key_path) as f:
            _FLOWPILOT_PUBLIC_KEY = f.read()
        return _FLOWPILOT_PUBLIC_KEY
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="FlowPilot public key not configured (neither SIGNING_KEY_PUB_CONTENT env var nor file at FLOWPILOT_PUBLIC_KEY_PATH)"
        )


# ============================================================================
# JWT Validation
# ============================================================================

_http_bearer = HTTPBearer(auto_error=True)


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
) -> dict[str, Any]:
    """
    FastAPI dependency: validates Authorization: Bearer <token>.
    
    By default, validates FlowPilot access tokens (pseudonymous, sub only).
    Use verify_firebase_token() for the token exchange endpoint specifically.
    """
    token = credentials.credentials
    return verify_flowpilot_token(token)


def verify_token_string(token: str) -> dict[str, Any]:
    """
    Validate a FlowPilot access token string.
    
    This is used when you already have the token string (not from HTTPBearer dependency).
    Returns decoded claims if valid, raises HTTPException if invalid.
    """
    return verify_flowpilot_token(token)


def verify_flowpilot_token(token: str) -> dict[str, Any]:
    """
    Validate FlowPilot access token (pseudonymous JWT with sub only).
    
    These tokens are issued by the /v1/token/exchange endpoint and are the
    primary authorization mechanism for all FlowPilot backend services.
    """
    try:
        # Get FlowPilot public key
        public_key = _get_flowpilot_public_key()

        # Expected issuer and audience
        expected_issuer = os.environ.get("FLOWPILOT_TOKEN_ISSUER", "https://flowpilot-authz-api")
        expected_audience = os.environ.get("FLOWPILOT_TOKEN_AUDIENCE", "flowpilot")

        # Decode and validate token
        claims = jose_jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=expected_audience,
            issuer=expected_issuer,
        )

        # Verify token_type
        if claims.get("token_type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type (expected access token)"
            )

        # Verify sub claim exists
        if not claims.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing sub claim in token"
            )

        return claims

    except JWTError as flowpilot_error:
        # FlowPilot token validation failed - try Google Cloud identity token as fallback
        # This allows service-to-service calls using GCP metadata server tokens
        try:
            # Try to decode as a Google Cloud identity token (RS256)
            unverified = pyjwt.decode(token, options={"verify_signature": False})

            # Check if this looks like a Google Cloud identity token
            iss = unverified.get("iss", "")
            if "accounts.google.com" in iss or "googleapis.com" in iss:
                # This is a Google Cloud token - verify it properly
                # Verify the token using Google's public keys
                decoded = id_token.verify_token(
                    token,
                    google_requests.Request(),
                    audience="flowpilot-services",
                )

                # Extract claims from verified token
                claims = {
                    "sub": decoded.get("sub") or decoded.get("email"),
                    "email": decoded.get("email"),
                    "iss": decoded.get("iss"),
                    "aud": decoded.get("aud"),
                    "iat": decoded.get("iat"),
                    "exp": decoded.get("exp"),
                    "persona": "service",
                    "token_type": "service",  # Mark as service token
                }

                return claims
            else:
                # Not a GCP token either
                raise flowpilot_error

        except Exception:
            # GCP token verification also failed - raise original FlowPilot error
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid FlowPilot access token: {str(flowpilot_error)}"
            ) from flowpilot_error
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {str(e)}"
        ) from e


def verify_firebase_token(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
) -> dict[str, Any]:
    """
    FastAPI dependency: validates Firebase ID token (for /v1/token/exchange endpoint ONLY).
    
    This function should only be used by the /v1/token/exchange endpoint
    to validate incoming Firebase ID tokens before exchanging them for
    pseudonymous FlowPilot access tokens.
    
    All other endpoints should use verify_token() which validates FlowPilot tokens.
    """
    token = credentials.credentials
    return verify_firebase_token_string(token)


def verify_firebase_token_string(token: str) -> dict[str, Any]:
    """
    Validate a raw Firebase ID token string.
    
    Returns decoded claims if valid, raises HTTPException if invalid.
    This is used by the token exchange endpoint to validate incoming Firebase tokens.
    """

    # First try Firebase token verification
    _initialize_firebase()

    try:
        decoded_token = auth.verify_id_token(token)

        # Map to expected claims format
        claims = {
            "sub": decoded_token.get("uid"),
            "email": decoded_token.get("email"),
            "email_verified": decoded_token.get("email_verified", False),
            "iss": decoded_token.get("iss"),
            "aud": decoded_token.get("aud"),
            "iat": decoded_token.get("iat"),
            "exp": decoded_token.get("exp"),
            "auth_time": decoded_token.get("auth_time"),
        }

        # Add custom claims
        custom_claims = decoded_token.get("custom_claims", {})
        if custom_claims:
            claims.update(custom_claims)

        if "persona" not in claims:
            claims["persona"] = decoded_token.get("persona", "traveler")

        return claims

    except Exception as firebase_error:
        # Firebase verification failed - try service token (HS256 JWT)
        try:
            import jwt

            # Try to decode as a service token (HS256)
            decoded = jwt.decode(token, 'secret', algorithms=['HS256'], options={'verify_signature': True})

            # Extract claims
            claims = {
                "sub": decoded.get("sub") or decoded.get("email"),
                "email": decoded.get("email"),
                "iss": decoded.get("iss"),
                "aud": decoded.get("aud"),
                "iat": decoded.get("iat"),
                "exp": decoded.get("exp"),
                "persona": decoded.get("persona", "service"),
            }

            return claims

        except Exception as service_error:
            # Service token verification failed - try Google Cloud identity token
            try:
                # Try to decode as a Google Cloud identity token (RS256)
                # These are signed JWTs from GCP metadata server
                # We decode without verification first to check if it's a GCP token
                unverified = pyjwt.decode(token, options={"verify_signature": False})

                # Check if this looks like a Google Cloud identity token
                iss = unverified.get("iss", "")
                if "accounts.google.com" in iss or "googleapis.com" in iss:
                    # This is a Google Cloud token - verify it properly
                    # For Cloud Run identity tokens, we can verify using Google's public keys
                    try:
                        # Verify the token using Google's public keys
                        # The audience should match what was requested when creating the token
                        decoded = id_token.verify_token(
                            token,
                            google_requests.Request(),
                            audience="flowpilot-services",  # Must match the audience in get_service_token
                        )

                        # Extract claims from verified token
                        claims = {
                            "sub": decoded.get("sub") or decoded.get("email"),
                            "email": decoded.get("email"),
                            "iss": decoded.get("iss"),
                            "aud": decoded.get("aud"),
                            "iat": decoded.get("iat"),
                            "exp": decoded.get("exp"),
                            "persona": "service",
                        }

                        return claims
                    except Exception as verify_error:
                        # If verification fails, try the tokeninfo endpoint as last resort
                        raise verify_error
                else:
                    # Not a Google Cloud token, try access token verification
                    raise ValueError("Not a Google Cloud identity token")

            except Exception as gcp_error:
                # All verification methods failed
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Token verification failed: Firebase: {str(firebase_error)}, Service: {str(service_error)}, GCP: {str(gcp_error)}",
                ) from gcp_error


# ============================================================================
# Service-to-service authentication
# For Cloud Run, use identity tokens instead of Firebase tokens
# ============================================================================

_service_token_cache: dict[str, Any] | None = None


def clear_service_token_cache() -> None:
    # Clear the service token cache
    global _service_token_cache
    _service_token_cache = None


clear_service_token_cache()


def get_service_token() -> str | None:
    # Get service-to-service token for Cloud Run services.
    # Uses Google Cloud's metadata server to fetch identity tokens.
    # These tokens are signed by Google and verified using Google's public keys.
    # Caches token and refreshes when expired.

    global _service_token_cache

    # Check if we have a cached token that's still valid
    if _service_token_cache:
        expires_at = _service_token_cache.get("expires_at", 0)
        if time.time() < expires_at - 60:  # Refresh 60 seconds before expiry
            return _service_token_cache.get("access_token")

    # Get Cloud Run identity token from metadata server
    try:
        # For Cloud Run service-to-service auth, request an identity token from metadata server
        # The audience must match what the receiving service expects during verification
        audience = "flowpilot-services"

        metadata_url = f"http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience={audience}"
        req = urllib.request.Request(metadata_url)
        req.add_header("Metadata-Flavor", "Google")

        with urllib.request.urlopen(req, timeout=5) as response:
            token = response.read().decode('utf-8')

        # Cache token (Google identity tokens typically valid for 1 hour)
        _service_token_cache = {
            "access_token": token,
            "expires_at": time.time() + 3600,
        }

        return token

    except Exception as e:
        # If we can't get a metadata server token (e.g., not running on GCP),
        # log warning and return None
        print(f"Warning: Failed to get service token from metadata server: {e}", flush=True)
        print("Service-to-service calls may fail if authentication is required.", flush=True)
        return None
