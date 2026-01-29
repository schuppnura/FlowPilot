# FlowPilot User Profile API - Persona Business Logic
#
# Business logic for persona management.
# Follows the same pattern as delegation_core.py
#
# Responsibilities:
# - Create, read, update, delete personas
# - Validate persona attributes
# - Enforce business rules (max personas per user, allowed titles, etc.)

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from utils import read_env_string
import persona_config

# ============================================================================
# Configuration
# ============================================================================

# Load allowed persona titles from policy manifest (single source of truth)
policy_name = read_env_string("POLICY_NAME", "travel")
manifest_dir = read_env_string("POLICY_MANIFEST_DIR", "/policies")

try:
    ALLOWED_PERSONA_TITLES = set(persona_config.get_allowed_persona_titles(policy_name, manifest_dir))
    print(f"Loaded {len(ALLOWED_PERSONA_TITLES)} allowed persona titles from manifest: {sorted(ALLOWED_PERSONA_TITLES)}", flush=True)
except Exception as e:
    # Fail fast - manifest is the only source of truth
    raise RuntimeError(
        f"Failed to load persona configuration from manifest at {manifest_dir}/{policy_name}/manifest.yaml. "
        f"Error: {e}. Ensure the policy manifest exists and contains a valid 'persona_config' section."
    ) from e

# Load allowed persona statuses from policy manifest (single source of truth)
try:
    ALLOWED_PERSONA_STATUSES = set(persona_config.get_allowed_persona_statuses(policy_name, manifest_dir))
    print(f"Loaded {len(ALLOWED_PERSONA_STATUSES)} allowed persona statuses from manifest: {sorted(ALLOWED_PERSONA_STATUSES)}", flush=True)
except Exception as e:
    # Fail fast - manifest is the only source of truth
    raise RuntimeError(
        f"Failed to load persona statuses from manifest at {manifest_dir}/{policy_name}/manifest.yaml. "
        f"Error: {e}. Ensure the policy manifest exists and contains 'persona_config.persona_statuses'."
    ) from e

# Maximum personas per user
try:
    MAX_PERSONAS_PER_USER = int(read_env_string("MAX_PERSONAS_PER_USER"))
except (ValueError, KeyError):
    MAX_PERSONAS_PER_USER = 5

# Default persona expiry (days)
try:
    PERSONA_DEFAULT_EXPIRY_DAYS = int(read_env_string("PERSONA_DEFAULT_EXPIRY_DAYS"))
except (ValueError, KeyError):
    PERSONA_DEFAULT_EXPIRY_DAYS = 365


# ============================================================================
# Data Classes
# ============================================================================

@dataclass(frozen=True)
class Persona:
    """Persona data transfer object."""
    persona_id: str
    user_sub: str
    title: str
    scope: list[str]
    valid_from: str
    valid_till: str
    status: str
    created_at: str
    updated_at: str
    consent: bool
    autobook_price: int
    autobook_leadtime: int
    autobook_risklevel: int


# ============================================================================
# Business Logic Service
# ============================================================================

