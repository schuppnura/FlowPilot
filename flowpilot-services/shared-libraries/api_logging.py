# Shared Logging Utilities for FlowPilot Services
#
# Structured JSON logging for API requests and responses to aid debugging.
# Logs are written to stdout in plain JSON format for easy inspection via CLI.
#
# Usage:
#   import api_logging
#
#   # At the start of an endpoint handler:
#   api_logging.log_api_request(
#       method="POST",
#       path="/v1/evaluate",
#       request_body=request_body,
#       token_claims=token_claims,
#       raw_token=raw_token  # optional
#   )
#
#   # After processing, before returning:
#   api_logging.log_api_response(
#       method="POST",
#       path="/v1/evaluate",
#       status_code=200,
#       response_body=result
#   )
#
# Environment variable: ENABLE_API_LOGGING (default: "0")
# Set to "1" to enable logging. When disabled, functions are no-ops.

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import security

# Configuration
ENABLE_API_LOGGING = os.environ.get("ENABLE_API_LOGGING", "0") == "1"


def _should_log() -> bool:
    # Check if logging is enabled via environment variable
    return ENABLE_API_LOGGING


def _print_separator() -> None:
    # Print a horizontal separator line to visually group API calls
    # Uses a simple line of dashes that's easy to spot in logs
    print("─" * 80, file=sys.stdout, flush=True)


def _safe_serialize(obj: Any) -> Any:
    # Safely serialize objects to JSON-compatible types
    # Handles common types that might not be directly JSON serializable
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(item) for item in obj]
    # For other types, convert to string representation
    return str(obj)


def _sanitize_token_for_logging(token: str | None) -> dict[str, Any] | None:
    # Decode and return token claims for logging, or None if decoding fails
    # This provides the decoded token information without exposing the raw token
    if not token:
        return None

    try:
        # Use security utility to decode token (without full validation for logging)
        # We just want the claims, not full validation
        claims = security.verify_token_string(token)
        return _safe_serialize(claims)
    except Exception:
        # If decoding fails, return a minimal safe representation
        return {"error": "failed_to_decode", "token_length": len(token) if token else 0}


def _extract_raw_token_from_request(request: Any) -> str | None:
    # Extract raw JWT token from FastAPI Request object.
    #
    # Args:
    #     request: FastAPI Request object with headers attribute
    #
    # Returns:
    #     Raw token string (without "Bearer " prefix) or None
    if not request or not hasattr(request, "headers"):
        return None

    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:]  # Remove "Bearer " prefix

    return None


def log_api_request(
    method: str,
    path: str,
    request_body: dict[str, Any] | None = None,
    token_claims: dict[str, Any] | None = None,
    raw_token: str | None = None,
    request: Any | None = None,  # FastAPI Request object
    path_params: dict[str, Any] | None = None,
    query_params: dict[str, Any] | None = None,
) -> None:
    # Log an API request with full context.
    #
    # Args:
    #     method: HTTP method (GET, POST, etc.)
    #     path: Request path
    #     request_body: Request body (for POST/PUT/PATCH)
    #     token_claims: Already decoded token claims (from verify_token dependency)
    #     raw_token: Raw JWT token string (optional, will be decoded if provided)
    #     request: FastAPI Request object (optional, will extract raw_token from headers if provided)
    #     path_params: Path parameters (from FastAPI path params)
    #     query_params: Query parameters (from FastAPI query params)
    #
    # Note: If both `raw_token` and `request` are provided, `raw_token` takes precedence.
    #       If only `request` is provided, the token will be extracted from the Authorization header.
    #
    # Outputs JSON to stdout with structure:
    # {
    #     "type": "api_request",
    #     "timestamp": "2025-12-21T13:00:00Z",
    #     "method": "POST",
    #     "path": "/v1/evaluate",
    #     "request_body": {...},
    #     "token_claims": {...},
    #     "path_params": {...},
    #     "query_params": {...}
    # }
    if not _should_log():
        return

    # Print separator line to visually group this API call
    _print_separator()

    # Extract raw token from request if not explicitly provided
    if raw_token is None and request is not None:
        raw_token = _extract_raw_token_from_request(request)

    log_entry: dict[str, Any] = {
        "type": "api_request",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": method,
        "path": path,
    }

    if request_body is not None:
        log_entry["request_body"] = _safe_serialize(request_body)

    # Prefer already-decoded claims, but decode raw token if provided
    if token_claims:
        log_entry["token_claims"] = _safe_serialize(token_claims)
    elif raw_token:
        decoded = _sanitize_token_for_logging(raw_token)
        if decoded:
            log_entry["token_claims"] = decoded

    if path_params:
        log_entry["path_params"] = _safe_serialize(path_params)

    if query_params:
        log_entry["query_params"] = _safe_serialize(query_params)

    # Write to stdout as single-line JSON
    print(json.dumps(log_entry, ensure_ascii=False), file=sys.stdout, flush=True)


def log_api_response(
    method: str,
    path: str,
    status_code: int,
    response_body: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    # Log an API response.
    #
    # Args:
    #     method: HTTP method (GET, POST, etc.)
    #     path: Request path
    #     status_code: HTTP status code
    #     response_body: Response body (if successful)
    #     error: Error message (if failed)
    #
    # Outputs JSON to stdout with structure:
    # {
    #     "type": "api_response",
    #     "timestamp": "2025-12-21T13:00:00Z",
    #     "method": "POST",
    #     "path": "/v1/evaluate",
    #     "status_code": 200,
    #     "response_body": {...}
    # }
    if not _should_log():
        return

    log_entry: dict[str, Any] = {
        "type": "api_response",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": method,
        "path": path,
        "status_code": status_code,
    }

    if response_body is not None:
        log_entry["response_body"] = _safe_serialize(response_body)

    if error:
        log_entry["error"] = error

    # Write to stdout as single-line JSON
    print(json.dumps(log_entry, ensure_ascii=False), file=sys.stdout, flush=True)


def log_api_call(
    method: str,
    path: str,
    request_body: dict[str, Any] | None = None,
    token_claims: dict[str, Any] | None = None,
    raw_token: str | None = None,
    request: Any | None = None,  # FastAPI Request object
    path_params: dict[str, Any] | None = None,
    query_params: dict[str, Any] | None = None,
    status_code: int | None = None,
    response_body: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    # Convenience function to log both request and response in one call.
    # Useful when you have all the information at once.
    log_api_request(
        method=method,
        path=path,
        request_body=request_body,
        token_claims=token_claims,
        raw_token=raw_token,
        request=request,
        path_params=path_params,
        query_params=query_params,
    )

    if status_code is not None:
        log_api_response(
            method=method,
            path=path,
            status_code=status_code,
            response_body=response_body,
            error=error,
        )
