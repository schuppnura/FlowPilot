# Shared Caching Layer for FlowPilot Services
#
# Provides transparent caching for HTTP calls with:
# - TTL-based expiration
# - Write-through invalidation
# - Cache coherency guarantees
# - Minimal code changes (drop-in replacement for http_* functions)
#
# Design principles:
# - Cache reads only (GET requests)
# - Write-through invalidation on POST/PUT/DELETE
# - Conservative TTLs to prevent stale data
# - Fail-open: cache errors don't break the system

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional
import os

# Try to import Redis, fall back to in-memory cache if not available
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

import api_logging


# ============================================================================
# Configuration
# ============================================================================

# Cache TTLs (time-to-live in seconds)
CACHE_TTL_PERSONA = int(os.getenv("CACHE_TTL_PERSONA", "300"))  # 5 minutes
CACHE_TTL_DELEGATION = int(os.getenv("CACHE_TTL_DELEGATION", "180"))  # 3 minutes
CACHE_TTL_OPA_DECISION = int(os.getenv("CACHE_TTL_OPA_DECISION", "60"))  # 1 minute
CACHE_TTL_DEFAULT = int(os.getenv("CACHE_TTL_DEFAULT", "300"))  # 5 minutes

# Cache enable/disable
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "false").lower() in ("true", "yes", "1")

# Redis connection (optional - falls back to in-memory if not configured)
REDIS_URL = os.getenv("REDIS_URL", None)  # e.g., "redis://localhost:6379/0"


# ============================================================================
# Cache Implementation
# ============================================================================

