# Core authorization logic for FlowPilot AuthZ API using OPA.
#
# Design goals
# - Keep policy evaluation simple: call a plain OPA server (HTTP) running in "server mode".
# - Keep the AuthZ API responsible for:
#   - authenticating callers (via shared security.py)
#   - shaping input for the Rego policy
#   - mapping OPA outputs into the OpenAPI response schema
#   - loading policy manifests to determine required attributes
#
# Assumptions
# - An OPA server is reachable at OPA_URL (default: http://opa:8181).
# - Policy configuration loaded from manifest (POLICY_NAME, POLICY_MANIFEST_DIR).
# - Policy rules used:
#   - data.<package>.allow  -> boolean
#   - data.<package>.reasons -> set/list of strings (optional)

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Required imports for API logging and security
import requests
import security
from policy_manifest import PolicyAttribute, PolicyManifest, PolicyRegistry
from utils import (
    build_timeouts,
    coerce_bool,
    coerce_dict,
    coerce_float,
    coerce_int,
    get_http_config,
    http_get_json,
    http_post_json,
    normalize_departure_date,
    read_env_string,
)

# ============================================================================
# Configuration Constants
# ============================================================================

# Allowed actions will be derived from policy manifests
# See _build_policy_registry() which collects all allowed-actions from persona_config
ALLOWED_ACTIONS: set[str] = set()  # Populated after registry is built


@dataclass(frozen=True)
class OpaConfig:
    base_url: str
    package: str
    policy_manifest: PolicyManifest
    allow_rule: str = "allow"
    reason_rule: str = "reasons"
    connect_timeout_seconds: float = 3.0
    read_timeout_seconds: float = 10.0


class OpaClient:
    def __init__(self, config: OpaConfig) -> None:
        self._config = config

    def evaluate_allow(self, input_document: dict[str, Any]) -> bool:
        result = self._post_data(
            path=f"{self._config.package}/{self._config.allow_rule}",
            input_document=input_document,
        )
        # OPA data API: {"result": <value>}
        return bool(result.get("result", False))

    def evaluate_reasons(self, input_document: dict[str, Any]) -> list[str]:
        result = self._post_data(
            path=f"{self._config.package}/{self._config.reason_rule}",
            input_document=input_document,
        )
        reasons = result.get("result", [])
        if reasons is None:
            return []
        if isinstance(reasons, list):
            return [str(item) for item in reasons]
        # Sets sometimes serialize as objects in some contexts; be defensive.
        if isinstance(reasons, dict):
            return [str(key) for key in reasons.keys()]
        return [str(reasons)]

    def _post_data(self, path: str, input_document: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._config.base_url.rstrip('/')}/v1/data/{path.lstrip('/')}"
        payload = {"input": input_document}
        timeouts = build_timeouts(
            connect_seconds=self._config.connect_timeout_seconds,
            read_seconds=self._config.read_timeout_seconds,
        )
        return http_post_json(url=url, payload=payload, timeouts=timeouts)


def _build_opa_client_for_policy(manifest: PolicyManifest) -> OpaClient:
    """Build OPA client for a specific policy manifest.
    
    Args:
        manifest: Policy manifest to use for OPA client
    
    Returns:
        OpaClient configured for the policy
    """
    config = OpaConfig(
        base_url=read_env_string("OPA_URL"),
        package=manifest.package,
        policy_manifest=manifest,
    )
    return OpaClient(config=config)


def _build_policy_registry() -> PolicyRegistry:
    """Build policy registry from environment configuration.
    
    Returns:
        PolicyRegistry with all loaded policies
    """
    manifest_dir = os.environ.get("POLICY_MANIFEST_DIR", "/policies")
    return PolicyRegistry(manifest_dir=manifest_dir)


# ============================================================================
# Module-Level Clients and Services
# ============================================================================

# Policy registry instance (initialized on module load)
_POLICY_REGISTRY = _build_policy_registry()

# Populate allowed actions from all loaded policies
ALLOWED_ACTIONS = _POLICY_REGISTRY.get_all_allowed_actions()
print(f"Allowed actions (from policy manifests): {', '.join(sorted(ALLOWED_ACTIONS))}", flush=True)

