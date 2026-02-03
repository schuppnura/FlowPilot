# Policy Manifest Loader for FlowPilot AuthZ API
#
# This module handles loading and parsing policy manifests that define:
# - OPA package name for policy evaluation
# - Required persona attributes for policy input
#
# Manifest files are YAML documents located in the policy directory structure:
#   {POLICY_MANIFEST_DIR}/{policy_name}/manifest.yaml
#
# Example manifest:
#   name: travel
#   package: auto_book
#   attributes:
#     - consent
#     - autobook_price
#     - autobook_leadtime
#     - autobook_risklevel

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List

import yaml


@dataclass(frozen=True)
class PolicyAttribute:
    """Represents a typed attribute requirement with defaults and validation."""
    name: str
    type: str  # "string", "integer", "float", "boolean", "date"
    source: str  # "persona" | "resource" - where the attribute comes from
    default: Any = None  # Default value if attribute is missing
    description: str = ""  # Human-readable description
    required: bool = False  # Whether attribute must be present (overrides default)


@dataclass(frozen=True)
class PolicyManifest:
    """Represents a policy manifest with package and attribute requirements."""

    name: str  # Policy identifier (e.g., "travel", "nursing")
    package: str  # OPA package name (e.g., "auto_book", "nursing_care")
    attributes: list[PolicyAttribute]  # All required attributes (unified list with source field)
    persona_config: dict[str, Any] = None  # Persona configuration (allowed titles, delegation rules)

    def __post_init__(self):
        """Validate manifest fields."""
        if not self.name or not isinstance(self.name, str):
            raise ValueError(f"Policy manifest 'name' must be a non-empty string, got: {self.name}")
        if not isinstance(self.package, str):
            raise ValueError(f"Policy manifest 'package' must be a non-empty string, got: {self.package}")
        if not isinstance(self.attributes, list):
            raise ValueError("Policy manifest 'attributes' must be a list")
        if not all(isinstance(attr, PolicyAttribute) for attr in self.attributes):
            raise ValueError("Policy manifest 'attributes' must be PolicyAttribute objects")

    @property
    def persona_attributes(self) -> list[PolicyAttribute]:
        """Get persona attributes (for backward compatibility)."""
        return [attr for attr in self.attributes if attr.source == "persona"]

    @property
    def resource_attributes(self) -> list[PolicyAttribute]:
        """Get resource attributes (for backward compatibility)."""
        return [attr for attr in self.attributes if attr.source == "resource"]


