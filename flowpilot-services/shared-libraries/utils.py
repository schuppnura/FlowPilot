# Shared Utilities for FlowPilot Services
#
# Common utility functions used across all FlowPilot services including:
# - String validation and parsing
# - URL building and HTTP operations
# - JSON parsing and configuration loading
# - Timeout management
#
# These utilities provide consistent error handling and validation across services.

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import api_logging
import requests

# Import cache module (optional - degrades gracefully if not available)
try:
    import cache
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False


def read_env_string(name: str, default_value: str | None = None) -> str:
    # Read required environment variable as string.
    # Args:
    #     name: Environment variable name
    #     default_value: Optional default value; if None, raises error when missing
    # Returns:
    #     Normalized string value (stripped of whitespace)
    # Raises:
    #     ValueError: If variable is not set or empty and no default provided
    value = os.getenv(name)
    if value is None or value.strip() == "":
        if default_value is None:
            raise ValueError(f"Required environment variable not set: {name}")
        return default_value
    return value.strip()


def read_env_int(name: str, default_value: int | None = None) -> int:
    # Read required environment variable as integer.
    # Args:
    #     name: Environment variable name
    #     default_value: Optional default value; if None, raises error when missing
    # Returns:
    #     Integer value
    # Raises:
    #     ValueError: If variable is not set/empty and no default, or if invalid integer
    value = os.getenv(name)
    if value is None or value.strip() == "":
        if default_value is None:
            raise ValueError(f"Required environment variable not set: {name}")
        return default_value
    try:
        return int(value.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid integer value for {name}: {value}") from exc


def read_env_float(name: str, default_value: float | None = None) -> float:
    # Read required environment variable as float.
    # Args:
    #     name: Environment variable name
    #     default_value: Optional default value; if None, raises error when missing
    # Returns:
    #     Float value
    # Raises:
    #     ValueError: If variable is not set/empty and no default, or if invalid float
    value = os.getenv(name)
    if value is None or value.strip() == "":
        if default_value is None:
            raise ValueError(f"Required environment variable not set: {name}")
        return default_value
    try:
        return float(value.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid float value for {name}: {value}") from exc


def read_env_bool(name: str, default_value: bool | None = None) -> bool:
    # Read required environment variable as boolean.
    # Recognizes common boolean representations:
    #   True: "true", "yes", "y", "1", "on" (case-insensitive)
    #   False: "false", "no", "n", "0", "off" (case-insensitive)
    # Args:
    #     name: Environment variable name
    #     default_value: Optional default value; if None, raises error when missing
    # Returns:
    #     Boolean value
    # Raises:
    #     ValueError: If variable is not set or empty and no default provided
    value = os.getenv(name)
    if value is None or value.strip() == "":
        if default_value is None:
            raise ValueError(f"Required environment variable not set: {name}")
        return default_value
    normalized = value.strip().lower()
    if normalized in {"yes", "y", "true", "t", "1", "on"}:
        return True
    if normalized in {"no", "n", "false", "f", "0", "off"}:
        return False
    raise ValueError(
        f"Invalid boolean value for {name}: {value} (expected true/false/yes/no/1/0)"
    )


# ============================================================================
# HTTP Client Configuration
# ============================================================================

# Centralized HTTP client configuration (required environment variables)
HTTP_DEFAULT_TIMEOUT = read_env_float("HTTP_DEFAULT_TIMEOUT")
HTTP_VERIFY_TLS = read_env_bool("HTTP_VERIFY_TLS")


def get_http_config() -> dict[str, Any]:
    # Return HTTP configuration dict compatible with requests library.
    # Usage: requests.get(url, **get_http_config())
    return {
        "timeout": HTTP_DEFAULT_TIMEOUT,
        "verify": HTTP_VERIFY_TLS,
    }


# ============================================================================
# Value Coercion Functions
# ============================================================================


def coerce_int(value: Any, default: int) -> int:
    # Convert a value to an integer, returning default if conversion fails or value is None.
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def coerce_dict(value: Any, field_name: str | None = None) -> dict[str, Any]:
    # Convert a value to a dict, raising error on invalid types.
    # Args:
    #     value: Value to convert (None or dict are acceptable)
    #     field_name: Optional field name for error messages
    # Returns:
    #     dict if value is dict, empty dict if value is None
    # Raises:
    #     ValueError: If value is not None and not a dict (API contract violation)
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    # API contract violation - someone sent wrong type
    field_msg = f" for {field_name}" if field_name else ""
    raise ValueError(
        f"Invalid type{field_msg}: expected dict or null, got {type(value).__name__}"
    )


def coerce_bool(value: Any, default: bool) -> bool:
    # Convert common string/primitive representations to boolean.
    # True: "yes", "y", "true", "t", "1", "on" (case-insensitive)
    # False: any other present value
    # Default applied only when value is None/empty.
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return default
        return normalized in {"yes", "y", "true", "t", "1", "on"}

    return bool(value)


def coerce_float(value: Any, default: float | None = None) -> float | None:
    # Convert a value to a float, returning default if conversion fails or value is None.
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def coerce_str(value: Any, default: str | None = None) -> str | None:
    # Convert a value to a string, returning default if value is None or empty.
    if value is None:
        return default
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else default
    # Convert non-string types to string
    return str(value)


def normalize_departure_date(date_value: Any) -> str | None:
    # Normalize departure date to RFC3339 format for OPA consumption.
    # Accepts:
    #   - RFC3339 format (e.g., "2025-12-31T00:00:00Z")
    #   - Date-only format (e.g., "2025-12-31") -> converted to midnight UTC
    # Returns:
    #   - RFC3339 string or None if invalid/missing
    if date_value is None:
        return None

    date_str = str(date_value).strip()
    if not date_str:
        return None

    # If already RFC3339 format (contains "T"), return as-is
    if "T" in date_str:
        return date_str

    # If date-only format (YYYY-MM-DD), convert to RFC3339 at midnight UTC
    parts = date_str.split("-")
    if len(parts) == 3:
        try:
            year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])
            return f"{year:04d}-{month:02d}-{day:02d}T00:00:00Z"
        except (ValueError, IndexError):
            return None

    return None


