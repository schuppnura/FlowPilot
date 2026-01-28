# flowpilot-services/shared-libraries/profile.py
#
# Profile module for accessing Keycloak user profile data.
#
# This module provides a unified interface to Keycloak for retrieving user profile
# information using service-to-service authentication (client credentials flow).
# All functions take a user sub (subject ID) as input and return normalized profile data.
#
# All functions use service tokens (client credentials) to access Keycloak admin API,
# not admin username/password. TLS verification is always enabled (no verify_tls parameter).

from __future__ import annotations

import os
import ssl
from typing import Any, Dict, List, Optional

import requests
import security
import utils
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# ============================================================================
# Configuration Constants
# ============================================================================

# Default Keycloak configuration for Docker environment
DEFAULT_KEYCLOAK_BASE_URL = "https://keycloak:8443"
DEFAULT_KEYCLOAK_REALM = "flowpilot"

# SSL/TLS configuration
CA_BUNDLE_PATH = "/app/ca-bundle.crt"

# Timeouts (in seconds)
KEYCLOAK_USER_REQUEST_TIMEOUT = 10
KEYCLOAK_USERS_LIST_TIMEOUT = 30

# HTTP connection pool settings
HTTP_POOL_CONNECTIONS = 10
HTTP_POOL_MAXSIZE = 10

# ============================================================================
# Module State
# ============================================================================

# Cache for service token to avoid repeated token requests
_service_token: str | None = None


def _get_service_token() -> str | None:
    # Get service token for Keycloak admin API access.
    global _service_token
    token = security.get_service_token()
    _service_token = token
    return token


def _get_keycloak_config() -> dict[str, str]:
    # Get Keycloak configuration from environment variables.
    # Default to internal Docker hostname for container-to-container communication
    base_url = os.environ.get("KEYCLOAK_BASE_URL", DEFAULT_KEYCLOAK_BASE_URL).strip()
    realm = os.environ.get("KEYCLOAK_REALM", DEFAULT_KEYCLOAK_REALM).strip()

    if not base_url:
        raise ValueError("KEYCLOAK_BASE_URL environment variable is required")

    return {
        "base_url": base_url.rstrip("/"),
        "realm": realm,
    }


def _fetch_user_by_id(user_sub: str) -> dict[str, Any] | None:
    # Fetch user data from Keycloak admin API by user sub.
    #
    # Returns None if user not found.
    # Raises RuntimeError if service token unavailable or request fails.
    token = _get_service_token()
    if not token:
        raise RuntimeError(
            "Service token not available - check KEYCLOAK_TOKEN_URL, AGENT_CLIENT_ID, AGENT_CLIENT_SECRET"
        )

    config = _get_keycloak_config()
    user_url = f"{config['base_url']}/admin/realms/{config['realm']}/users/{user_sub}"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        # TLS verification: enabled by default, can be disabled via env var for local debugging only
        verify_tls = os.environ.get("VERIFY_TLS", "true").lower() == "true"
        # Use combined cert bundle if available, otherwise use True (system certs) or False
        if verify_tls:
            # Try to use combined cert bundle (certifi + mkcert CA) if it exists
            ca_bundle = CA_BUNDLE_PATH if os.path.exists(CA_BUNDLE_PATH) else True
            # For internal Docker communication, disable hostname verification
            # (certificate is valid, but issued for localhost, not container hostname)
            ssl_context = create_urllib3_context()
            if isinstance(ca_bundle, str):
                ssl_context.load_verify_locations(cafile=ca_bundle)
            # Disable hostname checking for internal Docker services
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_REQUIRED

            # Create a session with custom adapter that uses our SSL context
            session = requests.Session()
            adapter = HTTPAdapter()
            # Initialize poolmanager with our custom SSL context
            adapter.init_poolmanager(
                connections=HTTP_POOL_CONNECTIONS,
                maxsize=HTTP_POOL_MAXSIZE,
                ssl_context=ssl_context,
                assert_hostname=False,
            )
            session.mount("https://", adapter)
            response = session.get(
                user_url, headers=headers, timeout=KEYCLOAK_USER_REQUEST_TIMEOUT
            )
        else:
            # Use get_http_config() which includes timeout and verify settings
            response = requests.get(
                user_url,
                headers=headers,
                **utils.get_http_config(),
            )
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return None
        else:
            raise RuntimeError(
                f"Failed to fetch user {user_sub}: HTTP {response.status_code}: {response.text}"
            )
    except requests.RequestException as e:
        raise RuntimeError(f"Exception fetching user {user_sub}: {e}") from e


