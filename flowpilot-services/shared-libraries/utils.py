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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests


def read_env_string(name: str, default_value: Optional[str] = None) -> str:
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


def read_env_int(name: str, default_value: Optional[int] = None) -> int:
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


def read_env_float(name: str, default_value: Optional[float] = None) -> float:
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


def read_env_bool(name: str, default_value: Optional[bool] = None) -> bool:
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
    raise ValueError(f"Invalid boolean value for {name}: {value} (expected true/false/yes/no/1/0)")


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


def coerce_dict(value: Any, field_name: Optional[str] = None) -> dict[str, Any]:
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


def coerce_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    # Convert a value to a float, returning default if conversion fails or value is None.
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def coerce_str(value: Any, default: Optional[str] = None) -> Optional[str]:
    # Convert a value to a string, returning default if value is None or empty.
    if value is None:
        return default
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else default
    # Convert non-string types to string
    return str(value)


def normalize_departure_date(date_value: Any) -> Optional[str]:
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


def coerce_timestamp() -> str:
    # Provide a stable UTC timestamp string for created_at and comparisons, avoiding timezone ambiguity.
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def coerce_utc(value: Optional[str]) -> Optional[datetime]:
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


def truncate_text(value: Optional[str], max_length: int) -> str:
    # Truncate text for error messages to keep logs readable and avoid leaking large upstream payloads.
    if value is None:
        return ""
    stripped = value.strip()
    if len(stripped) <= max_length:
        return stripped
    return stripped[:max_length] + "…"


def require_non_empty_list(value: Any, field_name: str) -> List[str]:
    # Validate scope arrays as non-empty lists of non-empty strings to prevent unsafe or ambiguous permissions.
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list of strings")

    normalized: List[str] = []
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


def require_optional_string(value: Any, field_name: str) -> Optional[str]:
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


def parse_json_object(text: str, context: str) -> Dict[str, Any]:
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
    url: str, timeout_seconds: int, headers: Optional[Dict[str, str]]
) -> Tuple[int, str]:
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
    url: str, timeout_seconds: int, headers: Optional[Dict[str, str]]
) -> Dict[str, Any]:
    # Perform HTTP GET expecting JSON object
    # how: call http_get_text then parse
    # side effect: network I/O.
    status_code, body_text = http_get_text(
        url=url, timeout_seconds=timeout_seconds, headers=headers
    )
    if status_code < 200 or status_code >= 300:
        raise ValueError(
            f"HTTP GET non-2xx: url={url} http={status_code} body={truncate_text(body_text, 800)}"
        )
    return parse_json_object(body_text, f"GET {url}")


def http_post_json(url: str, payload: dict, timeouts: tuple[float, float]) -> dict:
    # POST JSON and return JSON
    # why: centralize outbound HTTP with consistent timeouts and errors
    # assumptions: endpoint returns JSON on success
    # side effects: network I/O.
    if url.strip() == "":
        raise ValueError("url must be non-empty")
    if timeouts is None:
        raise ValueError("timeouts must be provided")
    if len(timeouts) != 2:
        raise ValueError(f"timeouts must be a (connect, read) tuple, got {timeouts}")

    response = requests.post(url, json=payload, timeout=timeouts)
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(
            f"HTTP POST non-2xx: url={url} http={response.status_code} body={response.text}"
        )

    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"HTTP POST invalid JSON response: url={url} http={response.status_code} body={response.text}"
        ) from exc


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
        with open(file_path, "r", encoding="utf-8") as handle:
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