# Delegation API configuration (required environment variables)
_DELEGATION_API_BASE_URL = read_env_string("DELEGATION_API_BASE_URL")

# User Profile API configuration (required environment variables)
_PERSONA_API_BASE_URL = read_env_string("PERSONA_API_BASE_URL")


def normalize_attributes(
    attributes_dict: dict[str, Any],
    policy_attributes: list[PolicyAttribute],
    source_type: str,  # "persona" or "resource"
) -> dict[str, Any]:
    """Normalize attributes: apply defaults, validate required, and coerce types.
    
    Combines three operations into one atomic function:
    1. Apply defaults for missing attributes
    2. Validate all required attributes are present
    3. Coerce attribute values to manifest types
    
    Args:
        attributes_dict: Dictionary of attribute values (from persona or resource)
        policy_attributes: List of PolicyAttribute definitions from manifest
        source_type: Type of attributes being normalized ("persona" or "resource")
    
    Returns:
        Normalized dictionary with defaults applied, validated, and type-coerced
    
    Raises:
        ValueError: If required attributes are missing or type coercion fails
    """
    result = dict(attributes_dict)
    
    # Step 1: Apply defaults for missing attributes
    for attr in policy_attributes:
        if attr.name not in result or result[attr.name] is None:
            if attr.default is not None:
                result[attr.name] = attr.default
    
    # Step 2: Validate required attributes are present
    missing_required = []
    for attr in policy_attributes:
        if attr.required:
            if attr.name not in result or result[attr.name] is None:
                missing_required.append(attr.name)
    
    if missing_required:
        raise ValueError(
            f"Missing required {source_type} attributes: {', '.join(missing_required)}"
        )
    
    # Step 3: Coerce attribute values to manifest types
    for attr in policy_attributes:
        if attr.name in result:
            attr_value = result[attr.name]
            attr_type = attr.type
            
            # Coerce based on type
            if attr_type == "float":
                result[attr.name] = coerce_float(attr_value)
            elif attr_type == "integer":
                result[attr.name] = coerce_int(attr_value, 0)
            elif attr_type == "date":
                result[attr.name] = normalize_departure_date(attr_value)
            elif attr_type == "boolean":
                result[attr.name] = coerce_bool(attr_value, False)
            else:  # string or unknown - coerce to string if not None
                result[attr.name] = str(attr_value) if attr_value is not None else ""
    
    return result


@dataclass(frozen=True)
class EvaluateResult:
    decision: str  # "allow" | "deny"
    reason_codes: list[str]
    advice: list[dict[str, Any]]


# ============================================================================
# Fetch information from PIPs Helper Functions
# ============================================================================


def fetch_persona(persona_id: str) -> dict[str, Any]:
    # Fetch persona from persona-api.
    # Returns full persona object with policy-specific attributes.
    #
    # This function acts as a Policy Information Point (PIP) - it fetches data
    # needed for authorization decisions.
    #
    # IMPORTANT: persona-api pre-validates all persona attributes:
    # - Applies defaults from policy manifest for missing attributes
    # - Validates required attributes are present
    # - Coerces all attribute types (integer, float, boolean, date, string)
    # Therefore, authz-api can trust the data quality and use it directly.
    #
    # Args:
    #     persona_id: Persona ID
    #
    # Returns:
    #     Dictionary with persona attributes (schema depends on policy):
    #       - persona_id: string (UUID)
    #       - user_sub: string (owner of persona)
    #       - title: string (e.g., "traveler", "travel-agent")
    #       - scope: list of strings (actions)
    #       - valid_from: string (ISO 8601)
    #       - valid_till: string (ISO 8601)
    #       - status: string ("active", "inactive", etc.)
    #       - Plus policy-specific attributes (e.g., consent, autobook_price, etc.)
    #         All policy-specific attributes are already validated and type-coerced.
    #
    # Raises:
    #     RuntimeError: If service token is not available or API call fails

    # Get service token for persona API authentication
    service_token = security.get_service_token()
    if not service_token:
        raise RuntimeError("Service token not available - cannot fetch persona")

    headers = {"Authorization": f"Bearer {service_token.strip()}"}
    url = f"{_PERSONA_API_BASE_URL.rstrip('/')}/v1/personas/{persona_id}"

    try:
        return http_get_json(url=url, headers=headers)
    except RuntimeError as e:
        # If persona not found (404), return empty dict and fall back to defaults
        if "404" in str(e):
            return {}
        raise RuntimeError(f"Failed to fetch persona {persona_id}: {e}") from e


