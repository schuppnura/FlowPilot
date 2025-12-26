# flowpilot-services/shared-libraries/profile.py
"""
Profile module for accessing Keycloak user profile data.

This module provides a unified interface to Keycloak for retrieving user profile
information using service-to-service authentication (client credentials flow).
All functions take a user sub (subject ID) as input and return normalized profile data.

All functions use service tokens (client credentials) to access Keycloak admin API,
not admin username/password. TLS verification is always enabled (no verify_tls parameter).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

import security

# Cache for service token to avoid repeated token requests
_service_token: Optional[str] = None


def _get_service_token() -> Optional[str]:
    """Get service token for Keycloak admin API access."""
    global _service_token
    token = security.get_service_token()
    _service_token = token
    return token


def _get_keycloak_config() -> Dict[str, str]:
    """Get Keycloak configuration from environment variables."""
    base_url = os.environ.get("KEYCLOAK_BASE_URL", "").strip()
    realm = os.environ.get("KEYCLOAK_REALM", "flowpilot").strip()
    
    if not base_url:
        raise ValueError("KEYCLOAK_BASE_URL environment variable is required")
    
    return {
        "base_url": base_url.rstrip("/"),
        "realm": realm,
    }


def _fetch_user_by_id(user_sub: str) -> Optional[Dict[str, Any]]:
    """
    Fetch user data from Keycloak admin API by user sub.
    
    Returns None if user not found or request fails.
    """
    token = _get_service_token()
    if not token:
        print("[profile] Service token not available - check KEYCLOAK_TOKEN_URL, AGENT_CLIENT_ID, AGENT_CLIENT_SECRET", flush=True)
        return None
    
    config = _get_keycloak_config()
    user_url = f"{config['base_url']}/admin/realms/{config['realm']}/users/{user_sub}"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        # TLS verification: enabled by default, can be disabled via env var for local debugging only
        verify_tls = os.environ.get("VERIFY_TLS", "true").lower() == "true"
        response = requests.get(user_url, headers=headers, timeout=10, verify=verify_tls)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            print(f"[profile] User not found: {user_sub}", flush=True)
            return None
        else:
            print(f"[profile] Failed to fetch user {user_sub}: HTTP {response.status_code}: {response.text}", flush=True)
            return None
    except Exception as e:
        print(f"[profile] Exception fetching user {user_sub}: {e}", flush=True)
        return None


def _fetch_all_users() -> List[Dict[str, Any]]:
    """
    Fetch all users from Keycloak admin API.
    
    Returns empty list if request fails.
    """
    token = _get_service_token()
    if not token:
        print("[profile] Service token not available - check KEYCLOAK_TOKEN_URL, AGENT_CLIENT_ID, AGENT_CLIENT_SECRET", flush=True)
        return []
    
    config = _get_keycloak_config()
    users_url = f"{config['base_url']}/admin/realms/{config['realm']}/users"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        # TLS verification: enabled by default, can be disabled via env var for local debugging only
        verify_tls = os.environ.get("VERIFY_TLS", "true").lower() == "true"
        response = requests.get(users_url, headers=headers, timeout=30, verify=verify_tls)
        if response.status_code == 200:
            users = response.json()
            if isinstance(users, list):
                return users
            else:
                print(f"[profile] Unexpected response format: {type(users)}", flush=True)
                return []
        else:
            print(f"[profile] Failed to fetch users: HTTP {response.status_code}: {response.text}", flush=True)
            return []
    except Exception as e:
        print(f"[profile] Exception fetching users: {e}", flush=True)
        return []


def _extract_attribute_value(attributes: Dict[str, Any], attr_name: str, default: Any = None) -> Any:
    """
    Extract attribute value from Keycloak user attributes.
    
    Keycloak returns attributes as lists, so we take the first element if it's a list.
    """
    if not attributes or not isinstance(attributes, dict):
        return default
    
    attr_value = attributes.get(attr_name)
    if isinstance(attr_value, list) and len(attr_value) > 0:
        return attr_value[0]
    elif attr_value:
        return attr_value
    
    return default


def get_username(user_sub: str) -> Optional[str]:
    """
    Get username for a user by their sub (subject ID).
    
    Args:
        user_sub: User subject ID (Keycloak user ID)
        
    Returns:
        Username string, or None if user not found
    """
    user_data = _fetch_user_by_id(user_sub)
    if not user_data:
        return None
    
    return user_data.get("username")


def get_persona(user_sub: str) -> List[str]:
    """
    Get persona(s) for a user by their sub (subject ID).
    
    Users can have multiple personas, so this returns a list.
    
    Args:
        user_sub: User subject ID (Keycloak user ID)
        
    Returns:
        List of persona strings (e.g., ["traveler", "travel-agent"]), empty list if none
    """
    user_data = _fetch_user_by_id(user_sub)
    if not user_data:
        return []
    
    attributes = user_data.get("attributes") or {}
    # Don't use _extract_attribute_value for persona since it's multi-valued
    # Access the attribute directly to get the full list
    persona_attr = attributes.get("persona")
    
    if not persona_attr:
        return []
    
    # Keycloak returns attributes as lists, so persona_attr is typically a list
    if isinstance(persona_attr, list):
        # Filter out empty strings and return all personas
        return [str(p).strip() for p in persona_attr if p and str(p).strip()]
    elif isinstance(persona_attr, str):
        # Single string value (shouldn't happen in Keycloak, but handle it)
        persona_str = persona_attr.strip()
        return [persona_str] if persona_str else []
    
    return []


def get_autobook_settings(user_sub: str) -> Dict[str, Any]:
    """
    Get autobook settings for a user by their sub (subject ID).
    
    Args:
        user_sub: User subject ID (Keycloak user ID)
        
    Returns:
        Dictionary with autobook settings:
        - autobook_consent: string (e.g., "Yes", "No")
        - autobook_price: string (e.g., "1500")
        - autobook_leadtime: string (e.g., "7")
        - autobook_risklevel: string (e.g., "2")
        Returns empty dict if user not found or settings missing
    """
    user_data = _fetch_user_by_id(user_sub)
    if not user_data:
        return {}
    
    attributes = user_data.get("attributes") or {}
    
    return {
        "autobook_consent": _extract_attribute_value(attributes, "autobook_consent", ""),
        "autobook_price": _extract_attribute_value(attributes, "autobook_price", ""),
        "autobook_leadtime": _extract_attribute_value(attributes, "autobook_leadtime", ""),
        "autobook_risklevel": _extract_attribute_value(attributes, "autobook_risklevel", ""),
    }


def list_users_by_persona(persona: str) -> List[Dict[str, Any]]:
    """
    List all users who have a specific persona.
    
    Args:
        persona: Persona value to filter by (e.g., "travel-agent")
        
    Returns:
        List of user dictionaries with:
        - id: User sub (subject ID)
        - username: Username
        - email: Email (if available)
    """
    all_users = _fetch_all_users()
    matching_users: List[Dict[str, Any]] = []
    
    for user in all_users:
        user_id = user.get("id")
        username = user.get("username")
        email = user.get("email")
        
        if not user_id or not username:
            continue
        
        # Get personas for this user
        user_personas = get_persona(user_id)
        
        # Check if the requested persona is in the user's personas
        if persona in user_personas:
            matching_users.append({
                "id": user_id,
                "username": username,
                "email": email or "",
            })
    
    return matching_users

