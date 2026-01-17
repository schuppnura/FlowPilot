# Restructure Persona Titles in Policy Manifest
## Problem
Persona titles are currently defined as simple lists, but they should have rich metadata similar to persona attributes: title, description, can-be-invited, can-be-delegated-to, and allowed-actions.
## Current State
manifest.yaml has:
* `allowed_titles`: Simple list of strings
* `delegation_personas`: Actions mapped to lists of persona strings
## Proposed Changes
1. Restructure `persona_titles` as a list of objects with metadata:
    * `title`: Persona title (e.g., "traveler")
    * `description`: Human-readable description
    * `can-be-invited`: Boolean (invitation personas)
    * `can-be-delegated-to`: Boolean (delegation personas)
    * `allowed-actions`: List of allowed actions (read, update, execute, delete)
2. Update persona_config.py to parse new structure:
    * Add `get_persona_titles()` function
    * Add `get_delegatable_personas()` function
    * Maintain backward compatibility with old API where possible
3. Update OPA policies to use new persona metadata if needed
4. Update any code that reads persona_config (user-profile-api, authz-api, etc.)
## Impact
* Code can now query persona metadata (e.g., "can this persona be delegated?")
* Cleaner, more structured configuration
* Single source of truth for persona capabilities