def fetch_persona_by_user_and_title(user_sub: str, persona_title: str) -> dict[str, Any]:
    # Fetch persona by user_sub and title from persona-api.
    # Returns the persona matching the title, regardless of status.
    #
    # IMPORTANT: This function is a Policy Information Point (PIP) - it fetches data
    # but does NOT make policy decisions. It returns the persona regardless of status
    # (active, suspended, expired, etc.) and lets OPA decide if the status is acceptable.
    #
    # Args:
    #     user_sub: User subject ID
    #     persona_title: Persona title (e.g., "traveler", "travel-agent")
    #
    # Returns:
    #     Dictionary with persona attributes (same as fetch_persona)
    #
    # Raises:
    #     RuntimeError: If service token is not available or API call fails

    # Get service token for persona API authentication
    service_token = security.get_service_token()
    if not service_token:
        raise RuntimeError("Service token not available - cannot fetch personas")

    headers = {"Authorization": f"Bearer {service_token.strip()}"}
    url = f"{_PERSONA_API_BASE_URL.rstrip('/')}/v1/users/{user_sub}/personas"

    try:
        # List all personas for the user (service account has access to all users' personas)
        personas_data = http_get_json(url=url, headers=headers)
        personas = personas_data.get("personas", [])

        # Find first persona with matching title (regardless of status)
        # Let OPA policy decide if the persona status is acceptable for the requested action
        for persona in personas:
            if persona.get("title") == persona_title:
                return persona

        # No matching persona found
        return {}
    except RuntimeError as e:
        # If no personas found (404), return empty dict
        if "404" in str(e):
            return {}
        raise RuntimeError(f"Failed to fetch personas for {user_sub}: {e}") from e


def compute_delegation_chain(
    *,
    owner_id: str,
    principal_id: str,
    workflow_id: str | None,
    requested_action: str,
) -> dict[str, Any]:
    # Fetch delegation chain data from delegation-api.
    # Returns delegation information for OPA to evaluate.
    #
    # This function acts as a Policy Information Point (PIP) - it fetches data
    # but does NOT make policy decisions. The OPA policy (PDP) decides whether
    # the available delegation permissions are sufficient.
    #
    # Args:
    #     owner_id: Owner ID (resource owner)
    #     principal_id: Principal ID (user attempting to act)
    #     workflow_id: Optional workflow ID to scope the delegation
    #     requested_action: Unused - kept for API compatibility, will be removed
    #
    # Returns:
    #     Dictionary with:
    #       - delegation_chain: list of user IDs in the chain
    #       - delegated_actions: list of actions available through delegation
    #
    #     Note: The 'valid' field previously returned by this function has been
    #     removed as it's redundant - OPA policy only checks delegated_actions.
    #
    # Raises:
    #     RuntimeError: If service token is not available

    # Get service token for delegation API authentication
    service_token = security.get_service_token()
    if not service_token:
        raise RuntimeError("Service token not available - cannot validate delegation")

    headers = {"Authorization": f"Bearer {service_token.strip()}"}
    url = f"{_DELEGATION_API_BASE_URL.rstrip('/')}/v1/delegations/validate"

    params: dict[str, str] = {
        "principal_id": owner_id,
        "delegate_id": principal_id,
    }
    if workflow_id:
        params["workflow_id"] = workflow_id

    try:
        data = http_get_json(url=url, params=params, headers=headers)
        delegation_chain = data.get("delegation_chain", [])
        delegated_actions = data.get("delegated_actions", [])

        # Return delegation data - let OPA decide if permissions are sufficient
        return {
            "delegation_chain": delegation_chain,
            "delegated_actions": delegated_actions,
        }
    except RuntimeError as e:
        raise RuntimeError(f"Failed to validate delegation chain: {e}") from e


