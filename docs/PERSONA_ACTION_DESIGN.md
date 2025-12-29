# Persona and Action Authorization Design

## Current State Analysis

### Current Hardcoded Values

1. **Agent Personas** (in OPA policy `auto_book.rego`):
   ```rego
   valid_agent_personas := {"travel-agent", "ai-agent", "secretary"}
   ```

2. **Service Agent Persona** (in `domain-services-api/core.py`):
   ```python
   subject: Dict[str, Any] = {"type": "agent", "id": service_id, "persona": "ai-agent"}
   ```

3. **Default Agent Persona** (in `domain-services-api/main.py`):
   ```python
   if not user_persona and user_sub == agent_sub:
       user_persona = "ai-agent"
   ```

### Current Actions

**Implemented:**
- `execute` - Execute workflow items (booking, purchasing)
- `read` - View workflows and workflow items

**Mentioned but Not Fully Implemented:**
- `create` - Create new resources
- `write` - Modify existing resources
- `delete` - Remove resources

**Need to Consider:**
- `revoke_delegation` - Revoke delegation grants
- `revoke_invitation` - Revoke invitations (future feature)
- `change` - Modify workflow items (alternative to `write`)

---

## Design Principles

### 1. Separation of Concerns

**Three Layers:**
1. **Application Layer** - Services and business logic
2. **Policy Layer** - OPA/Rego policies  
3. **Configuration Layer** - Environment variables and config files

### 2. Resource-Action-Persona Model

```
WHO (Persona) can perform WHAT (Action) on WHICH (Resource)
```

**Examples:**
- `travel-agent` can `execute` on `workflow_item`
- `ai-agent` can `execute` on `workflow_item`
- `traveler` can `read` on `workflow`
- `owner` can `delete` on `delegation`
- `admin` can `revoke_delegation` on `delegation`

### 3. Extensibility

The system should support:
- Adding new personas without code changes
- Adding new actions without code changes
- Different personas per resource type
- Role-based and attribute-based rules

---

## Proposed Architecture

### Configuration Structure

```yaml
# config/personas.yaml (or environment variables)
personas:
  # Agent personas - can act on behalf of others
  agents:
    - ai-agent
    - travel-agent
    - secretary
    - medical-assistant
  
  # User personas - act on own resources
  users:
    - traveler
    - patient
    - employee
  
  # Administrative personas
  admins:
    - admin
    - security-officer

# config/actions.yaml
actions:
  workflow_item:
    - execute
    - read
    - write
    - delete
  
  workflow:
    - create
    - read
    - write
    - delete
  
  delegation:
    - create
    - read
    - revoke
    - list
  
  invitation:
    - create
    - read
    - revoke
    - accept
```

### Environment Variable Approach (Simpler)

For immediate implementation without complex config files:

```bash
# Agent personas that can be delegated to
AGENT_PERSONAS="ai-agent,travel-agent,secretary"

# Default persona for service accounts
SERVICE_AGENT_PERSONA="ai-agent"

# Actions requiring delegation
DELEGATION_REQUIRED_ACTIONS="execute,write,delete"

# Actions available without delegation (owner only)
OWNER_ONLY_ACTIONS="create,read"

# Administrative actions
ADMIN_ACTIONS="revoke_delegation,manage_users"
```

---

## Generalized Action Handling

### Action Categories

#### 1. Data Actions (CRUD)
- `create` - Create new resource
- `read` - View resource
- `write` / `update` / `change` - Modify resource
- `delete` / `remove` - Delete resource

#### 2. Workflow Actions
- `execute` - Execute workflow item (booking, purchasing)
- `approve` - Approve pending item
- `reject` - Reject item

#### 3. Delegation Actions
- `create_delegation` / `delegate` - Grant delegation
- `revoke_delegation` - Revoke delegation
- `view_delegations` - List delegations

#### 4. Invitation Actions (Future)
- `create_invitation` / `invite` - Invite user
- `revoke_invitation` - Revoke invitation
- `accept_invitation` - Accept invitation
- `decline_invitation` - Decline invitation

### Action-Resource Matrix

| Action | workflow | workflow_item | delegation | invitation |
|--------|----------|---------------|------------|------------|
| create | ✓ | ✗ | ✓ | ✓ |
| read | ✓ | ✓ | ✓ | ✓ |
| write/change | ✓ | ✓ | ✗ | ✗ |
| delete | ✓ | ✓ | ✗ | ✗ |
| execute | ✗ | ✓ | ✗ | ✗ |
| revoke | ✗ | ✗ | ✓ | ✓ |
| accept | ✗ | ✗ | ✗ | ✓ |

