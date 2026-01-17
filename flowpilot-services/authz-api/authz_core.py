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
import api_logging
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
    http_post_json,
    normalize_departure_date,
    read_env_string,
)

# ============================================================================
# Configuration Constants
# ============================================================================

# Allowed action names (AuthZEN compliant, comma-separated)
# Must be configured via ALLOWED_ACTIONS environment variable
_ALLOWED_ACTIONS_STR = read_env_string("ALLOWED_ACTIONS")
ALLOWED_ACTIONS = {
    action.strip() for action in _ALLOWED_ACTIONS_STR.split(",") if action.strip()
}


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

# Delegation API configuration (required environment variables)
_DELEGATION_API_BASE_URL = read_env_string("DELEGATION_API_BASE_URL")

# User Profile API configuration (required environment variables)
_PERSONA_API_BASE_URL = read_env_string("PERSONA_API_BASE_URL")


def coerce_attribute_value(attr_value: Any, attr_type: str) -> Any:
    """Coerce attribute value based on manifest type.
    
    Args:
        attr_value: Raw attribute value
        attr_type: Type from manifest ("string", "integer", "float", "boolean", "date")
    
    Returns:
        Coerced value according to type
    """
    if attr_type == "float":
        return coerce_float(attr_value)
    elif attr_type == "integer":
        return coerce_int(attr_value, 0)
    elif attr_type == "date":
        return normalize_departure_date(attr_value)
    elif attr_type == "boolean":
        return coerce_bool(attr_value, False)
    else:  # string or unknown - return as-is (coerce to string if not None)
        return str(attr_value) if attr_value is not None else ""


def apply_attribute_defaults(
    attributes_dict: dict[str, Any],
    policy_attributes: list[PolicyAttribute],
) -> dict[str, Any]:
    """Apply default values for missing attributes based on policy manifest.
    
    Args:
        attributes_dict: Dictionary of attribute values (from persona or resource)
        policy_attributes: List of PolicyAttribute definitions with defaults
    
    Returns:
        Updated dictionary with defaults applied for missing attributes
    """
    result = dict(attributes_dict)

    for attr in policy_attributes:
        # If attribute is missing or None, apply default (if available)
        if attr.name not in result or result[attr.name] is None:
            if attr.default is not None:
                result[attr.name] = attr.default

    return result


def validate_attributes(
    attributes_dict: dict[str, Any],
    policy_attributes: list[PolicyAttribute],
    source_type: str,  # "persona" or "resource"
) -> str | None:
    """Validate that all required attributes are present.
    
    Args:
        attributes_dict: Dictionary of attribute values
        policy_attributes: List of PolicyAttribute definitions
        source_type: Type of attributes being validated (for error messages)
    
    Returns:
        None if validation passes, or error message string if validation fails
    """
    
    missing_required = []
    for attr in policy_attributes:
        if attr.required:
            if attr.name not in attributes_dict or attributes_dict[attr.name] is None:
                missing_required.append(attr.name)
    if missing_required:
        return f"Missing required {source_type} attributes: {', '.join(missing_required)}"

    return None


@dataclass(frozen=True)
class EvaluateResult:
    decision: str  # "allow" | "deny"
    reason_codes: list[str]
    advice: list[dict[str, Any]]