# ============================================================================
# OPA Input Builder Functions
# ============================================================================

def build_opa_subject(authzen_request: dict[str, Any]) -> dict[str, Any]:
    """Build and validate OPA subject from AuthZEN request.
    
    Extracts subject information (agent or user) from the request.
    
    Args:
        authzen_request: AuthZEN-compliant request
    
    Returns:
        Subject dict with {type, id, persona}
    
    Raises:
        ValueError: If required subject fields are missing
    """
    request_subject = authzen_request.get("subject")
    if not request_subject or not isinstance(request_subject, dict):
        raise ValueError("Request must be AuthZEN compliant: subject is required")
    
    # Validate and extract subject.id
    subject_id = request_subject.get("id")
    if not subject_id or not isinstance(subject_id, str) or not subject_id.strip():
        raise ValueError("Request must be AuthZEN compliant: subject.id is required")
    subject_id = subject_id.strip()
    
    # Extract subject.type (optional, defaults to "user")
    subject_type = request_subject.get("type", "user")
    
    # Validate and extract subject.properties.persona (required for users, optional for agents)
    subject_properties = request_subject.get("properties", {})
    if not isinstance(subject_properties, dict):
        raise ValueError("Request must be AuthZEN compliant: subject.properties must be a dictionary")
    
    subject_persona = subject_properties.get("persona")
    
    # For agents/services, persona is optional (type is sufficient to identify them)
    # For users, persona is required
    if subject_type == "user":
        if not subject_persona:
            raise ValueError("Request must contain subject.properties.persona for user subjects")
        
        # Handle list format (take first element)
        if isinstance(subject_persona, list):
            if not subject_persona:
                raise ValueError("Request must contain non-empty subject.properties.persona")
            subject_persona = subject_persona[0]
        
        # Ensure persona is a non-empty string
        if not isinstance(subject_persona, str) or not subject_persona.strip():
            raise ValueError("Request must contain a string for subject.properties.persona")
        subject_persona = subject_persona.strip()
    
    result = {
        "type": subject_type,
        "id": subject_id,
    }
    
    # Only include persona if it's present (required for users, optional for agents)
    if subject_persona:
        result["persona"] = subject_persona
    
    return result


def build_opa_action(authzen_request: dict[str, Any]) -> dict[str, Any]:
    """Build and validate OPA action from AuthZEN request.
    
    Args:
        authzen_request: AuthZEN-compliant request
    
    Returns:
        Action dict with {name}
    
    Raises:
        ValueError: If action is missing or invalid
    """
    action_from_request = authzen_request.get("action", {})
    if not action_from_request or not isinstance(action_from_request, dict):
        raise ValueError("Request must be AuthZEN compliant: action is required")
    
    normalized_action = action_from_request.get("name")
    if not normalized_action or not isinstance(normalized_action, str) or not normalized_action.strip():
        raise ValueError("Request must be AuthZEN compliant: action.name is required")
    
    normalized_action = security.sanitize_string(normalized_action.strip(), 255)
    if normalized_action not in ALLOWED_ACTIONS:
        raise ValueError(
            f"Invalid action name: {normalized_action}. Allowed actions: {', '.join(sorted(ALLOWED_ACTIONS))}"
        )
    
    return {"name": normalized_action}