def load_policy_manifest(policy_name: str, manifest_dir: str) -> PolicyManifest:
    """Load policy manifest from YAML file.
    
    Args:
        policy_name: Policy identifier (e.g., "travel")
        manifest_dir: Base directory containing policy subdirectories
        
    Returns:
        PolicyManifest with parsed configuration
        
    Raises:
        FileNotFoundError: If manifest file doesn't exist
        ValueError: If manifest is invalid or malformed
        yaml.YAMLError: If manifest cannot be parsed
    """
    manifest_path = Path(manifest_dir) / policy_name / "manifest.yaml"

    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Policy manifest not found: {manifest_path}. "
            f"Expected structure: {manifest_dir}/{policy_name}/manifest.yaml"
        )

    try:
        with open(manifest_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse policy manifest {manifest_path}: {e}") from e

    if not isinstance(data, dict):
        raise ValueError(f"Policy manifest must be a YAML dictionary, got: {type(data)}")

    # Extract required fields
    name = data.get("name")
    package = data.get("package")

    # Validate manifest structure
    if not name:
        raise ValueError(f"Policy manifest missing required field 'name': {manifest_path}")
    if not package:
        raise ValueError(f"Policy manifest missing required field 'package': {manifest_path}")

    # Validate name matches expected policy_name
    if name != policy_name:
        raise ValueError(
            f"Policy manifest 'name' field ({name}) does not match policy directory ({policy_name})"
        )

    # Parse unified attributes list (required)
    attrs_raw = data.get("attributes")
    if not attrs_raw:
        raise ValueError(f"Policy manifest missing required field 'attributes': {manifest_path}")
    if not isinstance(attrs_raw, list):
        raise ValueError(f"'attributes' must be a list, got: {type(attrs_raw)}")

    all_attributes = []
    for attr_def in attrs_raw:
        if not isinstance(attr_def, dict):
            raise ValueError(
                f"Each attribute must be a dict with 'name', 'type', and 'source'. Got: {attr_def}"
            )

        attr_name = attr_def.get("name")
        if not attr_name:
            raise ValueError(f"Attribute missing 'name' field: {attr_def}")

        attr_type = attr_def.get("type", "string")
        attr_source = attr_def.get("source")
        if not attr_source or attr_source not in ("persona", "resource"):
            raise ValueError(
                f"Attribute '{attr_name}' missing or invalid 'source' field "
                f"(must be 'persona' or 'resource'): {attr_def}"
            )

        attr_default = attr_def.get("default")
        attr_description = attr_def.get("description", "")

        # Determine if attribute is required
        # If 'required' is explicitly set, use that value
        # Otherwise, infer: attributes without defaults are required by default
        if "required" in attr_def:
            attr_required = bool(attr_def["required"])
        else:
            attr_required = (attr_default is None)

        all_attributes.append(PolicyAttribute(
            name=attr_name,
            type=attr_type,
            source=attr_source,
            default=attr_default,
            description=attr_description,
            required=attr_required,
        ))

    # Parse optional persona_config
    persona_config = data.get("persona_config")
    if persona_config and not isinstance(persona_config, dict):
        raise ValueError(f"'persona_config' must be a dict, got: {type(persona_config)}")

    return PolicyManifest(
        name=name,
        package=package,
        attributes=all_attributes,
        persona_config=persona_config,
    )


class PolicyRegistry:
    """Registry for managing multiple policy manifests."""

    def __init__(self, manifest_dir: str):
        """Initialize registry by loading all policies from directory.
        
        Args:
            manifest_dir: Base directory containing policy subdirectories
        """
        self.manifest_dir = manifest_dir
        self.policies: dict[str, PolicyManifest] = {}
        self._load_all_policies()

    def _load_all_policies(self) -> None:
        """Load all policy manifests from the directory."""
        manifest_path = Path(self.manifest_dir)
        if not manifest_path.exists():
            raise RuntimeError(f"Policy manifest directory not found: {self.manifest_dir}")

        # Find all subdirectories with manifest.yaml
        policy_errors = []
        for policy_dir in manifest_path.iterdir():
            if policy_dir.is_dir():
                manifest_file = policy_dir / "manifest.yaml"
                if manifest_file.exists():
                    try:
                        policy_name = policy_dir.name
                        manifest = load_policy_manifest(policy_name, self.manifest_dir)
                        self.policies[policy_name] = manifest
                    except Exception as e:
                        # Collect errors instead of silently continuing
                        policy_errors.append(f"Failed to load policy '{policy_dir.name}': {e}")

        if not self.policies:
            error_details = "\n".join(policy_errors) if policy_errors else "No manifest.yaml files found"
            raise RuntimeError(f"No valid policies found in {self.manifest_dir}. {error_details}")

        if policy_errors:
            # Some policies failed to load but at least one succeeded
            # Raise exception to make failures visible instead of silently ignoring them
            raise RuntimeError(
                f"Loaded {len(self.policies)} policies but encountered errors:\n" + "\n".join(policy_errors)
            )

        print(f"Loaded {len(self.policies)} policies: {', '.join(self.policies.keys())}", flush=True)

    def select_policy(
        self,
        policy_hint: str,
    ) -> PolicyManifest:
        """Select policy by explicit policy_hint.
        
        Args:
            policy_hint: Explicit policy name from context.policy_hint (REQUIRED)
        
        Returns:
            PolicyManifest for the selected policy
        
        Raises:
            ValueError: If policy_hint is missing or policy not found
        """
        if not policy_hint:
            available = ", ".join(self.policies.keys())
            raise ValueError(
                f"Policy selection requires context.policy_hint. "
                f"Available policies: {available}"
            )
        
        if policy_hint not in self.policies:
            available = ", ".join(self.policies.keys())
            raise ValueError(
                f"Policy '{policy_hint}' not found. Available policies: {available}"
            )
        
        return self.policies[policy_hint]

    def get_policy_by_name(self, policy_name: str) -> PolicyManifest:
        """Get policy manifest by name.
        
        Args:
            policy_name: Name of the policy
        
        Returns:
            PolicyManifest for the policy
        
        Raises:
            ValueError: If policy not found
        """
        if policy_name not in self.policies:
            available = ", ".join(self.policies.keys())
            raise ValueError(f"Policy '{policy_name}' not found. Available: {available}")
        return self.policies[policy_name]

    def list_policies(self) -> list[str]:
        """List all available policy names."""
        return list(self.policies.keys())

    def get_all_allowed_actions(self) -> set[str]:
        """Get all allowed actions across all loaded policies.
        
        Collects unique actions from:
        - All persona_titles.allowed-actions in persona_config
        - Standard CRUD actions (if any personas exist)
        
        Returns:
            Set of all allowed action names
        """
        actions = set()
        
        for policy in self.policies.values():
            if policy.persona_config:
                persona_titles = policy.persona_config.get("persona_titles", [])
                for persona_def in persona_titles:
                    if isinstance(persona_def, dict):
                        allowed = persona_def.get("allowed-actions", [])
                        if isinstance(allowed, list):
                            actions.update(allowed)
        
        return actions


def get_policy_manifest_from_env() -> PolicyManifest:
    """Load policy manifest using environment variables.
    
    Reads configuration from:
    - POLICY_NAME: Policy identifier (required)
    - POLICY_MANIFEST_DIR: Base directory for policy manifests (default: /policies)
    
    Returns:
        PolicyManifest for the configured policy
        
    Raises:
        RuntimeError: If required environment variables are missing
        FileNotFoundError: If manifest file doesn't exist
        ValueError: If manifest is invalid
    """
    policy_name = os.environ.get("POLICY_NAME")
    if not policy_name:
        raise RuntimeError(
            "POLICY_NAME environment variable is required. "
            "Example: POLICY_NAME=travel"
        )

    manifest_dir = os.environ.get("POLICY_MANIFEST_DIR", "/policies")

    try:
        return load_policy_manifest(policy_name, manifest_dir)
    except Exception as e:
        raise RuntimeError(
            f"Failed to load policy manifest for '{policy_name}': {e}"
        ) from e