def build_opa_input(
    *,
    authzen_request: dict[str, Any],
    delegation_result: dict[str, Any] | None = None,
    owner_persona: dict[str, Any] | None = None,
    persona_attributes: list[PolicyAttribute] | None = None,
    resource_attributes: list[PolicyAttribute] | None = None,
) -> tuple[dict[str, Any], str | None]:
    # Build OPA input document from AuthZEN request.
    #
    # Args:
    #     authzen_request: AuthZEN-compliant request body with context.principal containing claims
    #     delegation_result: Computed delegation chain result from delegation-api (PIP data)
    #     owner_persona: Optional owner's persona with policy-specific attributes
    #     persona_attributes: List of typed persona attributes from manifest
    #     resource_attributes: List of typed resource attributes from manifest

    # Extract top-level AuthZEN elements
    request_context = authzen_request.get("context") or {}
    request_resource = authzen_request.get("resource") or {}
    request_action = authzen_request.get("action") or {}
    request_subject = authzen_request.get("subject") or {}
    resource_properties = coerce_dict(
        request_resource.get("properties"), "resource.properties"
    )

    # ========================================================================
    # SUBJECT: Use the subject from the AuthZEN request (agent or user)
    # ========================================================================
    subject_id = request_subject.get("id", "")
    subject_type = request_subject.get("type", "user")

    # Extract subject persona
    subject_persona = request_subject.get("persona") or ""
    if isinstance(subject_persona, list) and subject_persona:
        subject_persona = subject_persona[0]
    subject_persona = str(subject_persona) if subject_persona else ""

    subject = {
        "type": subject_type,
        "id": subject_id,
        "persona": subject_persona,
    }

    # ========================================================================
    # RESOURCE: Preserve AuthZEN structure and augment with owner attributes
    # ========================================================================
    # Start with the original resource structure from AuthZEN request
    resource = dict(request_resource)

    # Make a copy of properties to augment
    resource_properties_augmented = dict(resource_properties)

    # Apply defaults and validate resource attributes
    if resource_attributes:
        # Apply defaults for missing resource attributes
        resource_properties_augmented = apply_attribute_defaults(
            resource_properties_augmented, resource_attributes
        )

        # Validate required resource attributes are present
        validation_error = validate_attributes(
            resource_properties_augmented, resource_attributes, "resource"
        )
        if validation_error:
            # Return validation error instead of continuing
            return {}, validation_error

        # Coerce resource attribute types after defaults and validation
        for attr in resource_attributes:
            if attr.name in resource_properties_augmented:
                resource_properties_augmented[attr.name] = coerce_attribute_value(
                    resource_properties_augmented[attr.name], attr.type
                )

    # Extract owner information
    owner_props = coerce_dict(
        resource_properties_augmented.get("owner"), "resource.properties.owner"
    )
    owner_id = owner_props.get("id") if owner_props else None

    # Augment resource.properties.owner with fetched persona attributes
    if owner_id and owner_persona:
        # Ensure owner object exists and is a dict
        if "owner" not in resource_properties_augmented:
            resource_properties_augmented["owner"] = {}
        if not isinstance(resource_properties_augmented["owner"], dict):
            resource_properties_augmented["owner"] = {}

        # ALWAYS fetch 'consent' - it's a general attribute, not policy-specific
        if "consent" in owner_persona:
            resource_properties_augmented["owner"]["consent"] = owner_persona["consent"]

        # Extract policy-specific persona attributes from manifest
        # Note: persona-api already validates, applies defaults, and coerces these
        # attributes, so we can trust the data and pass it through directly
        if persona_attributes:
            for attr in persona_attributes:
                if attr.name in owner_persona:
                    resource_properties_augmented["owner"][attr.name] = owner_persona[attr.name]

        # Always add persona metadata for policy evaluation (not policy-specific)
        # Trust the source system - all mandatory fields should be present
        persona_id = owner_persona.get("persona_id", "")
        persona_title = owner_persona.get("title", "")
        persona_status = owner_persona.get("status", "")  # No default - trust source
        persona_valid_from = owner_persona.get("valid_from", "")
        persona_valid_till = owner_persona.get("valid_till", "")

        resource_properties_augmented["owner"]["persona_id"] = persona_id
        resource_properties_augmented["owner"]["persona"] = persona_title
        resource_properties_augmented["owner"]["persona_status"] = persona_status
        resource_properties_augmented["owner"]["persona_valid_from"] = persona_valid_from
        resource_properties_augmented["owner"]["persona_valid_till"] = persona_valid_till

    # Update resource with augmented properties
    resource["properties"] = resource_properties_augmented

    # ========================================================================
    # CONTEXT: Build AuthZEN-compliant context with delegation and principal
    # ========================================================================

    # Add the delegation chain, if required
    if delegation_result is not None:
        delegation = delegation_result
    else:
        delegation = {
            "valid": False,
            "delegation_chain": [],
            "delegated_actions": [],
        }

    # Initialize context with delegation
    context = {
        "delegation": delegation,
    }

    # Preserve context.principal from the original request (for agent-runner scenarios)
    if "principal" in request_context:
        context["principal"] = request_context["principal"]

    # ========================================================================
    # Assemble final OPA input document
    # ========================================================================
    opa_input = {
        "subject": subject,
        "action": request_action,
        "resource": resource,
        "context": context,
    }

    # Return OPA input with no validation error (success)
    return opa_input, None