def build_opa_resource(
    authzen_request: dict[str, Any],
    persona_attributes: list[PolicyAttribute],
    resource_attributes: list[PolicyAttribute],
) -> dict[str, Any]:
    """Build OPA resource from AuthZEN request.
    
    Extracts resource, fetches owner's persona, and augments resource.properties.owner
    with policy-specific attributes (NOT metadata).
    
    Args:
        authzen_request: AuthZEN-compliant request
        persona_attributes: Policy-specific persona attributes from manifest
        resource_attributes: Resource attributes from manifest
    
    Returns:
        Resource dict with owner enriched with policy-specific persona attributes
    
    Raises:
        ValueError: If resource validation fails
        RuntimeError: If persona fetch fails
    """
    resource_from_request = authzen_request.get("resource") or {}
    properties_from_request = coerce_dict(
        resource_from_request.get("properties"), "resource.properties"
    )
    
    # Extract the original resource structure
    resource = dict(resource_from_request)
    enriched_properties = dict(properties_from_request)
    
    # Normalize resource attributes (default, validate, coerce)
    if resource_attributes:
        enriched_properties = normalize_attributes(
            enriched_properties, resource_attributes, "resource"
        )
    
    # Extract the original owner information
    owner_props = coerce_dict(
        enriched_properties.get("owner"), "resource.properties.owner"
    )
    owner_id = owner_props.get("id") if owner_props else None
    
    # Fetch owner's persona and augment resource.properties.owner
    if owner_id:
        owner_persona_id = owner_props.get("persona_id")
        owner_persona_title = owner_props.get("persona")
        workflow_id = enriched_properties.get("workflow_id") or resource_from_request.get("id")
        
        # Fetch owner's persona from persona-api (raises RuntimeError on failure)
        owner_persona = None
        if owner_persona_id:
            owner_persona = fetch_persona(str(owner_persona_id))
        elif owner_persona_title:
            owner_persona = fetch_persona_by_user_and_title(owner_id, str(owner_persona_title))
        
        # Augment owner with policy-specific attributes (NOT metadata)
        # IMPORTANT: Preserve existing owner fields (id, type, persona) from request
        if owner_persona:
            # Add policy-specific persona attributes to owner (e.g. autobook settings)
            # This only adds NEW fields, preserving existing ones like persona
            for attr in persona_attributes:
                if attr.name in owner_persona:
                    enriched_properties["owner"][attr.name] = owner_persona[attr.name]
    
    # Update resource with augmented properties
    resource["properties"] = enriched_properties
    
    return resource


def build_opa_context(
    authzen_request: dict[str, Any],
) -> dict[str, Any]:
    """Build OPA context from AuthZEN request.
    
    Logic flow:
    1. Extract and validate principal (REQUIRED - fail if missing/incomplete)
    2. Enrich principal with persona metadata (REQUIRED - fail if persona not found)
    3. Extract owner from resource (may be None for CREATE actions)
    4. Compute delegation if principal != owner
    
    Args:
        authzen_request: AuthZEN-compliant request
    
    Returns:
        Context dict with {delegation, principal}
    
    Raises:
        RuntimeError: If principal is missing, incomplete, or persona not found
    """
    
    # Step 1: Extract and validate principal
    principal_from_request = (authzen_request.get("context") or {}).get("principal")

    if not principal_from_request or not isinstance(principal_from_request, dict):
        raise RuntimeError("Principal is required in context")
    
    principal_id = principal_from_request.get("id")
    principal_persona_title = principal_from_request.get("persona")
    
    if not principal_id:
        raise RuntimeError("Principal must have an 'id'")
    if not principal_persona_title:
        raise RuntimeError("Principal must have a 'persona' title")
    
    # Step 2: Enrich principal with persona metadata
    enriched_principal = dict(principal_from_request)

    principal_persona = fetch_persona_by_user_and_title(
        str(principal_id), str(principal_persona_title)
    )    
    if principal_persona:
        # Persona found - enrich with metadata
        enriched_principal["persona_status"] = principal_persona.get("status", "")
        enriched_principal["persona_valid_from"] = principal_persona.get("valid_from", "")
        enriched_principal["persona_valid_till"] = principal_persona.get("valid_till", "")
    else:
        # Persona fetch failed - continue with 'unknown' persona
        # This is acceptable as policy-check is done by opa
        enriched_principal["persona_status"] = "not_found"
        enriched_principal["persona_valid_from"] = ""
        enriched_principal["persona_valid_till"] = ""
    
    # Step 3: Extract owner from resource (may be None for CREATE actions)
    resource_from_request = authzen_request.get("resource") or {}
    properties_from_request = resource_from_request.get("properties", {})
    
    owner = properties_from_request.get("owner")
    
    if isinstance(owner, dict):
        owner_id = owner.get("id")
        workflow_id = properties_from_request.get("workflow_id") or resource_from_request.get("id")
    else:
        owner_id = None
        workflow_id = None
   
    # Step 4: Compute delegation (only if owner exists and principal != owner)
    delegation = {
        "delegation_chain": [],
        "delegated_actions": [],
    }    
    if owner_id and principal_id != owner_id:
        # Principal is acting on behalf of owner - check for delegation
        try:
            action_from_request = authzen_request.get("action", {}).get("name", "")
            delegation_result = compute_delegation_chain(
                owner_id=str(owner_id),
                principal_id=str(principal_id),
                workflow_id=str(workflow_id) if workflow_id else None,
                requested_action=action_from_request,
            )
            delegation = {
                "delegation_chain": delegation_result.get("delegation_chain", []),
                "delegated_actions": delegation_result.get("delegated_actions", []),
            }
        except Exception:
            # Delegation fetch failed - continue with no delegation
            # This is acceptable as policy-check is done by opa
            pass
    
    return {
        "delegation": delegation,
        "principal": enriched_principal,
    }


