# Shared Input Sanitization and Security Middleware for FlowPilot Services
#
# Comprehensive input validation and injection attack prevention middleware used
# across all FlowPilot services to protect against security vulnerabilities.
#
# Input sanitization and security middleware for FastAPI services.
#
# Protects against:
# - Large payload attacks (request body size limits)
# - SQL injection attempts (dangerous pattern detection)
# - Excessive string lengths (per-field character limits)
# - Resource exhaustion (connection limits)

from __future__ import annotations

import os
import re
from typing import Any, Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

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
    r"\.\.\\",                      # Parent directory (Windows)
    r"%2e%2e/",                      # URL encoded ..
    r"%2e%2e\\",                    # URL encoded .. (Windows)
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