---

## Implementation Strategy

### Phase 1: Environment Variables (Priority 3 - Immediate)

**Add these environment variables:**

```bash
# Agent personas configuration
AGENT_PERSONAS="ai-agent,travel-agent,secretary"
SERVICE_AGENT_PERSONA="ai-agent"

# User personas configuration  
USER_PERSONAS="traveler,patient,employee"

# Admin personas configuration
ADMIN_PERSONAS="admin,security-officer"
```

**Update locations:**
1. `domain-services-api/core.py` - Use `SERVICE_AGENT_PERSONA`
2. `domain-services-api/main.py` - Use `SERVICE_AGENT_PERSONA`
3. `infra/opa/policies/auto_book.rego` - Make configurable or document

### Phase 2: Policy Parameterization (Future)

OPA policies can accept data from external sources:

```rego
# Instead of hardcoded:
valid_agent_personas := {"travel-agent", "ai-agent", "secretary"}

# Use data injection:
valid_agent_personas := data.config.agent_personas
```

**Methods:**
1. **OPA Bundle** - Package policies with data files
2. **OPA Data API** - Push data via REST API
3. **Environment Variables** - Pass via policy input

### Phase 3: Action Mapping (Future)

Create action aliases to support different naming conventions:

```python
# config/action_aliases.py
ACTION_ALIASES = {
    "change": "write",
    "update": "write",
    "modify": "write",
    "remove": "delete",
    "revoke_delegation": "delete",  # Revoke is delete on delegation resource
    "revoke_invitation": "delete",   # Revoke is delete on invitation resource
}
```

---

## Handling Specific Operations

### 1. Revoke Delegation

**Resource**: `delegation`  
**Action**: `delete` or `revoke`  
**Authorization Logic:**
- Owner (principal) can always revoke their own delegations
- Delegate cannot revoke delegation granted to them
- Admin can revoke any delegation

**OPA Policy Snippet:**
```rego
allow_revoke_delegation if {
  input.action.name == "delete"
  input.resource.type == "delegation"
  # Owner can revoke
  input.subject.id == input.resource.properties.principal_id
}

allow_revoke_delegation if {
  input.action.name == "delete"
  input.resource.type == "delegation"
  # Admin can revoke
  input.subject.persona == "admin"
}
```

### 2. Revoke Invitation (Future)

**Resource**: `invitation`  
**Action**: `delete` or `revoke`  
**Authorization Logic:**
- Inviter can revoke invitation
- Invitee can decline (different from revoke)
- Admin can revoke any invitation

**OPA Policy Snippet:**
```rego
allow_revoke_invitation if {
  input.action.name == "delete"
  input.resource.type == "invitation"
  # Inviter can revoke
  input.subject.id == input.resource.properties.inviter_id
}
```

### 3. Delete Workflow Item

**Resource**: `workflow_item`  
**Action**: `delete`  
**Authorization Logic:**
- Owner can delete items in their workflows
- Delegated agents typically cannot delete (depends on policy)
- May require special permission

**OPA Policy Snippet:**
```rego
allow_delete_workflow_item if {
  input.action.name == "delete"
  input.resource.type == "workflow_item"
  # Owner only
  input.subject.id == input.resource.owner_id
}
```

### 4. Change/Update Workflow Item

**Resource**: `workflow_item`  
**Action**: `write` or `change`  
**Authorization Logic:**
- Owner can always change
- Delegated agents may be allowed with proper scope
- May require re-authorization if cost changes significantly

**OPA Policy Snippet:**
```rego
allow_change_workflow_item if {
  input.action.name == "write"
  input.resource.type == "workflow_item"
  # Owner or delegated with write permission
  authorized_for_write
}
```

---

## Recommended Action Naming Convention

### Standard CRUD (Preferred)
- `create` - Create new resources
- `read` - View resources  
- `write` - Modify resources (covers update/change)
- `delete` - Remove resources (covers revoke for delegations)

### Domain-Specific Extensions
- `execute` - Execute workflow actions
- `approve` - Approve items
- `reject` - Reject items
- `accept` - Accept invitations (different from approve)
- `decline` - Decline invitations

### Why This Works

**Advantages:**
1. **Consistency** - Standard CRUD pattern
2. **Simplicity** - Fewer actions to manage
3. **Flexibility** - Resource type + action clarifies intent
4. **Compatibility** - Aligns with RESTful APIs