# ============================================================================
# Call the OPA PDP
# ============================================================================

def evaluate_authorization_request(
    authzen_request: dict[str, Any],
) -> EvaluateResult:
    """Evaluate an authorization request end-to-end.
    
    Uses focused builder functions to construct OPA input and evaluates with OPA.
    
    Args:
        authzen_request: AuthZEN-compliant request body
    
    Returns:
        EvaluateResult with decision, reason_codes, and advice
    
    Raises:
        ValueError: If request is invalid or policy selection fails
    """

    # Select policy based on required policy_hint
    try:
        selected_policy = _POLICY_REGISTRY.select_policy(
            policy_hint=authzen_request.get("context", {}).get("policy_hint"),
        )
    except ValueError as e:
        raise ValueError(f"Policy selection failed: {e}") from e

    # 1. Build and validate subject for OPA policy
    try:
        subject = build_opa_subject(authzen_request)
    except ValueError as e:
        # Invalid or missing subject fields
        return EvaluateResult(
            decision="deny",
            reason_codes=["authz.invalid_subject"],
            advice=[{"message": str(e)}],
        )
    
    # 2. Build and validate action for OPA policy
    try:
        action = build_opa_action(authzen_request)
    except ValueError as e:
        # Invalid action name or missing action
        return EvaluateResult(
            decision="deny",
            reason_codes=["authz.invalid_action"],
            advice=[{"message": str(e)}],
        )
    
    # 3. Build and validate resource for OPA policy
    try:
        resource = build_opa_resource(
            authzen_request,
            selected_policy.persona_attributes,
            selected_policy.resource_attributes,
        )
    except ValueError as e:
        # Validation error (missing required attributes, etc.)
        return EvaluateResult(
            decision="deny",
            reason_codes=["authz.missing_required_attributes"],
            advice=[{"message": str(e)}],
        )
    except RuntimeError as e:
        # Persona API failure - return denial with system error
        return EvaluateResult(
            decision="deny",
            reason_codes=["authz.persona_fetch_failed"],
            advice=[{"message": f"Failed to fetch owner persona: {str(e)}"}],
        )
    
    # 4. Build and validate context for OPA policy
    try:
        context = build_opa_context(
            authzen_request,
        )
    except RuntimeError as e:
        # Persona or delegation API failure - return denial with system error
        return EvaluateResult(
            decision="deny",
            reason_codes=["authz.system_error"],
            advice=[{"message": f"Failed to build context: {str(e)}"}],
        )
    
    # Evaluate with OPA
    opa_authzen = {
        "subject": subject,
        "action": action,
        "resource": resource,
        "context": context,
    }
    
    opa_client = _build_opa_client_for_policy(selected_policy)
    is_allowed = opa_client.evaluate_allow(input_document=opa_authzen)
    reasons = opa_client.evaluate_reasons(input_document=opa_authzen)
    
    return EvaluateResult(
        decision="allow" if is_allowed else "deny",
        reason_codes=reasons,
        advice=[],
    )
