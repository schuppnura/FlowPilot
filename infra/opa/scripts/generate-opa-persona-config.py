#!/usr/bin/env python3
"""Generate OPA persona_config.json from manifest.yaml

This script ensures OPA and Python services use the same persona configuration
by generating the JSON data file from the single source of truth (manifest.yaml).

Usage:
    python3 scripts/generate-opa-persona-config.py [policy_name]
    
    policy_name: Optional policy name (default: travel)
"""

import sys
import json
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Warning: PyYAML not found. Attempting to use ruamel.yaml...", file=sys.stderr)
    try:
        from ruamel.yaml import YAML
        yaml_loader = YAML(typ='safe')
        
        class YAMLCompat:
            @staticmethod
            def safe_load(stream):
                return yaml_loader.load(stream)
        
        yaml = YAMLCompat()
    except ImportError:
        print("Error: Neither PyYAML nor ruamel.yaml is installed.", file=sys.stderr)
        print("Please install one of them:", file=sys.stderr)
        print("  pip3 install --user pyyaml", file=sys.stderr)
        print("  OR", file=sys.stderr)
        print("  pip3 install --user ruamel.yaml", file=sys.stderr)
        sys.exit(1)


def generate_opa_persona_config(policy_name: str = "travel"):
    """Generate OPA persona_config.json from manifest.yaml
    
    Args:
        policy_name: Policy name (default: travel)
    """
    # Paths - support both local dev and Docker container contexts
    script_dir = Path(__file__).parent
    
    # Check if we're in Docker (/tmp/generate.py with policies at /tmp/policies)
    if script_dir == Path("/tmp"):
        policies_dir = Path("/tmp/policies")
    else:
        # Local development context
        base_dir = script_dir.parent
        policies_dir = base_dir / "infra" / "opa" / "policies"
    
    policy_dir = policies_dir / policy_name
    manifest_path = policy_dir / "manifest.yaml"
    output_path = policy_dir / "persona_config.json"
    
    # Validate manifest exists
    if not manifest_path.exists():
        print(f"Error: Manifest not found at {manifest_path}", file=sys.stderr)
        sys.exit(1)
    
    # Load manifest
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = yaml.safe_load(f)
    except Exception as e:
        print(f"Error: Failed to load manifest: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Extract persona_config
    persona_config = manifest.get("persona_config", {})
    if not persona_config:
        print(f"Error: No persona_config section in manifest", file=sys.stderr)
        sys.exit(1)
    
    # Build OPA data structure
    # OPA needs: persona_titles (for lookup) and delegation_personas (for policy rules)
    opa_data = {
        "persona_titles": persona_config.get("persona_titles", []),
        "persona_statuses": persona_config.get("persona_statuses", []),
    }
    
    # Generate delegation_personas mapping (action -> list of delegatable personas)
    # OPA policy.rego line 218 expects: persona_config.delegation_personas.execute
    delegation_personas = {"read": [], "update": [], "execute": [], "delete": []}
    
    # Generate invitation_personas mapping (action -> list of invitable personas)
    # These are personas that can be invited (read-only access)
    invitation_personas = {"read": [], "update": []}
    
    for persona in opa_data["persona_titles"]:
        if not isinstance(persona, dict):
            continue
        
        title = persona.get("title")
        if not title:
            continue
        
        allowed_actions = persona.get("allowed-actions", [])
        
        # Personas that can be delegated to (execute actions)
        if persona.get("can-be-delegated-to", False):
            for action in allowed_actions:
                if action in delegation_personas:
                    delegation_personas[action].append(title)
        
        # Personas that can be invited (read-only access)
        if persona.get("can-be-invited", False):
            for action in allowed_actions:
                if action in invitation_personas:
                    invitation_personas[action].append(title)
    
    opa_data["delegation_personas"] = delegation_personas
    opa_data["invitation_personas"] = invitation_personas
    
    # Write JSON file
    # Note: JSON does not support comments, so we cannot include generation metadata in the file
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(opa_data, f, indent=2, ensure_ascii=False)
        print(f"✓ Generated {output_path}")
        print(f"  Persona titles: {len(opa_data['persona_titles'])}")
        print(f"  Persona statuses: {len(opa_data['persona_statuses'])}")
        print(f"  Delegation personas for 'execute': {delegation_personas['execute']}")
        print(f"  Invitation personas for 'read': {invitation_personas['read']}")
    except Exception as e:
        print(f"Error: Failed to write JSON: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    policy = sys.argv[1] if len(sys.argv) > 1 else "travel"
    generate_opa_persona_config(policy)
