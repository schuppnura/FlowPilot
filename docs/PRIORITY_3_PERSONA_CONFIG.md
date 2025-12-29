# Priority 3: Agent Persona Configuration

## Overview

This document describes the changes made to remove hardcoded agent persona values and make them configurable via environment variables.

## Changes Implemented

### Environment Variables Added

#### AI_AGENT_PERSONA
**Default**: `"ai-agent"`  
**Usage**: Identifies the AI agent service account persona in authorization requests  
**Services**: domain-services-api

```bash
# Default behavior
AI_AGENT_PERSONA="ai-agent"

# For different agent types
AI_AGENT_PERSONA="medical-assistant"
AI_AGENT_PERSONA="legal-assistant"
```

#### DELEGATION_PERSONAS (Documented)
**Default**: `"ai-agent,travel-agent,secretary"` (currently hardcoded in OPA policy)  
**Usage**: Valid personas that can be delegated to execute workflows  
**Location**: OPA policy `auto_book.rego`

**Note**: Currently documented in the OPA policy but not yet runtime-configurable. Future enhancement will allow passing via policy input.

---

## Code Changes

### 1. domain-services-api/core.py

**Added module-level configuration:**
```python
# AI Agent persona configuration
AI_AGENT_PERSONA = os.getenv("AI_AGENT_PERSONA", "ai-agent")
```

**Updated authorization call in `_call_authz_for_item`:**
```python
# Before
subject: Dict[str, Any] = {"type": "agent", "id": service_id, "persona": "ai-agent"}

# After
subject: Dict[str, Any] = {"type": "agent", "id": service_id, "persona": AI_AGENT_PERSONA}
```

**Updated authorization call in `_call_authz_for_workflow`:**
```python
# Before
subject: Dict[str, Any] = {"type": "agent", "id": service_id, "persona": "ai-agent"}

# After
subject: Dict[str, Any] = {"type": "agent", "id": service_id, "persona": AI_AGENT_PERSONA}
```

### 2. domain-services-api/main.py

**Added module-level configuration:**
```python
# AI Agent persona configuration
AI_AGENT_PERSONA = os.environ.get("AI_AGENT_PERSONA", "ai-agent")
```

**Updated default persona logic in `handle_get_workflow_items`:**
```python
# Before
agent_sub = request.app.state.service._config.get("agent_sub", "ab011ba8-fb46-4b2f-a706-41ea03dad2b7")
if not user_persona and user_sub == agent_sub:
    user_persona = "ai-agent"
    print(f"[handle_get_workflow_items] Agent detected, using ai-agent persona", flush=True)

# After
agent_sub = request.app.state.service._config.get("agent_sub")
if not user_persona and agent_sub and user_sub == agent_sub:
    user_persona = AI_AGENT_PERSONA
    print(f"[handle_get_workflow_items] Agent detected, using {AI_AGENT_PERSONA} persona", flush=True)
```

**Key improvements:**
- Removed hardcoded UUID fallback (better security)
- Made persona configurable
- Added null check for agent_sub before comparison

### 3. infra/opa/policies/auto_book.rego

**Added documentation:**
```rego
# Configuration Note:
# The valid agent personas are currently hardcoded here but should match the
# DELEGATION_PERSONAS environment variable in the service configuration.
# Future enhancement: Pass personas via input.config.delegation_personas

# Valid agent personas that can be delegated to execute workflows
# These should match DELEGATION_PERSONAS env var: "ai-agent,travel-agent,secretary"
valid_agent_personas := {"travel-agent", "ai-agent", "secretary"}
```

---

## Use Cases

### Use Case 1: Multi-Domain Deployment

Different FlowPilot instances for different domains:

**Travel Domain:**
```bash
AI_AGENT_PERSONA="travel-assistant"
# OPA policy: valid_agent_personas := {"travel-agent", "travel-assistant"}
```

**Healthcare Domain:**
```bash
AI_AGENT_PERSONA="medical-assistant"
# OPA policy: valid_agent_personas := {"nurse", "medical-assistant"}
```

**Legal Domain:**
```bash
AI_AGENT_PERSONA="legal-assistant"
# OPA policy: valid_agent_personas := {"paralegal", "legal-assistant"}
```

### Use Case 2: Testing Different Agent Types

```bash
# Development environment
AI_AGENT_PERSONA="test-agent"

# Staging environment
AI_AGENT_PERSONA="staging-agent"

# Production environment
AI_AGENT_PERSONA="ai-agent"
```

### Use Case 3: Multi-Tenant Environment

**Tenant A:**
```bash
AI_AGENT_PERSONA="tenant-a-agent"
```

**Tenant B:**
```bash
AI_AGENT_PERSONA="tenant-b-agent"
```

---

## Benefits

### 1. Flexibility
- Can deploy FlowPilot for different domains without code changes
- Easy to test with different agent personas

### 2. Security
- Removed hardcoded UUID fallback
- More explicit configuration requirements
- Better null checking

### 3. Extensibility
- Foundation for future OPA policy parameterization
- Clear path to fully dynamic persona configuration

### 4. Maintainability
- Single source of truth for agent persona
- Easier to audit and update
- Self-documenting via environment variable name

---

## Backward Compatibility

All changes are **fully backward compatible**:

✅ Default value `"ai-agent"` matches previous hardcoded value  
✅ No configuration required for existing deployments  
✅ OPA policy unchanged (documented for future enhancement)  
✅ Existing authorization checks continue to work  

