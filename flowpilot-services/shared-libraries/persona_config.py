# Persona Configuration Loader
#
# This module provides utilities to load persona configuration from policy manifests.
# It serves as the single source of truth for allowed persona titles and delegation rules.

import os
from pathlib import Path
from typing import List, Dict, Any

import yaml


def load_persona_config_from_manifest(
    policy_name: str = "travel",
    manifest_dir: str = "/policies"
) -> Dict[str, Any]:
    """Load persona configuration from policy manifest.
    
    Args:
        policy_name: Policy identifier (default: "travel")
        manifest_dir: Base directory containing policy subdirectories
        
    Returns:
        Dict with persona_config containing:
        - persona_titles: List of persona title definitions with metadata
        - allowed_titles: (Computed) List of allowed persona titles (for backward compatibility)
        - delegation_personas: (Computed) Dict mapping actions to allowed personas (for backward compatibility)
        
    Raises:
        FileNotFoundError: If manifest file doesn't exist
        ValueError: If manifest is invalid or missing persona_config
    """
    manifest_path = Path(manifest_dir) / policy_name / "manifest.yaml"
    
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Policy manifest not found: {manifest_path}"
        )
    
    try:
        with open(manifest_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse policy manifest {manifest_path}: {e}") from e
    
    if not isinstance(data, dict):
        raise ValueError(f"Policy manifest must be a YAML dictionary")
    
    persona_config = data.get("persona_config")
    if not persona_config:
        raise ValueError(f"Policy manifest missing 'persona_config' section")
    
    if not isinstance(persona_config, dict):
        raise ValueError(f"'persona_config' must be a dict")
    
    # Require persona_titles
    if "persona_titles" not in persona_config:
        raise ValueError("persona_config missing 'persona_titles'")
    
    if not isinstance(persona_config["persona_titles"], list):
        raise ValueError("persona_config.persona_titles must be a list")
    
    # Compute allowed_titles and delegation_personas for backward compatibility
    persona_config["allowed_titles"] = _extract_allowed_titles(persona_config["persona_titles"])
    persona_config["delegation_personas"] = _extract_delegation_personas(persona_config["persona_titles"])
    
    return persona_config


def _extract_allowed_titles(persona_titles: List[Dict[str, Any]]) -> List[str]:
    """Extract list of allowed persona titles from persona_titles definitions.
    
    Args:
        persona_titles: List of persona title definitions
        
    Returns:
        List of persona title strings
    """
    return [p["title"] for p in persona_titles if isinstance(p, dict) and "title" in p]


def _extract_delegation_personas(persona_titles: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Extract delegation personas by action from persona_titles definitions.
    
    Args:
        persona_titles: List of persona title definitions
        
    Returns:
        Dict mapping action names to lists of delegatable persona titles
    """
    delegation_personas = {"read": [], "update": [], "execute": [], "delete": []}
    
    for persona in persona_titles:
        if not isinstance(persona, dict):
            continue
        
        title = persona.get("title")
        if not title:
            continue
        
        # Only include personas that can be delegated to
        if not persona.get("can-be-delegated-to", False):
            continue
        
        # Add this persona to allowed actions based on its allowed-actions
        allowed_actions = persona.get("allowed-actions", [])
        for action in allowed_actions:
            if action in delegation_personas:
                delegation_personas[action].append(title)
    
    return delegation_personas


def get_persona_titles(
    policy_name: str = "travel",
    manifest_dir: str = "/policies"
) -> List[Dict[str, Any]]:
    """Get persona title definitions with metadata from manifest.
    
    Args:
        policy_name: Policy identifier (default: "travel")
        manifest_dir: Base directory containing policy subdirectories
        
    Returns:
        List of persona definition dicts with keys:
        - title: Persona title
        - description: Human-readable description
        - can-be-invited: Whether this persona can be invited
        - can-be-delegated-to: Whether this persona can be delegated to
        - allowed-actions: List of allowed actions
    """
    persona_config = load_persona_config_from_manifest(policy_name, manifest_dir)
    return persona_config.get("persona_titles", [])


def get_allowed_persona_titles(
    policy_name: str = "travel",
    manifest_dir: str = "/policies"
) -> List[str]:
    """Get list of allowed persona titles from manifest.
    
    Args:
        policy_name: Policy identifier (default: "travel")
        manifest_dir: Base directory containing policy subdirectories
        
    Returns:
        List of allowed persona title strings
    """
    persona_config = load_persona_config_from_manifest(policy_name, manifest_dir)
    return persona_config["allowed_titles"]


def get_allowed_persona_statuses(
    policy_name: str = "travel",
    manifest_dir: str = "/policies"
) -> List[str]:
    """Get list of allowed persona statuses from manifest.
    
    Args:
        policy_name: Policy identifier (default: "travel")
        manifest_dir: Base directory containing policy subdirectories
        
    Returns:
        List of allowed persona status strings (e.g., ["pending", "active", "inactive", "suspended", "expired"])
        
    Raises:
        ValueError: If persona_statuses not defined in manifest
    """
    persona_config = load_persona_config_from_manifest(policy_name, manifest_dir)
    statuses = persona_config.get("persona_statuses")
    
    if statuses is None:
        raise ValueError(
            f"persona_config.persona_statuses not defined in manifest for policy '{policy_name}'. "
            f"Please add persona_statuses list to the manifest."
        )
    
    if not isinstance(statuses, list):
        raise ValueError(f"persona_config.persona_statuses must be a list")
    
    return statuses


def get_invitation_personas(
    policy_name: str = "travel",
    manifest_dir: str = "/policies"
) -> List[str]:
    """Get list of personas that can be invited from manifest.
    
    Args:
        policy_name: Policy identifier (default: "travel")
        manifest_dir: Base directory containing policy subdirectories
        
    Returns:
        List of persona titles that can be invited
    """
    persona_titles = get_persona_titles(policy_name, manifest_dir)
    return [p["title"] for p in persona_titles if p.get("can-be-invited", False)]


def get_delegatable_personas(
    policy_name: str = "travel",
    manifest_dir: str = "/policies"
) -> List[str]:
    """Get list of personas that can be delegated to from manifest.
    
    Args:
        policy_name: Policy identifier (default: "travel")
        manifest_dir: Base directory containing policy subdirectories
        
    Returns:
        List of persona titles that can be delegated to
    """
    persona_titles = get_persona_titles(policy_name, manifest_dir)
    return [p["title"] for p in persona_titles if p.get("can-be-delegated-to", False)]


def get_persona_by_title(
    title: str,
    policy_name: str = "travel",
    manifest_dir: str = "/policies"
) -> Dict[str, Any] | None:
    """Get persona definition by title from manifest.
    
    Args:
        title: Persona title to look up
        policy_name: Policy identifier (default: "travel")
        manifest_dir: Base directory containing policy subdirectories
        
    Returns:
        Persona definition dict if found, None otherwise
    """
    persona_titles = get_persona_titles(policy_name, manifest_dir)
    for persona in persona_titles:
        if persona.get("title") == title:
            return persona
    return None


def get_delegation_personas_for_action(
    action: str,
    policy_name: str = "travel",
    manifest_dir: str = "/policies"
) -> List[str]:
    """Get list of personas that can be delegated for a specific action.
    
    Args:
        action: Action name ("execute", "read", "edit")
        policy_name: Policy identifier (default: "travel")
        manifest_dir: Base directory containing policy subdirectories
        
    Returns:
        List of persona titles authorized for the action
        
    Raises:
        ValueError: If action is not defined in manifest
    """
    persona_config = load_persona_config_from_manifest(policy_name, manifest_dir)
    delegation_personas = persona_config.get("delegation_personas", {})
    
    if action not in delegation_personas:
        raise ValueError(f"Action '{action}' not defined in persona_config.delegation_personas")
    
    return delegation_personas[action]


def load_full_manifest(
    policy_name: str = "travel",
    manifest_dir: str = "/policies"
) -> Dict[str, Any]:
    """Load complete policy manifest including attributes section.
    
    Args:
        policy_name: Policy identifier (default: "travel")
        manifest_dir: Base directory containing policy subdirectories
        
    Returns:
        Complete manifest dictionary
        
    Raises:
        FileNotFoundError: If manifest file doesn't exist
        ValueError: If manifest is invalid
    """
    manifest_path = Path(manifest_dir) / policy_name / "manifest.yaml"
    
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Policy manifest not found: {manifest_path}"
        )
    
    try:
        with open(manifest_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse policy manifest {manifest_path}: {e}") from e
    
    if not isinstance(data, dict):
        raise ValueError(f"Policy manifest must be a YAML dictionary")
    
    return data


def get_persona_attribute_schema(
    policy_name: str = "travel",
    manifest_dir: str = "/policies"
) -> Dict[str, Dict[str, Any]]:
    """Get schema for persona attributes from manifest.
    
    Returns a dict mapping attribute names to their definitions.
    Only includes attributes with source="persona".
    
    Args:
        policy_name: Policy identifier (default: "travel")
        manifest_dir: Base directory containing policy subdirectories
        
    Returns:
        Dict mapping attribute name to attribute definition dict with keys:
        - type: Data type ("integer", "string", "boolean", "float", "date")
        - required: Whether the attribute is required
        - default: Default value if not required
        - description: Human-readable description
    """
    manifest = load_full_manifest(policy_name, manifest_dir)
    attributes = manifest.get("attributes", [])
    
    schema = {}
    for attr in attributes:
        if not isinstance(attr, dict):
            continue
        
        # Only include persona-sourced attributes
        if attr.get("source") == "persona":
            name = attr.get("name")
            if name:
                schema[name] = {
                    "type": attr.get("type", "string"),
                    "required": attr.get("required", False),
                    "default": attr.get("default"),
                    "description": attr.get("description", ""),
                }
    
    return schema


def coerce_attribute_value(attr_value: Any, attr_type: str) -> Any:
    """Coerce attribute value based on manifest type.
    
    This follows the same logic as authz-api's coerce_attribute_value.
    
    Args:
        attr_value: Raw attribute value
        attr_type: Type from manifest ("string", "integer", "float", "boolean", "date", "email")
    
    Returns:
        Coerced value according to type
    """
    # Import utils for coerce functions (avoid circular import by importing inside function)
    import utils
    
    if attr_type == "float":
        # Convert to float, default to 0.0 if invalid
        if isinstance(attr_value, (int, float)) and not isinstance(attr_value, bool):
            return float(attr_value)
        return 0.0
    elif attr_type == "integer":
        # Convert to int, default to 0 if invalid
        if isinstance(attr_value, int) and not isinstance(attr_value, bool):
            return int(attr_value)
        if isinstance(attr_value, float):
            return int(attr_value)
        return 0
    elif attr_type == "boolean":
        # Convert to bool, default to False if invalid
        if isinstance(attr_value, bool):
            return attr_value
        return False
    elif attr_type == "date":
        # Return as-is for date strings (ISO 8601)
        return str(attr_value) if attr_value is not None else ""
    elif attr_type == "email":
        # Coerce to lowercase normalized email, or empty string if invalid
        return utils.coerce_email(attr_value, default="") or ""
    else:  # string or unknown - return as-is (coerce to string if not None)
        return str(attr_value) if attr_value is not None else ""


def apply_attribute_defaults(
    attributes_dict: Dict[str, Any],
    schema: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Apply default values for missing attributes based on schema.
    
    Args:
        attributes_dict: Dictionary of attribute values
        schema: Attribute schema from get_persona_attribute_schema()
    
    Returns:
        Updated dictionary with defaults applied for missing attributes
    """
    result = dict(attributes_dict)
    
    for attr_name, attr_schema in schema.items():
        # If attribute is missing or None, apply default (if available)
        if attr_name not in result or result[attr_name] is None:
            if attr_schema["default"] is not None:
                result[attr_name] = attr_schema["default"]
    
    return result


def validate_required_attributes(
    attributes_dict: Dict[str, Any],
    schema: Dict[str, Dict[str, Any]],
) -> str | None:
    """Validate that all required attributes are present.
    
    Args:
        attributes_dict: Dictionary of attribute values
        schema: Attribute schema from get_persona_attribute_schema()
    
    Returns:
        None if validation passes, or error message string if validation fails
    """
    missing_required = []
    for attr_name, attr_schema in schema.items():
        if attr_schema["required"]:
            if attr_name not in attributes_dict or attributes_dict[attr_name] is None:
                missing_required.append(attr_name)
    
    if missing_required:
        return f"Missing required persona attributes: {', '.join(missing_required)}"
    
    return None


def apply_defaults_and_coerce_attributes(
    attributes_dict: Dict[str, Any],
    policy_name: str = "travel",
    manifest_dir: str = "/policies"
) -> tuple[Dict[str, Any], str | None]:
    """Apply defaults, validate required attributes, and coerce types.
    
    This is the main entry point for persona attribute processing.
    It follows the same pattern as authz-api's attribute handling.
    
    Args:
        attributes_dict: Dictionary of attribute values
        policy_name: Policy identifier (default: "travel")
        manifest_dir: Base directory containing policy subdirectories
    
    Returns:
        Tuple of (processed_attributes_dict, error_message)
        If error_message is not None, validation failed
    """
    schema = get_persona_attribute_schema(policy_name, manifest_dir)
    
    # Step 1: Apply defaults for missing attributes
    result = apply_attribute_defaults(attributes_dict, schema)
    
    # Step 2: Validate required attributes are present
    validation_error = validate_required_attributes(result, schema)
    if validation_error:
        return {}, validation_error
    
    # Step 3: Coerce types
    for attr_name, attr_schema in schema.items():
        if attr_name in result:
            result[attr_name] = coerce_attribute_value(
                result[attr_name], attr_schema["type"]
            )
    
    return result, None
