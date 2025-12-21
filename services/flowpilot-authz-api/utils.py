"""
Utility functions for FlowPilot AuthZ API.
"""
from __future__ import annotations

from typing import Any


def to_int(value: Any, default: int) -> int:
    """
    Safely convert a value to an integer with a fallback default.
    
    Args:
        value: The value to convert (can be string, int, or None)
        default: The default value to return if conversion fails
        
    Returns:
        The integer value, or default if conversion fails
    """
    try:
        return int(value) if value else default
    except (ValueError, TypeError):
        return default