class PersonaService:
    """Business logic for persona management."""

    def __init__(self, personadb):
        """
        Initialize the persona service.
        
        Args:
            personadb: Persona database instance (PersonaDB)
        """
        self.personadb = personadb

    def create_persona(
        self,
        user_sub: str,
        title: str,
        scope: list[str] | None = None,
        valid_from: str | None = None,
        valid_till: str | None = None,
        status: str | None = None,
        **custom_attributes: Any,
    ) -> dict[str, Any]:
        """
        Create a new persona for a user.
        
        Args:
            user_sub: User subject ID
            title: Persona title
            scope: List of actions (defaults to [])
            valid_from: When persona becomes active (ISO 8601)
            valid_till: When persona expires (ISO 8601)
            status: Status (active, inactive, suspended, revoked). Defaults to "active" if not provided.
            **custom_attributes: Policy-specific attributes (dynamically loaded from manifest)
                Examples for travel policy: consent, autobook_price, autobook_leadtime, autobook_risklevel
                Examples for nursing policy: shift_type, certification_level, etc.
            
        Returns:
            Created persona dictionary
            
        Raises:
            ValueError: If validation fails
        """
        # Validate title
        if title not in ALLOWED_PERSONA_TITLES:
            raise ValueError(
                f"Invalid persona title '{title}'. Allowed: {', '.join(sorted(ALLOWED_PERSONA_TITLES))}"
            )

        # Validate status if provided
        if status is not None:
            if status not in ALLOWED_PERSONA_STATUSES:
                raise ValueError(f"Invalid status '{status}'. Allowed: {', '.join(sorted(ALLOWED_PERSONA_STATUSES))}")

        # Check max personas per user
        existing_personas = self.personadb.list_personas(user_sub)
        if len(existing_personas) >= MAX_PERSONAS_PER_USER:
            raise ValueError(
                f"Maximum {MAX_PERSONAS_PER_USER} personas per user. Delete an existing persona first."
            )

        # Note: Duplicate title check removed - database layer now enforces uniqueness
        # via composite document ID (user_sub_title) and returns existing persona if duplicate

        # Validate scope (can be empty list or None)
        if scope is None:
            scope = []

        # Apply defaults and coerce custom attributes from manifest
        # custom_attributes contains all policy-specific attributes passed by caller
        processed_attrs, validation_error = persona_config.apply_defaults_and_coerce_attributes(
            custom_attributes,
            policy_name=policy_name,
            manifest_dir=manifest_dir
        )
        
        if validation_error:
            raise ValueError(f"Attribute validation failed: {validation_error}")

        # Create persona in database with processed attributes
        # Build kwargs dynamically from processed attributes
        create_kwargs = {
            "user_sub": user_sub,
            "title": title,
            "scope": scope,
            "valid_from": valid_from,
            "valid_till": valid_till,
            "status": status,
        }
        
        # Add all processed custom attributes
        create_kwargs.update(processed_attrs)
        
        persona = self.personadb.create_persona(**create_kwargs)

        return persona

    def get_persona(self, persona_id: str, user_sub: str) -> dict[str, Any]:
        """
        Get a persona by ID.
        
        Args:
            persona_id: Persona ID
            user_sub: User subject ID (for ownership validation)
            
        Returns:
            Persona dictionary
            
        Raises:
            ValueError: If persona not found or access denied
        """
        persona = self.personadb.get_persona(persona_id)

        if not persona:
            raise ValueError(f"Persona {persona_id} not found")

        # Verify ownership
        if persona["user_sub"] != user_sub:
            raise ValueError(f"Access denied to persona {persona_id}")

        return persona

    def list_personas(
        self,
        user_sub: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List personas for a user.
        
        Args:
            user_sub: User subject ID
            status: Optional status filter
            
        Returns:
            List of persona dictionaries
        """
        return self.personadb.list_personas(user_sub, status=status)

    def update_persona(
        self,
        persona_id: str,
        user_sub: str,
        title: str | None = None,
        scope: list[str] | None = None,
        valid_from: str | None = None,
        valid_till: str | None = None,
        status: str | None = None,
        **custom_attributes: Any,
    ) -> dict[str, Any]:
        """
        Update a persona (partial update).
        
        Args:
            persona_id: Persona ID
            user_sub: User subject ID (for ownership validation)
            title: Optional new title
            scope: Optional new scope
            valid_from: Optional new valid_from
            valid_till: Optional new valid_till
            status: Optional new status
            **custom_attributes: Policy-specific attributes to update
                Only provide attributes you want to change.
                Examples: consent=True, autobook_price=1000, etc.
            
        Returns:
            Updated persona dictionary
            
        Raises:
            ValueError: If validation fails
        """
        # Verify ownership first and get existing persona
        existing_persona = self.get_persona(persona_id, user_sub)

        # Validate title if provided
        if title is not None and title not in ALLOWED_PERSONA_TITLES:
            raise ValueError(
                f"Invalid persona title '{title}'. Allowed: {', '.join(sorted(ALLOWED_PERSONA_TITLES))}"
            )

        # Validate status if provided
        if status is not None:
            if status not in ALLOWED_PERSONA_STATUSES:
                raise ValueError(f"Invalid status '{status}'. Allowed: {', '.join(sorted(ALLOWED_PERSONA_STATUSES))}")

        # Get attribute schema from manifest to determine which attributes exist
        attribute_schema = persona_config.get_persona_attribute_schema(
            policy_name=policy_name,
            manifest_dir=manifest_dir
        )
        
        # Build complete set of custom attributes (merge existing + updates)
        # Start with existing values for all attributes in the schema
        merged_attributes = {}
        for attr_name in attribute_schema.keys():
            # Start with existing value
            merged_attributes[attr_name] = existing_persona.get(attr_name)
            
            # Override with new value if provided in custom_attributes
            if attr_name in custom_attributes:
                merged_attributes[attr_name] = custom_attributes[attr_name]
        
        # Apply defaults and coerce ALL custom attributes (not just updated ones)
        # This ensures the complete persona remains valid after the update
        processed_attrs, validation_error = persona_config.apply_defaults_and_coerce_attributes(
            merged_attributes,
            policy_name=policy_name,
            manifest_dir=manifest_dir
        )
        
        if validation_error:
            raise ValueError(f"Attribute validation failed: {validation_error}")

        # Update persona in database with processed attributes
        # Build kwargs dynamically from processed attributes
        update_db_kwargs = {
            "persona_id": persona_id,
            "title": title,
            "scope": scope,
            "valid_from": valid_from,
            "valid_till": valid_till,
            "status": status,
        }
        
        # Add all processed custom attributes
        update_db_kwargs.update(processed_attrs)
        
        updated_persona = self.personadb.update_persona(**update_db_kwargs)


        if not updated_persona:
            raise ValueError(f"Failed to update persona {persona_id}")

        return updated_persona

    def delete_persona(self, persona_id: str, user_sub: str) -> bool:
        """
        Delete a persona.
        
        Args:
            persona_id: Persona ID
            user_sub: User subject ID (for ownership validation)
            
        Returns:
            True if deleted
            
        Raises:
            ValueError: If persona not found or access denied
        """
        # Verify ownership first
        self.get_persona(persona_id, user_sub)

        # Delete from database
        deleted = self.personadb.delete_persona(persona_id)

        if not deleted:
            raise ValueError(f"Failed to delete persona {persona_id}")

        return True

    def get_active_persona(self, user_sub: str) -> dict[str, Any] | None:
        """
        Get the active persona for a user.
        
        Args:
            user_sub: User subject ID
            
        Returns:
            Active persona dictionary or None if not found
        """
        return self.personadb.get_active_persona(user_sub)

    def get_persona_by_id_no_auth(self, persona_id: str) -> dict[str, Any] | None:
        """
        Get a persona by ID without ownership validation.
        
        This is used by service accounts (e.g., authz-api) to fetch
        any persona for authorization decisions.
        
        Args:
            persona_id: Persona ID
            
        Returns:
            Persona dictionary or None if not found
        """
        return self.personadb.get_persona(persona_id)

