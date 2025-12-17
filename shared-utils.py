from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urljoin

import requests


def validate_non_empty_string(value: Any, field_name: str) -> str:
    # Validate that a field is a non-empty string to fail fast, protect callers, and improve diagnostics.
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def parse_positive_int(value: str, variable_name: str) -> int:
    # Parse and validate a positive integer from env/CLI to prevent silent misconfiguration.
    try:
        parsed = int(value)
    except ValueError as exception:
        raise ValueError(f"Invalid {variable_name}: expected integer, got '{value}'.") from exception
    if parsed <= 0:
        raise ValueError(f"Invalid {variable_name}: expected > 0, got '{value}'.")
    return parsed


def parse_positive_float(raw_value: str, field_name: str) -> float:
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


def build_url(base_url: str, path: str) -> str:
    # Build a stable absolute URL from base URL + path to avoid double slashes and missing separators.
    base = base_url.rstrip("/") + "/"
    relative = path.lstrip("/")
    return urljoin(base, relative)


def truncate_text(value: Optional[str], max_length: int) -> str:
    # Truncate text for error messages to keep logs readable and avoid leaking large upstream payloads.
    if value is None:
        return ""
    stripped = value.strip()
    if len(stripped) <= max_length:
        return stripped
    return stripped[:max_length] + "…"


def parse_json_object(text: str, context: str) -> Dict[str, Any]:
    # Parse JSON response into an object
    # assumption: callers expect an object and want actionable errors.
    if not text or not text.strip():
        raise ValueError(f"Empty JSON response: {context}")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exception:
        raise ValueError(f"Invalid JSON response: {context} body={truncate_text(text, 800)}") from exception
    if not isinstance(parsed, dict):
        raise ValueError(f"JSON response must be an object: {context}")
    return parsed


def http_get_text(url: str, timeout_seconds: int, headers: Optional[Dict[str, str]]) -> Tuple[int, str]:
    # Perform HTTP GET and return (status, text)
    # side effect: network I/O and raises on transport errors.
    try:
        response = requests.get(url, headers=headers or {}, timeout=int(timeout_seconds))
    except requests.RequestException as exception:
        raise ValueError(f"HTTP GET failed: url={url}") from exception
    return int(response.status_code), str(response.text)


def http_get_json(url: str, timeout_seconds: int, headers: Optional[Dict[str, str]]) -> Dict[str, Any]:
    # Perform HTTP GET expecting JSON object
    # how: call http_get_text then parse
    # side effect: network I/O.
    status_code, body_text = http_get_text(url=url, timeout_seconds=timeout_seconds, headers=headers)
    if status_code < 200 or status_code >= 300:
        raise ValueError(f"HTTP GET non-2xx: url={url} http={status_code} body={truncate_text(body_text, 800)}")
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

def build_timeouts(connect_seconds: float = 5.0, read_seconds: float = 30.0) -> tuple[float, float]:
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