class CacheBackend:
    """Abstract cache backend interface"""
    
    def get(self, key: str) -> Optional[str]:
        """Get value from cache, returns None if not found or expired"""
        raise NotImplementedError
    
    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Set value in cache with TTL"""
        raise NotImplementedError
    
    def delete(self, key: str) -> None:
        """Delete specific key from cache"""
        raise NotImplementedError
    
    def delete_pattern(self, pattern: str) -> None:
        """Delete all keys matching pattern (for invalidation)"""
        raise NotImplementedError


class InMemoryCache(CacheBackend):
    """Simple in-memory cache with TTL (for development/testing)"""
    
    def __init__(self):
        self._cache: dict[str, tuple[str, float]] = {}  # key -> (value, expiry_time)
    
    def get(self, key: str) -> Optional[str]:
        if key not in self._cache:
            return None
        
        value, expiry = self._cache[key]
        if time.time() > expiry:
            del self._cache[key]
            return None
        
        return value
    
    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        expiry = time.time() + ttl_seconds
        self._cache[key] = (value, expiry)
    
    def delete(self, key: str) -> None:
        self._cache.pop(key, None)
    
    def delete_pattern(self, pattern: str) -> None:
        # Simple pattern matching (supports * wildcard)
        pattern_prefix = pattern.rstrip("*")
        keys_to_delete = [k for k in self._cache if k.startswith(pattern_prefix)]
        for key in keys_to_delete:
            del self._cache[key]


class RedisCache(CacheBackend):
    """Redis-backed cache (for production)"""
    
    def __init__(self, url: str):
        self._client = redis.from_url(url, decode_responses=True)
    
    def get(self, key: str) -> Optional[str]:
        try:
            return self._client.get(key)
        except redis.RedisError as e:
            # Fail open - log error but don't break the request
            api_logging.log_api_response(
                method="CACHE",
                path="GET",
                status_code=0,
                error=f"Redis GET error: {e}",
            )
            return None
    
    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        try:
            self._client.setex(key, ttl_seconds, value)
        except redis.RedisError as e:
            # Fail open - log error but don't break the request
            api_logging.log_api_response(
                method="CACHE",
                path="SET",
                status_code=0,
                error=f"Redis SET error: {e}",
            )
    
    def delete(self, key: str) -> None:
        try:
            self._client.delete(key)
        except redis.RedisError as e:
            api_logging.log_api_response(
                method="CACHE",
                path="DELETE",
                status_code=0,
                error=f"Redis DELETE error: {e}",
            )
    
    def delete_pattern(self, pattern: str) -> None:
        try:
            # Use SCAN instead of KEYS to avoid blocking Redis
            # SCAN is O(N) but non-blocking and cursor-based
            cursor = 0
            keys_to_delete = []
            
            # Iterate through all keys matching pattern using SCAN
            while True:
                cursor, keys = self._client.scan(cursor, match=pattern, count=100)
                if keys:
                    keys_to_delete.extend(keys)
                if cursor == 0:
                    break
            
            # Delete all matched keys in batches
            if keys_to_delete:
                # Delete in batches of 100 to avoid large DEL commands
                batch_size = 100
                for i in range(0, len(keys_to_delete), batch_size):
                    batch = keys_to_delete[i:i + batch_size]
                    self._client.delete(*batch)
        except redis.RedisError as e:
            api_logging.log_api_response(
                method="CACHE",
                path="DELETE_PATTERN",
                status_code=0,
                error=f"Redis DELETE_PATTERN error: {e}",
            )


# Initialize global cache backend
def _init_cache() -> CacheBackend:
    if not CACHE_ENABLED:
        return InMemoryCache()  # Dummy cache (always returns None)
    
    if REDIS_URL and REDIS_AVAILABLE:
        try:
            return RedisCache(REDIS_URL)
        except Exception as e:
            print(f"WARNING: Failed to connect to Redis at {REDIS_URL}: {e}", flush=True)
            print("WARNING: Falling back to in-memory cache", flush=True)
            return InMemoryCache()
    
    if CACHE_ENABLED:
        print("WARNING: Cache enabled but Redis not available. Using in-memory cache.", flush=True)
    
    return InMemoryCache()


_cache_backend = _init_cache()


# ============================================================================
# Cache Key Generation
# ============================================================================

def _generate_cache_key(url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> str:
    """Generate deterministic cache key from request parameters
    
    Includes:
    - Resource type prefix (for pattern-based invalidation)
    - URL hash
    - Query parameters (sorted for consistency)
    - Authorization header (to prevent cross-user cache pollution)
    """
    # Determine resource type from URL for cache invalidation
    resource_type = "unknown"
    url_lower = url.lower()
    if "persona" in url_lower:
        resource_type = "persona"
    elif "delegation" in url_lower:
        resource_type = "delegation"
    elif "workflow" in url_lower:
        resource_type = "workflow"
    elif "evaluate" in url_lower or "opa" in url_lower:
        resource_type = "authz"
    
    key_parts = [url]
    
    # Add sorted params
    if params:
        sorted_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        key_parts.append(sorted_params)
    
    # Add auth header (if present) to prevent cross-user cache hits
    if headers and "Authorization" in headers:
        # Hash the token to keep cache key short
        token_hash = hashlib.sha256(headers["Authorization"].encode()).hexdigest()[:16]
        key_parts.append(token_hash)
    
    # Generate stable key with resource type prefix for pattern matching
    key_string = "|".join(key_parts)
    content_hash = hashlib.sha256(key_string.encode()).hexdigest()
    return f"flowpilot:{resource_type}:{content_hash}"


def _determine_ttl(url: str) -> int:
    """Determine appropriate TTL based on URL/endpoint"""
    if "personas" in url or "persona" in url:
        return CACHE_TTL_PERSONA
    elif "delegations" in url or "delegation" in url:
        return CACHE_TTL_DELEGATION
    elif "opa" in url or "evaluate" in url:
        return CACHE_TTL_OPA_DECISION
    else:
        return CACHE_TTL_DEFAULT


# ============================================================================
# Cached HTTP Functions (drop-in replacements)
# ============================================================================

def http_get_json_with_cache(
    url: str,
    params: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
    headers: dict[str, str] | None = None,
    http_get_impl = None,  # The actual implementation function from utils
) -> dict[str, Any]:
    """Cached wrapper for http_get_json
    
    This is called automatically by utils.http_get_json() when cache module is available.
    You don't need to call this directly - just use utils.http_get_json() as normal.
    
    Cache behavior:
    - Cache key includes URL, params, and auth token hash
    - TTL determined by endpoint type (persona/delegation/OPA)
    - Cache misses fall through to actual HTTP call
    - Errors in cache layer don't break requests (fail-open)
    """
    if not CACHE_ENABLED or http_get_impl is None:
        # Cache disabled or no implementation provided - pass through
        return http_get_impl(url, params=params, timeout_seconds=timeout_seconds, headers=headers)
    
    # Generate cache key
    cache_key = _generate_cache_key(url, params, headers)
    
    # Try cache first
    try:
        cached_value = _cache_backend.get(cache_key)
        if cached_value is not None:
            # Cache hit - log and return
            api_logging.log_api_response(
                method="CACHE",
                path=url,
                status_code=200,
                response_body={"cache": "HIT"},
            )
            return json.loads(cached_value)
    except Exception as e:
        # Cache error - log but continue with HTTP call
        api_logging.log_api_response(
            method="CACHE",
            path=url,
            status_code=0,
            error=f"Cache GET error: {e}",
        )
    
    # Cache miss - make actual HTTP call
    response = http_get_impl(url, params=params, timeout_seconds=timeout_seconds, headers=headers)
    
    # Store in cache
    try:
        ttl = _determine_ttl(url)
        _cache_backend.set(cache_key, json.dumps(response), ttl)
    except Exception as e:
        # Cache error - log but don't fail the request
        api_logging.log_api_response(
            method="CACHE",
            path=url,
            status_code=0,
            error=f"Cache SET error: {e}",
        )
    
    return response


def invalidate_cache_for_resource(resource_type: str, resource_id: Optional[str] = None) -> None:
    """Invalidate cache entries for a specific resource type
    
    Call this after POST/PUT/DELETE operations to maintain cache coherency.
    
    Usage:
        # After creating/updating a delegation
        cache.invalidate_cache_for_resource("delegation", delegation_id)
        
        # After updating a persona
        cache.invalidate_cache_for_resource("persona", user_sub)
        
        # After any authz-related change (nuclear option)
        cache.invalidate_cache_for_resource("authz")
    
    Args:
        resource_type: Type of resource ("persona", "delegation", "authz", etc.)
        resource_id: Optional specific resource ID (if None, invalidates all of that type)
    """
    if not CACHE_ENABLED:
        return
    
    try:
        if resource_id:
            # Invalidate specific resource (would need more sophisticated key tracking)
            # For now, invalidate entire resource type
            pattern = f"flowpilot:*{resource_type}*"
        else:
            # Invalidate entire resource type
            pattern = f"flowpilot:*{resource_type}*"
        
        _cache_backend.delete_pattern(pattern)
        
        api_logging.log_api_response(
            method="CACHE",
            path="INVALIDATE",
            status_code=200,
            response_body={"resource_type": resource_type, "resource_id": resource_id},
        )
    except Exception as e:
        api_logging.log_api_response(
            method="CACHE",
            path="INVALIDATE",
            status_code=0,
            error=f"Cache invalidation error: {e}",
        )


# ============================================================================
# Cache Statistics (for monitoring)
# ============================================================================

def get_cache_stats() -> dict[str, Any]:
    """Get cache statistics for monitoring
    
    Returns:
        Dict with cache configuration and status
    """
    return {
        "enabled": CACHE_ENABLED,
        "backend": "redis" if isinstance(_cache_backend, RedisCache) else "memory",
        "redis_url": REDIS_URL if REDIS_URL else None,
        "ttls": {
            "persona": CACHE_TTL_PERSONA,
            "delegation": CACHE_TTL_DELEGATION,
            "opa_decision": CACHE_TTL_OPA_DECISION,
            "default": CACHE_TTL_DEFAULT,
        },
    }
