# services/shared-libraries/security.py
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


#
# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
#

DEFAULT_MAX_REQUEST_SIZE_BYTES = 1_048_576  # 1 MB
DEFAULT_MAX_STRING_LENGTH = 10_000

DEFAULT_JWKS_CACHE_TTL_SECONDS = int(
    os.environ.get("JWKS_CACHE_TTL_SECONDS", "3600")
)

# Optional: enable signature/payload scanning (off by default to avoid false positives).
ENABLE_PAYLOAD_SIGNATURE_SCAN = os.environ.get("ENABLE_PAYLOAD_SIGNATURE_SCAN", "0") == "1"


#
# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
#

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


#
# ---------------------------------------------------------------------------
# JWT validation using JWKS (no network calls per request)
# ---------------------------------------------------------------------------
#

class JWTValidator:
    # Validates JWT Bearer tokens using JWKS for signature verification.
    #
    # Notes:
    # - JWKS is fetched once and cached (PyJWKClient handles this internally).
    # - No network call is made per token validation, only when JWKS needs refresh.
    # - JWT signature, expiration, and issuer are validated locally.
    def __init__(
        self,
        jwks_uri: str,
        issuer: str,
        audience: Optional[str] = None,
        *,
        cache_ttl_seconds: int = DEFAULT_JWKS_CACHE_TTL_SECONDS,
    ) -> None:
        self.issuer = issuer
        self.audience = audience
        
        # PyJWKClient caches JWKS and only refetches when needed
        self.jwks_client = PyJWKClient(
            jwks_uri,
            cache_keys=True,
            max_cached_keys=16,
            lifespan=cache_ttl_seconds,  # Cache lifespan in seconds
        )

    def validate(self, token: str) -> dict[str, Any]:
        try:
            # Get signing key from JWKS (cached)
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            
            # Decode and validate JWT locally (no network call)
            # Best practice: verify all standard claims
            decode_options = {
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,  # Not Before
                "verify_iss": True,
                "verify_aud": bool(self.audience),
                "require_exp": True,
                "require_iat": True,
            }
            
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
                issuer=self.issuer,
                audience=self.audience,
                options=decode_options,
                leeway=10,  # 10 seconds clock skew tolerance
            )
            
            # Additional best-practice validations
            self._validate_token_type(claims)
            self._validate_subject(claims)
            self._validate_issued_at(claims)
            
            return claims
            
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
            )
        except jwt.InvalidIssuerError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token issuer",
            )
        except jwt.InvalidAudienceError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token audience",
            )
        except jwt.InvalidSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token signature",
            )
        except jwt.DecodeError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed token",
            )
        except jwt.ImmatureSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token not yet valid (nbf)",
            )
        except jwt.MissingRequiredClaimError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token missing required claim: {str(exc)}",
            )
        except Exception as exc:
            # Catch-all for any other JWT validation errors
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token validation failed: {str(exc)}",
            )
    
    def _validate_token_type(self, claims: dict[str, Any]) -> None:
        # Best practice: verify token type is Bearer/Access token
        typ = claims.get("typ")
        if typ and typ.upper() not in ["BEARER", "AT+JWT", "JWT"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token type: {typ}",
            )
    
    def _validate_subject(self, claims: dict[str, Any]) -> None:
        # Best practice: require subject claim
        sub = claims.get("sub")
        if not sub or not isinstance(sub, str) or not sub.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing valid subject claim",
            )
    
    def _validate_issued_at(self, claims: dict[str, Any]) -> None:
        # Best practice: reject tokens issued too far in the future
        # (protects against time manipulation attacks)
        iat = claims.get("iat")
        if isinstance(iat, (int, float)):
            now = time.time()
            # Allow 60 seconds for clock skew
            if iat > now + 60:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token issued in the future",
                )


_http_bearer = HTTPBearer(auto_error=True)


# Singleton JWT validator instance
_jwt_validator: Optional[JWTValidator] = None


