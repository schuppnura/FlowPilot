"""
Request size limiting middleware for FastAPI services.

Protects against large payload attacks that could exhaust memory or resources.
"""

from __future__ import annotations

import os
from typing import Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class RequestSizeLimiterMiddleware(BaseHTTPMiddleware):
    """
    Middleware to limit request body size.
    
    Protects against resource exhaustion attacks via large payloads.
    """

    def __init__(self, app, max_size: int = 1_048_576):  # 1 MB default
        """
        Initialize the request size limiter.
        
        Args:
            app: FastAPI application
            max_size: Maximum request body size in bytes (default: 1MB)
        """
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Check request size before processing."""
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


def get_max_request_size() -> int:
    """
    Get maximum request size from environment variable.
    
    Returns:
        Maximum request size in bytes (default: 1MB)
    """
    max_size_mb = int(os.environ.get("MAX_REQUEST_SIZE_MB", "1"))
    return max_size_mb * 1_048_576