**Examples:**
- `delete` on `delegation` = revoke delegation
- `delete` on `invitation` = revoke invitation  
- `write` on `workflow_item` = change/update workflow item
- `delete` on `workflow_item` = delete workflow item

---

## Migration Path

### Step 1: Add Environment Variables (Now)
```bash
AGENT_PERSONAS="ai-agent,travel-agent,secretary"
SERVICE_AGENT_PERSONA="ai-agent"
```

### Step 2: Update Service Code (Now)
Replace hardcoded `"ai-agent"` with `os.getenv("SERVICE_AGENT_PERSONA", "ai-agent")`

### Step 3: Document OPA Configuration (Now)
Add comments to Rego policies explaining persona configuration

### Step 4: Add Action Aliases (Later)
Create mapping for common action variations

### Step 5: Policy Parameterization (Later)
Move persona lists from Rego to external data

---

## Configuration Examples

### Development Environment
```bash
# Permissive for testing
AGENT_PERSONAS="ai-agent,travel-agent,secretary,test-agent"
SERVICE_AGENT_PERSONA="ai-agent"
ALLOWED_ACTIONS="create,read,write,delete,execute"
```

### Production Environment
```bash
# Restrictive for security
AGENT_PERSONAS="ai-agent,travel-agent"
SERVICE_AGENT_PERSONA="ai-agent"
ALLOWED_ACTIONS="read,execute"  # No write/delete via API
```

### Multi-Tenant Environment
```bash
# Different personas per tenant
TENANT_A_AGENT_PERSONAS="medical-assistant,nurse"
TENANT_A_SERVICE_PERSONA="medical-assistant"

TENANT_B_AGENT_PERSONAS="travel-agent,secretary"
TENANT_B_SERVICE_PERSONA="travel-agent"
```

---

## Best Practices

### 1. Persona Design
- Keep persona names descriptive and role-based
- Avoid user-specific personas (e.g., "john-doe")
- Use organizational roles (e.g., "travel-agent", "nurse")

### 2. Action Design
- Prefer standard CRUD actions
- Add domain actions only when CRUD doesn't fit
- Document what each action means per resource type

### 3. Policy Design
- Start with fail-closed (deny by default)
- Use explicit allow rules
- Provide clear reason codes
- Test with various persona combinations

### 4. Configuration Management
- Use environment variables for simple configs
- Use config files for complex rules
- Version control all configuration
- Document all options

---

## Testing Strategy

### Test Matrix

| Persona | Action | Resource | Expected Result |
|---------|--------|----------|-----------------|
| owner | read | workflow | ALLOW |
| owner | execute | workflow_item | ALLOW (with consent) |
| owner | delete | workflow | ALLOW |
| travel-agent | read | workflow | ALLOW (with delegation) |
| travel-agent | execute | workflow_item | ALLOW (with delegation + consent) |
| travel-agent | delete | workflow | DENY |
| ai-agent | execute | workflow_item | ALLOW (with delegation + consent) |
| ai-agent | delete | delegation | DENY |
| admin | delete | delegation | ALLOW |

### Integration Tests

```python
def test_revoke_delegation_as_owner():
    # Owner should be able to revoke their delegation
    assert can_revoke_delegation(principal="owner-1", delegation_id="d-123")

def test_revoke_delegation_as_delegate():
    # Delegate cannot revoke delegation granted to them
    assert not can_revoke_delegation(principal="agent-1", delegation_id="d-123")

def test_delete_workflow_item_as_owner():
    # Owner can delete their workflow items
    assert can_delete_workflow_item(principal="owner-1", item_id="i-123")

def test_delete_workflow_item_as_agent():
    # Agent cannot delete items (policy-dependent)
    assert not can_delete_workflow_item(principal="agent-1", item_id="i-123")
```

---

## Summary

### Immediate Implementation (Priority 3)
1. Add `AGENT_PERSONAS` environment variable
2. Add `SERVICE_AGENT_PERSONA` environment variable  
3. Replace hardcoded `"ai-agent"` in service code
4. Document persona configuration in OPA policies

### Future Enhancements
1. Action aliases for common variations
2. Policy parameterization via OPA data
3. Resource-specific action validation
4. Multi-tenant persona configuration

### Key Decisions
- **Use standard CRUD actions** where possible
- **Resource + Action** determines authorization (not action alone)
- **Personas are configurable** via environment variables
- **Policies remain explicit** - no magic action mapping initially

This design provides a clear path forward while maintaining backward compatibility and allowing future flexibility.