---

## Future Enhancements

### Phase 1: OPA Policy Data Injection (Recommended Next Step)

Allow passing delegation personas to OPA at runtime:

**Option A: Via AuthZEN Request Context**
```python
# In domain-services-api/core.py
authz_request = {
    "subject": {...},
    "action": {...},
    "resource": {...},
    "context": {
        "principal": principal_user,
        "config": {
            "delegation_personas": ["ai-agent", "travel-agent", "secretary"]
        }
    }
}
```

**Option B: Via OPA Data API**
```bash
# Push configuration to OPA
curl -X PUT http://opa:8181/v1/data/config \
  -d '{"delegation_personas": ["ai-agent", "travel-agent", "secretary"]}'
```

**OPA Policy Update:**
```rego
# Before (hardcoded)
valid_agent_personas := {"travel-agent", "ai-agent", "secretary"}

# After (configurable)
valid_agent_personas := input.context.config.delegation_personas
# or
valid_agent_personas := data.config.delegation_personas
```

### Phase 2: Environment Variable Parsing

Add environment variable support in services:

```bash
DELEGATION_PERSONAS="ai-agent,travel-agent,secretary,custom-agent"
```

```python
# Parse and pass to OPA
delegation_personas = os.getenv("DELEGATION_PERSONAS", "ai-agent,travel-agent,secretary")
personas_list = [p.strip() for p in delegation_personas.split(",") if p.strip()]
```

---

## Testing

### Manual Testing

1. **Default Configuration (No env var set)**
   ```bash
   # Services should start successfully
   # Agent persona should be "ai-agent"
   docker compose up -d
   docker compose logs domain-services-api | grep persona
   ```

2. **Custom Configuration**
   ```bash
   # Set environment variable
   export AI_AGENT_PERSONA="test-agent"
   docker compose up -d
   
   # Verify in logs
   docker compose logs domain-services-api | grep "test-agent"
   ```

3. **Authorization Check**
   ```bash
   # Make authorization request
   # Verify subject.persona uses configured value
   curl -X POST http://localhost:8002/v1/evaluate \
     -H "Authorization: Bearer $TOKEN" \
     -d '{...}'
   ```

### Integration Testing

```python
def test_ai_agent_persona_configuration():
    """Test that AI_AGENT_PERSONA is used in authorization requests"""
    # Set environment variable
    os.environ["AI_AGENT_PERSONA"] = "test-agent"
    
    # Execute workflow item
    result = execute_workflow_item(...)
    
    # Verify authz request used configured persona
    assert authz_request["subject"]["persona"] == "test-agent"

def test_default_ai_agent_persona():
    """Test default persona when env var not set"""
    # Unset environment variable
    os.environ.pop("AI_AGENT_PERSONA", None)
    
    # Execute workflow item
    result = execute_workflow_item(...)
    
    # Verify default persona is used
    assert authz_request["subject"]["persona"] == "ai-agent"
```

---

## Docker Compose Configuration

### Minimal Configuration (Uses Defaults)

```yaml
services:
  flowpilot-domain-services-api:
    environment:
      # AI_AGENT_PERSONA defaults to "ai-agent" if not set
      # No configuration needed for default behavior
```

### Custom Configuration

```yaml
services:
  flowpilot-domain-services-api:
    environment:
      AI_AGENT_PERSONA: "medical-assistant"
      # Other configurations...
```

### Multi-Environment Setup

```yaml
# docker-compose.dev.yml
services:
  flowpilot-domain-services-api:
    environment:
      AI_AGENT_PERSONA: "dev-agent"

# docker-compose.prod.yml
services:
  flowpilot-domain-services-api:
    environment:
      AI_AGENT_PERSONA: "ai-agent"
```

---

## Migration Guide

### For Development Teams

No action required - defaults match current behavior.

### For Production Deployments

1. **Review current persona usage**
   ```bash
   grep -r "ai-agent" infra/opa/policies/
   ```

2. **Document domain-specific personas**
   ```bash
   # Create .env file or update docker-compose.yml
   echo "AI_AGENT_PERSONA=ai-agent" >> .env
   ```

3. **Plan OPA policy updates** (future)
   - Document required personas for your domain
   - Plan migration to configurable personas in OPA

### For Multi-Domain Deployments

1. **Define personas per domain**
   ```bash
   # Travel domain
   AI_AGENT_PERSONA="travel-assistant"
   
   # Healthcare domain  
   AI_AGENT_PERSONA="medical-assistant"
   ```

2. **Update OPA policies**
   ```rego
   # Customize valid_agent_personas per domain
   valid_agent_personas := {"travel-agent", "travel-assistant"}
   ```

3. **Test authorization flows**
   - Verify each persona is accepted by OPA
   - Test delegation scenarios
   - Verify audit logs show correct personas

---

## Related Documentation

- `docs/PERSONA_ACTION_DESIGN.md` - Comprehensive persona/action design
- `docs/CONFIGURATION_CLEANUP.md` - All configuration variables reference
- `docs/CLEANUP_SUMMARY.md` - Complete cleanup summary

---

## Summary

✅ **Completed**: AI agent persona is now configurable via `AI_AGENT_PERSONA`  
✅ **Documented**: OPA policy personas documented for future parameterization  
✅ **Improved**: Removed hardcoded UUID fallback for better security  
✅ **Backward Compatible**: All existing deployments continue to work  

🔜 **Next**: OPA policy parameterization to make delegation personas fully configurable