def _fetch_all_users() -> list[dict[str, Any]]:
    # Fetch all users from Keycloak admin API.
    #
    # Raises RuntimeError if service token unavailable or request fails.
    token = _get_service_token()
    if not token:
        raise RuntimeError(
            "Service token not available - check KEYCLOAK_TOKEN_URL, AGENT_CLIENT_ID, AGENT_CLIENT_SECRET"
        )

    config = _get_keycloak_config()
    users_url = f"{config['base_url']}/admin/realms/{config['realm']}/users"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        # TLS verification: enabled by default, can be disabled via env var for local debugging only
        verify_tls = os.environ.get("VERIFY_TLS", "true").lower() == "true"
        # Use combined cert bundle if available, otherwise use True (system certs) or False
        if verify_tls:
            # Try to use combined cert bundle (certifi + mkcert CA) if it exists
            ca_bundle = CA_BUNDLE_PATH if os.path.exists(CA_BUNDLE_PATH) else True
            # For internal Docker communication, disable hostname verification
            # (certificate is valid, but issued for localhost, not container hostname)
            ssl_context = create_urllib3_context()
            if isinstance(ca_bundle, str):
                ssl_context.load_verify_locations(cafile=ca_bundle)
            # Disable hostname checking for internal Docker services
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_REQUIRED

            # Create a session with custom adapter that uses our SSL context
            session = requests.Session()
            adapter = HTTPAdapter()
            # Initialize poolmanager with our custom SSL context
            adapter.init_poolmanager(
                connections=HTTP_POOL_CONNECTIONS,
                maxsize=HTTP_POOL_MAXSIZE,
                ssl_context=ssl_context,
                assert_hostname=False,
            )
            session.mount("https://", adapter)
            response = session.get(
                users_url, headers=headers, timeout=KEYCLOAK_USERS_LIST_TIMEOUT
            )
        else:
            # Use get_http_config() which includes timeout and verify settings
            response = requests.get(
                users_url,
                headers=headers,
                **utils.get_http_config(),
            )
        if response.status_code == 200:
            users = response.json()
            if isinstance(users, list):
                return users
            else:
                raise RuntimeError(f"Unexpected response format: {type(users)}")
        else:
            raise RuntimeError(
                f"Failed to fetch users: HTTP {response.status_code}: {response.text}"
            )
    except requests.RequestException as e:
        raise RuntimeError(f"Exception fetching users: {e}") from e


def _extract_attribute_value(
    attributes: dict[str, Any], attr_name: str, default: Any = None
) -> Any:
    # Extract attribute value from Keycloak user attributes.
    #
    # Keycloak returns attributes as lists, so we take the first element if it's a list.
    if not attributes or not isinstance(attributes, dict):
        return default

    attr_value = attributes.get(attr_name)
    if isinstance(attr_value, list) and len(attr_value) > 0:
        return attr_value[0]
    elif attr_value:
        return attr_value

    return default


def fetch_username(user_sub: str) -> str | None:
    # Fetch username for a user by their sub (subject ID).
    #
    # Args:
    #     user_sub: User subject ID (Keycloak user ID)
    #
    # Returns:
    #     Username string, or None if user not found
    user_data = _fetch_user_by_id(user_sub)
    if not user_data:
        return None

    return user_data.get("username")


def fetch_persona(user_sub: str) -> list[str]:
    # Fetch persona(s) for a user by their sub (subject ID).
    #
    # Users can have multiple personas, so this returns a list.
    #
    # Args:
    #     user_sub: User subject ID (Keycloak user ID)
    #
    # Returns:
    #     List of persona strings (e.g., ["traveler", "travel-agent"]), empty list if none
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