def _get_jwt_validator() -> JWTValidator:
    global _jwt_validator
    
    if _jwt_validator is None:
        jwks_uri = os.environ.get("KEYCLOAK_JWKS_URI", "").strip()
        issuer = os.environ.get("KEYCLOAK_ISSUER", "").strip()
        audience = os.environ.get("KEYCLOAK_AUDIENCE", "").strip() or None
        
        if not jwks_uri or not issuer:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Auth is not configured (missing KEYCLOAK_JWKS_URI or KEYCLOAK_ISSUER env vars)",
            )
        
        _jwt_validator = JWTValidator(
            jwks_uri=jwks_uri,
            issuer=issuer,
            audience=audience,
        )
    
    return _jwt_validator


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
) -> dict[str, Any]:
    # FastAPI dependency: validates Authorization: Bearer <token> using JWKS.
    #
    # Required env vars:
    # - KEYCLOAK_JWKS_URI (e.g., https://keycloak.example.com/realms/myrealm/protocol/openid-connect/certs)
    # - KEYCLOAK_ISSUER (e.g., https://keycloak.example.com/realms/myrealm)
    # - KEYCLOAK_AUDIENCE (optional, e.g., account or client_id)
    token = credentials.credentials
    validator = _get_jwt_validator()
    return validator.validate(token)


#
# ---------------------------------------------------------------------------
# Input validation / sanitization helpers
# ---------------------------------------------------------------------------
#

# Conservative control char check (allow tab/newline/carriage return)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# These patterns are intentionally conservative and are only used if
# ENABLE_PAYLOAD_SIGNATURE_SCAN=1. They are not “protection”; they are
# best treated as “signals” for telemetry or early rejection on endpoints
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

_SQL_RE = re.compile("|".join(SQL_INJECTION_PATTERNS), re.IGNORECASE) if SQL_INJECTION_PATTERNS else None
_XSS_RE = re.compile("|".join(XSS_PATTERNS), re.IGNORECASE) if XSS_PATTERNS else None
_CMD_RE = re.compile("|".join(COMMAND_INJECTION_PATTERNS), re.IGNORECASE) if COMMAND_INJECTION_PATTERNS else None
_TRAV_RE = re.compile("|".join(PATH_TRAVERSAL_PATTERNS), re.IGNORECASE) if PATH_TRAVERSAL_PATTERNS else None


def _detect_payload_signatures(value: str) -> Optional[str]:
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
    # - Optionally perform conservative “signature” detection (opt-in).
    if not isinstance(value, str):
        return value

    if len(value) > max_length:
        raise InputValidationError(f"Input too long. Maximum length: {max_length} characters")

    if _CONTROL_CHARS.search(value):
        raise InputValidationError("Input contains invalid control characters")

    signature = _detect_payload_signatures(value)
    if signature:
        raise InputValidationError(f"Input contains potentially dangerous content ({signature})")

    return value


def sanitize_dict(data: dict[str, Any], max_length: int = DEFAULT_MAX_STRING_LENGTH) -> dict[str, Any]:
    # Recursively sanitize all string values in a dictionary.
    #
    # Note: This does not “secure” downstream usage by itself. You must still:
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
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        
        # Prevent referrer leakage
        response.headers["Referrer-Policy"] = "no-referrer"
        
        # Permissions policy (disable unnecessary features)
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        return response


#
# ---------------------------------------------------------------------------
# Validation helpers for IDs and common patterns
# ---------------------------------------------------------------------------
#

# Common ID patterns (alphanumeric, hyphens, underscores)
_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
_UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)
# ISO 8601 date pattern (YYYY-MM-DD)
_DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def validate_id(value: str, field_name: str = "id", max_length: int = 255) -> str:
    # Validate an ID field (alphanumeric, hyphens, underscores only).
    if not isinstance(value, str) or not value.strip():
        raise InputValidationError(f"{field_name} must be a non-empty string")
    
    value = value.strip()
    
    if len(value) > max_length:
        raise InputValidationError(f"{field_name} too long (max {max_length} characters)")
    
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
        raise InputValidationError(f"{field_name} must be in ISO 8601 format (YYYY-MM-DD)")
    
    # Additional validation: check if it's a valid date
    try:
        year, month, day = map(int, value.split('-'))
        if not (1900 <= year <= 2100):
            raise ValueError("Year out of range")
        if not (1 <= month <= 12):
            raise ValueError("Month out of range")
        if not (1 <= day <= 31):
            raise ValueError("Day out of range")
    except (ValueError, AttributeError) as exc:
        raise InputValidationError(f"{field_name} is not a valid date") from exc
    
    return value


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