def fetch_persona_from_api(persona_id: str) -> dict[str, Any]:
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

    try:
        response = requests.get(
            f"{_PERSONA_API_BASE_URL.rstrip('/')}/v1/personas/{persona_id}",
            headers=headers,
            **get_http_config(),
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        # If persona not found (404), return empty dict and fall back to defaults
        if e.response.status_code == 404:
            api_logging.log_api_response(
                "GET", f"/v1/personas/{persona_id}", 404,
                error=f"Persona not found: {persona_id}"
            )
            return {}
        raise RuntimeError(f"Failed to fetch persona {persona_id}: {e}") from e
    except Exception as e:
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
    #     Dictionary with persona attributes (same as fetch_persona_from_api)
    #
    # Raises:
    #     RuntimeError: If service token is not available or API call fails

    # Get service token for persona API authentication
    service_token = security.get_service_token()
    if not service_token:
        raise RuntimeError("Service token not available - cannot fetch personas")

    headers = {"Authorization": f"Bearer {service_token.strip()}"}

    try:
        # List all personas for the user (service account has access to all users' personas)
        response = requests.get(
            f"{_PERSONA_API_BASE_URL.rstrip('/')}/v1/users/{user_sub}/personas",
            headers=headers,
            **get_http_config(),
        )

        # If no personas found, return empty dict
        if response.status_code == 404:
            api_logging.log_api_response(
                "GET", f"/v1/users/{user_sub}/personas", 404,
                error=f"No personas found for user {user_sub}"
            )
            return {}

        response.raise_for_status()
        personas_data = response.json()
        personas = personas_data.get("personas", [])

        # Find first persona with matching title (regardless of status)
        # Let OPA policy decide if the persona status is acceptable for the requested action
        for persona in personas:
            if persona.get("title") == persona_title:
                return persona

        # No matching persona found
        return {}
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return {}
        raise RuntimeError(f"Failed to fetch personas for {user_sub}: {e}") from e
    except Exception as e:
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
    #       - valid: boolean (whether delegation path exists)
    #       - delegation_chain: list of user IDs in the chain
    #       - delegated_actions: list of actions available through delegation
    #
    # Raises:
    #     RuntimeError: If service token is not available

    # Get service token for delegation API authentication
    service_token = security.get_service_token()
    if not service_token:
        raise RuntimeError("Service token not available - cannot validate delegation")

    headers = {"Authorization": f"Bearer {service_token.strip()}"}

    params: dict[str, str] = {
        "principal_id": owner_id,
        "delegate_id": principal_id,
    }
    if workflow_id:
        params["workflow_id"] = workflow_id

    response = requests.get(
        f"{_DELEGATION_API_BASE_URL.rstrip('/')}/v1/delegations/validate",
        params=params,
        headers=headers,
        **get_http_config(),
    )
    response.raise_for_status()  # Raise HTTPError for bad responses

    data = response.json()
    valid = data.get("valid", False)
    delegation_chain = data.get("delegation_chain", [])
    delegated_actions = data.get("delegated_actions", [])

    # Return delegation data - let OPA decide if permissions are sufficient
    return {
        "valid": valid,
        "delegation_chain": delegation_chain,
        "delegated_actions": delegated_actions,
    }


def evaluate_authorization_request(
    authzen_request: dict[str, Any],
) -> EvaluateResult:
    # Evaluate an authorization request end-to-end.
    #
    # This function handles the complete authorization flow:
    # 1. Validates AuthZEN compliance
    # 2. Computes delegation chain (if resource has owner)
    # 3. Fetches owner attributes (if resource has owner)
    # 4. Evaluates the request with OPA
    #
    # Args:
    #     authzen_request: AuthZEN-compliant request body
    #
    # Returns:
    #     EvaluateResult with decision, reason_codes, and advice
    #
    # Raises:
    #     ValueError: If request is not AuthZEN compliant

    # Validate and extract principal
    context = authzen_request.get("context", {})
    principal = context.get("principal")
    if not principal or not isinstance(principal, dict):
        raise ValueError(
            "Request must be AuthZEN compliant: context.principal is required"
        )

    principal_id = principal.get("id")
    if (
        not principal_id
        or not isinstance(principal_id, str)
        or not principal_id.strip()
    ):
        raise ValueError(
            "Request must be AuthZEN compliant: context.principal.id is required"
        )
    principal_id = principal_id.strip()

    # Validate and extract action
    action = authzen_request.get("action", {})
    if not action or not isinstance(action, dict):
        raise ValueError("Request must be AuthZEN compliant: action is required")

    action_name = action.get("name")
    if not action_name or not isinstance(action_name, str) or not action_name.strip():
        raise ValueError("Request must be AuthZEN compliant: action.name is required")

    action_name = security.sanitize_string(action_name.strip(), 255)
    if action_name not in ALLOWED_ACTIONS:
        raise ValueError(
            f"Invalid action name: {action_name}. Allowed actions: {', '.join(sorted(ALLOWED_ACTIONS))}"
        )

    # ========================================================================
    # POLICY SELECTION: Extract resource type and policy hint for routing
    # ========================================================================
    request_resource = authzen_request.get("resource", {})
    resource_type = request_resource.get("type")
    policy_hint = context.get("policy_hint")

    # Select appropriate policy based on resource type or policy hint
    try:
        selected_policy = _POLICY_REGISTRY.select_policy(
            resource_type=resource_type,
            policy_hint=policy_hint,
        )
    except ValueError as e:
        # Policy selection failed - return error
        raise ValueError(f"Policy selection failed: {e}") from e

    # Create OPA client for the selected policy
    opa_client = _build_opa_client_for_policy(selected_policy)

    # Log policy selection for debugging
    api_logging.log_api_request(
        "POLICY_SELECTION",
        f"Selected policy: {selected_policy.name}",
        request_body={"resource_type": resource_type, "policy_hint": policy_hint},
    )

    # Validate and extract workflow and owner information from resource
    resource_properties = request_resource.get("properties", {})

    owner = resource_properties.get("owner")
    owner_id = None
    owner_persona_id = None
    workflow_id = None
    if isinstance(owner, dict):
        owner_id_raw = owner.get("id")
        owner_id = str(owner_id_raw) if owner_id_raw else None
        # Extract persona_id from owner object
        owner_persona_id_raw = owner.get("persona_id")
        owner_persona_id = str(owner_persona_id_raw) if owner_persona_id_raw else None
        workflow_id_raw = resource_properties.get(
            "workflow_id"
        ) or request_resource.get("id")
        workflow_id = str(workflow_id_raw) if workflow_id_raw else None

    # Compute delegation chain and fetch owner persona (PIP - Policy Information Point)
    delegation_result = None
    owner_persona = None
    if owner_id:
        # Fetch owner's persona from persona-api
        if owner_persona_id:
            # Have persona_id, fetch directly
            try:
                owner_persona = fetch_persona_from_api(owner_persona_id)
            except Exception as e:
                # Log error but continue with empty persona (will use defaults)
                api_logging.log_api_response(
                    "GET", f"/v1/personas/{owner_persona_id}", 500,
                    error=f"Failed to fetch persona: {e}"
                )
                owner_persona = {}
        else:
            # No persona_id, check if we have persona title in owner object
            owner_persona_title = owner.get("persona") if isinstance(owner, dict) else None
            if owner_persona_title:
                # Look up persona by user_sub and title
                try:
                    owner_persona = fetch_persona_by_user_and_title(owner_id, str(owner_persona_title))
                except Exception as e:
                    # Log error but continue with empty persona (will use defaults)
                    api_logging.log_api_response(
                        "GET", f"/v1/personas?user_sub={owner_id}&title={owner_persona_title}", 500,
                        error=f"Failed to fetch persona: {e}"
                    )
                    owner_persona = {}
            else:
                # No persona info provided, use empty persona (defaults will apply)
                owner_persona = {}

        # Compute delegation chain from delegation-api
        delegation_result = compute_delegation_chain(
            owner_id=owner_id,
            principal_id=principal_id,
            workflow_id=workflow_id,
            requested_action=action_name,
        )

    # Build OPA input document using selected policy's attributes
    input_document, validation_error = build_opa_input(
        authzen_request=authzen_request,
        delegation_result=delegation_result,
        owner_persona=owner_persona,
        persona_attributes=selected_policy.persona_attributes,
        resource_attributes=selected_policy.resource_attributes,
    )

    # If validation failed, return denial with reason code
    if validation_error:
        return EvaluateResult(
            decision="deny",
            reason_codes=["authz.missing_required_attributes"],
            advice=[{"message": validation_error}],
        )

    api_logging.log_api_request(
        "POST", f"OPA /v1/data/{selected_policy.package}/allow", request_body=input_document
    )

    # Evaluate with OPA using selected policy's OPA client
    is_allowed = opa_client.evaluate_allow(input_document=input_document)
    reasons = opa_client.evaluate_reasons(input_document=input_document)

    return EvaluateResult(
        decision="allow" if is_allowed else "deny",
        reason_codes=reasons,
        advice=[],
    )