def coerce_positive_int(value: str, variable_name: str) -> int:
    # Parse and validate a positive integer from env/CLI to prevent silent misconfiguration.
    try:
        parsed = int(value)
    except ValueError as exception:
        raise ValueError(
            f"Invalid {variable_name}: expected integer, got '{value}'."
        ) from exception
    if parsed <= 0:
        raise ValueError(f"Invalid {variable_name}: expected > 0, got '{value}'.")
    return parsed


def coerce_positive_float(raw_value: str, field_name: str) -> float:
    # Parse a positive float from a string
    # why: validate numeric config/CLI inputs early
    # assumptions: raw_value is user-provided text
    # side effects: raises ValueError on invalid input.
    if raw_value is None:
        raise ValueError(f"{field_name} must be provided")

    value_text = str(raw_value).strip()
    if value_text == "":
        raise ValueError(f"{field_name} must be provided")

    try:
        parsed_value = float(value_text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a number (got '{value_text}')") from exc

    if parsed_value <= 0.0:
        raise ValueError(f"{field_name} must be > 0 (got {parsed_value})")

    return parsed_value


def coerce_timestamp(value: Any = None) -> str:
    # Provide a stable UTC timestamp string for created_at and comparisons, avoiding timezone ambiguity.
    # Args:
    #     value: Optional timestamp value to parse. If None, returns current timestamp.
    #            Accepts ISO 8601 strings, datetime objects, or Unix timestamps (int/float).
    # Returns:
    #     RFC3339 UTC timestamp string (e.g., "2025-12-31T23:59:59Z")
    if value is None:
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    
    # If already a datetime object
    if isinstance(value, datetime):
        return (
            value.astimezone(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    
    # If string, try parsing as ISO 8601
    if isinstance(value, str):
        value_str = value.strip()
        if not value_str:
            return coerce_timestamp()
        
        # Normalize "Z" to "+00:00" for parsing
        if value_str.endswith("Z"):
            value_str = value_str[:-1] + "+00:00"
        
        try:
            parsed = datetime.fromisoformat(value_str)
            return (
                parsed.astimezone(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
        except ValueError:
            # Invalid format, return current timestamp
            return coerce_timestamp()
    
    # If Unix timestamp (int or float)
    if isinstance(value, (int, float)):
        try:
            parsed = datetime.fromtimestamp(value, tz=timezone.utc)
            return (
                parsed.replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
        except (ValueError, OSError):
            # Invalid timestamp, return current
            return coerce_timestamp()
    
    # Fallback: return current timestamp
    return coerce_timestamp()


def coerce_email(value: Any, default: str | None = None) -> str | None:
    # Validate and normalize an email address.
    # Args:
    #     value: Email address to validate (string or None)
    #     default: Default value if validation fails or value is None
    # Returns:
    #     Normalized email address (lowercase) or default if invalid
    # Note:
    #     Uses a simple regex pattern for basic validation.
    #     Does not perform DNS/MX record checks or deep RFC 5322 validation.
    if value is None:
        return default
    
    if not isinstance(value, str):
        return default
    
    email_str = value.strip().lower()
    
    if not email_str:
        return default
    
    # Basic email validation regex
    # Matches: local-part@domain.tld
    # Allows alphanumeric, dots, hyphens, underscores, plus signs in local part
    # Requires at least one dot in domain part
    email_pattern = r'^[a-z0-9][a-z0-9._+-]*@[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$'
    
    if re.match(email_pattern, email_str):
        return email_str
    
    return default


def coerce_utc(value: str | None) -> datetime | None:
    # Parse a strict subset of ISO-8601 UTC timestamps used by the service, returning None for missing values.
    if value is None:
        return None

    if not isinstance(value, str) or not value.strip():
        return None

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return None

    return parsed.astimezone(timezone.utc)


def truncate_text(value: str | None, max_length: int) -> str:
    # Truncate text for error messages to keep logs readable and avoid leaking large upstream payloads.
    if value is None:
        return ""
    stripped = value.strip()
    if len(stripped) <= max_length:
        return stripped
    return stripped[:max_length] + "…"


def require_non_empty_list(value: Any, field_name: str) -> list[str]:
    # Validate scope arrays as non-empty lists of non-empty strings to prevent unsafe or ambiguous permissions.
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list of strings")

    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} items must be non-empty list of strings")
        normalized.append(item.strip())

    return normalized


def require_non_empty_string(value: Any, field_name: str) -> str:
    # Validate that a field is a non-empty string to fail fast, protect callers, and improve diagnostics.
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def require_optional_string(value: Any, field_name: str) -> str | None:
    # Validate optional strings without forcing presence, ensuring consistent normalization to None.
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string or null")
    stripped = value.strip()
    return stripped if stripped else None


def build_url(base_url: str, path: str) -> str:
    # Build a stable absolute URL from base URL + path to avoid double slashes and missing separators.
    base = base_url.rstrip("/") + "/"
    relative = path.lstrip("/")
    return urljoin(base, relative)


def parse_json_object(text: str, context: str) -> dict[str, Any]:
    # Parse JSON response into an object
    # assumption: callers expect an object and want actionable errors.
    if not text or not text.strip():
        raise ValueError(f"Empty JSON response: {context}")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exception:
        raise ValueError(
            f"Invalid JSON response: {context} body={truncate_text(text, 800)}"
        ) from exception
    if not isinstance(parsed, dict):
        raise ValueError(f"JSON response must be an object: {context}")
    return parsed


def http_get_text(
    url: str, timeout_seconds: int, headers: dict[str, str] | None
) -> tuple[int, str]:
    # Perform HTTP GET and return (status, text)
    # side effect: network I/O and raises on transport errors.
    try:
        response = requests.get(
            url, headers=headers or {}, timeout=int(timeout_seconds)
        )
    except requests.RequestException as exception:
        raise ValueError(f"HTTP GET failed: url={url}") from exception
    return int(response.status_code), str(response.text)


def http_get_json(
    url: str,
    params: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    # Perform HTTP GET expecting JSON object with optional query parameters
    # Includes automatic request/response logging via api_logging
    # Now with transparent caching support (if cache module available)
    #
    # Args:
    #     url: Full URL to GET from
    #     params: Optional query parameters (e.g., {"key": "value"})
    #     timeout_seconds: Optional timeout in seconds. If None, uses get_http_config() defaults
    #     headers: Optional HTTP headers (e.g., {"Authorization": "Bearer token"})
    #
    # Returns:
    #     Response body as dict
    #
    # Raises:
    #     RuntimeError: On non-2xx status or invalid JSON response
    
    if url.strip() == "":
        raise ValueError("url must be non-empty")
    
    # Try cache first (if available and enabled)
    if CACHE_AVAILABLE:
        try:
            return cache.http_get_json_with_cache(
                url=url,
                params=params,
                timeout_seconds=timeout_seconds,
                headers=headers,
                http_get_impl=_http_get_json_impl  # Pass through to actual implementation
            )
        except Exception as e:
            # Cache module had an error - fall back to direct call
            api_logging.log_api_response(
                method="CACHE",
                path=url,
                status_code=0,
                error=f"Cache wrapper error, falling back to direct call: {e}",
            )
    
    # Cache not available or disabled - direct call
    return _http_get_json_impl(url, params, timeout_seconds, headers)


def _http_get_json_impl(
    url: str,
    params: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    # Internal implementation of HTTP GET (called by http_get_json or cache layer)
    # This is the actual HTTP call logic, separated so cache can wrap it
    
    # Use provided timeout or fall back to get_http_config() defaults
    if timeout_seconds is not None:
        request_kwargs = {"timeout": timeout_seconds}
    else:
        request_kwargs = get_http_config()
    
    # Log outbound request
    api_logging.log_api_request(
        method="GET",
        path=url,
        request_body=params,  # Log query params as request_body for visibility
    )
    
    # Make request
    try:
        response = requests.get(
            url,
            params=params or {},
            headers=headers or {},
            **request_kwargs
        )
    except requests.RequestException as exc:
        api_logging.log_api_response(
            method="GET",
            path=url,
            status_code=0,
            error=f"Network error: {exc}",
        )
        raise RuntimeError(f"HTTP GET failed: url={url}") from exc
    
    if response.status_code < 200 or response.status_code >= 300:
        # Log error response
        api_logging.log_api_response(
            method="GET",
            path=url,
            status_code=response.status_code,
            error=f"HTTP GET non-2xx: body={truncate_text(response.text, 800)}",
        )
        raise RuntimeError(
            f"HTTP GET non-2xx: url={url} http={response.status_code} body={truncate_text(response.text, 800)}"
        )
    
    try:
        response_body = response.json()
    except ValueError as exc:
        # Log JSON parsing error
        api_logging.log_api_response(
            method="GET",
            path=url,
            status_code=response.status_code,
            error=f"Invalid JSON response: body={truncate_text(response.text, 800)}",
        )
        raise RuntimeError(
            f"HTTP GET invalid JSON response: url={url} http={response.status_code} body={truncate_text(response.text, 800)}"
        ) from exc
    
    # Log successful response
    api_logging.log_api_response(
        method="GET",
        path=url,
        status_code=response.status_code,
        response_body=response_body,
    )
    
    return response_body


def http_post_json(
    url: str,
    payload: dict,
    timeouts: tuple[float, float] | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    # POST JSON and return JSON
    # why: centralize outbound HTTP with consistent timeouts, errors, and logging
    # assumptions: endpoint returns JSON on success
    # side effects: network I/O, automatic request/response logging via api_logging, cache invalidation
    #
    # Args:
    #     url: Full URL to POST to
    #     payload: JSON payload (dict)
    #     timeouts: Optional (connect, read) timeout tuple. If None, uses get_http_config() defaults
    #     headers: Optional HTTP headers (e.g., {"Authorization": "Bearer token"})
    #
    # Returns:
    #     Response body as dict
    #
    # Raises:
    #     RuntimeError: On non-2xx status or invalid JSON response
    if url.strip() == "":
        raise ValueError("url must be non-empty")
    
    # Use provided timeouts or fall back to get_http_config() defaults
    if timeouts is not None:
        if len(timeouts) != 2:
            raise ValueError(f"timeouts must be a (connect, read) tuple, got {timeouts}")
        request_kwargs = {"timeout": timeouts}
    else:
        request_kwargs = get_http_config()
    
    # Log outbound request
    api_logging.log_api_request(
        method="POST",
        path=url,
        request_body=payload,
    )
    
    # Make request
    response = requests.post(
        url,
        json=payload,
        headers=headers or {},
        **request_kwargs
    )
    
    if response.status_code < 200 or response.status_code >= 300:
        # Log error response
        api_logging.log_api_response(
            method="POST",
            path=url,
            status_code=response.status_code,
            error=f"HTTP POST non-2xx: body={truncate_text(response.text, 800)}",
        )
        raise RuntimeError(
            f"HTTP POST non-2xx: url={url} http={response.status_code} body={truncate_text(response.text, 800)}"
        )
    
    try:
        response_body = response.json()
    except ValueError as exc:
        # Log JSON parsing error
        api_logging.log_api_response(
            method="POST",
            path=url,
            status_code=response.status_code,
            error=f"Invalid JSON response: body={truncate_text(response.text, 800)}",
        )
        raise RuntimeError(
            f"HTTP POST invalid JSON response: url={url} http={response.status_code} body={truncate_text(response.text, 800)}"
        ) from exc
    
    # Log successful response
    api_logging.log_api_response(
        method="POST",
        path=url,
        status_code=response.status_code,
        response_body=response_body,
    )
    
    # Invalidate cache after successful POST (write operations should clear stale cache)
    if CACHE_AVAILABLE:
        try:
            # Determine resource type from URL for targeted invalidation
            if "delegation" in url.lower():
                cache.invalidate_cache_for_resource("delegation")
            elif "persona" in url.lower():
                cache.invalidate_cache_for_resource("persona")
            elif "workflow" in url.lower():
                # Workflow changes might affect authorization decisions
                cache.invalidate_cache_for_resource("authz")
            # Note: OPA evaluations are not cached, so no invalidation needed
        except Exception as e:
            # Cache invalidation failure should not break the request
            api_logging.log_api_response(
                method="CACHE",
                path="INVALIDATE",
                status_code=0,
                error=f"Cache invalidation after POST failed: {e}",
            )
    
    return response_body


def build_timeouts(
    connect_seconds: float = 5.0, read_seconds: float = 30.0
) -> tuple[float, float]:
    # Build a requests-compatible timeout tuple
    # why: keep HTTP calls bounded and predictable
    # assumptions: used with requests(timeout=(connect, read))
    # side effects: none.
    if connect_seconds <= 0:
        raise ValueError(f"connect_seconds must be > 0 (got {connect_seconds})")
    if read_seconds <= 0:
        raise ValueError(f"read_seconds must be > 0 (got {read_seconds})")

    return (float(connect_seconds), float(read_seconds))


def load_json_object(file_path: str) -> dict:
    # Load a JSON config file and return it as a dict object
    # why: centralized JSON loading with consistent error handling
    # side effect: filesystem I/O.
    try:
        with open(file_path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exception:
        raise ValueError(f"Config file not found: {file_path}") from exception
    except json.JSONDecodeError as exception:
        raise ValueError(f"Config file is not valid JSON: {file_path}") from exception

    if not isinstance(data, dict):
        raise ValueError(f"Config file root must be a JSON object: {file_path}")

    return data


def merge_config(base_config: dict, override_config: dict) -> dict:
    # Merge config shallowly
    # why: keep override semantics explicit and avoid surprising deep merges
    # side effect: none.
    merged = dict(base_config)
    for key, value in override_config.items():
        merged[key] = value
    return merged