def fetch_attributes(user_sub: str) -> dict[str, Any]:
    # Fetch user attributes from Keycloak including personas and autobook settings.
    #
    # This is a unified function that fetches all user attributes in a single call,
    # replacing the need to call both fetch_persona() and get_autobook_settings().
    #
    # Args:
    #     user_sub: User subject ID (Keycloak user ID)
    #
    # Returns:
    #     Dictionary with user attributes:
    #     - persona: List[str] - List of persona strings (e.g., ["traveler", "travel-agent"])
    #     - consent: string (e.g., "Yes", "No")
    #     - autobook_price: string (e.g., "1500")
    #     - autobook_leadtime: string (e.g., "7")
    #     - autobook_risklevel: string (e.g., "2")
    #     Returns empty dict if user not found
    user_data = _fetch_user_by_id(user_sub)
    if not user_data:
        return {}

    attributes = user_data.get("attributes") or {}

    # Extract personas (multi-valued)
    persona_attr = attributes.get("persona")
    personas: list[str] = []
    if persona_attr:
        if isinstance(persona_attr, list):
            personas = [str(p).strip() for p in persona_attr if p and str(p).strip()]
        elif isinstance(persona_attr, str):
            persona_str = persona_attr.strip()
            if persona_str:
                personas = [persona_str]

    # Extract autobook settings
    return {
        "persona": personas,
        "consent": _extract_attribute_value(
            attributes, "consent", ""
        ),
        "autobook_price": _extract_attribute_value(attributes, "autobook_price", ""),
        "autobook_leadtime": _extract_attribute_value(
            attributes, "autobook_leadtime", ""
        ),
        "autobook_risklevel": _extract_attribute_value(
            attributes, "autobook_risklevel", ""
        ),
    }


def list_users_by_persona(persona: str) -> list[dict[str, Any]]:
    # List all users who have a specific persona.
    #
    # Args:
    #     persona: Persona value to filter by (e.g., "travel-agent")
    #
    # Returns:
    #     List of user dictionaries with:
    #     - id: User sub (subject ID)
    #     - username: Username
    #     - email: Email (if available)
    all_users = _fetch_all_users()
    matching_users: list[dict[str, Any]] = []

    for user in all_users:
        user_id = user.get("id")
        username = user.get("username")
        email = user.get("email")

        if not user_id or not username:
            continue

        # Get personas for this user
        user_personas = fetch_persona(user_id)

        # Check if the requested persona is in the user's personas
        if persona in user_personas:
            matching_users.append(
                {
                    "id": user_id,
                    "username": username,
                    "email": email or "",
                }
            )

    return matching_users


def set_user_attributes(user_sub: str, attributes: dict[str, Any]) -> bool:
    # Set user attributes in Keycloak via admin API.
    #
    # Args:
    #     user_sub: User subject ID (Keycloak user ID)
    #     attributes: Dictionary of attributes to set
    #
    # Returns:
    #     True if successful
    #
    # Raises:
    #     RuntimeError: If service token unavailable or request fails
    token = _get_service_token()
    if not token:
        raise RuntimeError(
            "Service token not available - check KEYCLOAK_TOKEN_URL, AGENT_CLIENT_ID, AGENT_CLIENT_SECRET"
        )

    config = _get_keycloak_config()
    user_url = f"{config['base_url']}/admin/realms/{config['realm']}/users/{user_sub}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        # Keycloak expects attributes as lists
        keycloak_attributes = {}
        for key, value in attributes.items():
            if isinstance(value, list):
                keycloak_attributes[key] = value
            else:
                keycloak_attributes[key] = [str(value)]

        # Update user attributes via PUT request
        payload = {"attributes": keycloak_attributes}

        # TLS verification: enabled by default, can be disabled via env var for local debugging only
        verify_tls = os.environ.get("VERIFY_TLS", "true").lower() == "true"
        if verify_tls:
            # Try to use combined cert bundle (certifi + mkcert CA) if it exists
            ca_bundle = CA_BUNDLE_PATH if os.path.exists(CA_BUNDLE_PATH) else True
            # For internal Docker communication, disable hostname verification
            ssl_context = create_urllib3_context()
            if isinstance(ca_bundle, str):
                ssl_context.load_verify_locations(cafile=ca_bundle)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_REQUIRED

            # Create a session with custom adapter
            session = requests.Session()
            adapter = HTTPAdapter()
            adapter.init_poolmanager(
                connections=HTTP_POOL_CONNECTIONS,
                maxsize=HTTP_POOL_MAXSIZE,
                ssl_context=ssl_context,
                assert_hostname=False,
            )
            session.mount("https://", adapter)
            response = session.put(
                user_url,
                headers=headers,
                json=payload,
                timeout=KEYCLOAK_USER_REQUEST_TIMEOUT,
            )
        else:
            response = requests.put(
                user_url,
                headers=headers,
                json=payload,
                **utils.get_http_config(),
            )

        if response.status_code in [200, 204]:
            return True
        else:
            raise RuntimeError(
                f"Failed to set attributes for user {user_sub}: HTTP {response.status_code}: {response.text}"
            )
    except requests.RequestException as e:
        raise RuntimeError(f"Exception setting attributes for user {user_sub}: {e}") from e
