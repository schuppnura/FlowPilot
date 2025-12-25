# Delegation Architecture for FlowPilot

## Overview

FlowPilot implements a delegation system that allows travelers to delegate workflow execution authority to travel agents and AI agents, with support for multi-level delegation chains (traveler → agent → AI agent).

## Architecture Components

### 1. Delegation API Service (`flowpilot-delegation-api`)

A new service that manages delegation relationships and maintains a delegation graph.

**Responsibilities:**
- Create, read, update, delete delegation relationships
- Maintain delegation graph (who can act on behalf of whom)
- Validate delegation chains
- Provide delegation queries for authorization decisions

**Graph Structure:**
```
traveler (user) --delegates_to--> travel_agent (user)
traveler (user) --delegates_to--> ai_agent (service)
travel_agent (user) --delegates_to--> ai_agent (service)
```

**Key Endpoints:**
- `POST /v1/delegations` - Create a delegation
- `GET /v1/delegations/{delegation_id}` - Get delegation details
- `GET /v1/delegations?principal_id={id}` - List delegations for a principal
- `GET /v1/delegations?delegate_id={id}` - List delegations to a delegate
- `GET /v1/delegations/validate` - Validate if delegation chain exists
- `DELETE /v1/delegations/{delegation_id}` - Revoke delegation

### 3. Integration with AuthZ API

The authz-api queries the delegation-api to prepare OPA. OPA policies then check if a delegation chain exists.
If a request is denied due to something missing in the delegation chain, OPA and the autz-api need to feed back the exact reason for deny.


## Delegation Data Model

### Delegation Object

```json
{
  "delegation_id": "d_abc123",
  "principal_id": "700c733c-b51b-4c03-a151-660e5b1cc91a",  // Traveler
  "delegate_id": "agent_flowpilot_1",                      // Travel Agent or AI Agent
  "delegate_type": "user" | "agent",
  "workflow_id": "w_xyz789",                               // Optional: scope to specific workflow
  "scope": ["execute", "view"],                            // What can be delegated
  "created_at": "2025-12-21T10:00:00Z",
  "expires_at": "2026-12-21T10:00:00Z",                    // Optional expiration
  "status": "active" | "revoked" | "expired"
}
```

### Delegation Chain Resolution

When checking if `ai_agent` can act on behalf of `traveler`:

1. Direct: `traveler --delegates_to--> ai_agent` ✓
2. Indirect: `traveler --delegates_to--> travel_agent --delegates_to--> ai_agent` ✓

The delegation-api resolves these chains automatically.

## Service Integration

### Domain Services API → Delegation API

When a workflow is created:
```python
# In domain-services-api after workflow creation
delegation_api.create_delegation(
    principal_id=owner_sub,
    delegate_id="agent-runner",  # AI agent
    workflow_id=workflow_id,
    scope=["execute"]
)
```

### AuthZ API → Delegation API

Before evaluating OPA policy:
```python
# In authz-api before OPA evaluation
delegation_result = delegation_api.validate_delegation(
    principal_id=principal_user["id"],
    delegate_id=agent_sub,
    workflow_id=workflow_id  # Optional: check workflow-specific delegation
)

if not delegation_result["valid"]:
    return {"decision": "deny", "reason_codes": ["delegation.missing"]}
```

## MacOS App UI Design

### New "Delegations" Pane

**Location:** New tab/section in the main window

**Features:**

1. **My Delegations** (Outgoing)
   - List of people/services I've delegated to
   - Show: Delegate name, workflow scope, status, actions (revoke)
   - Add button: "Delegate to Travel Agent" / "Delegate to AI Agent"

2. **Delegations to Me** (Incoming)
   - List of people who delegated to me (if user is a travel agent)
   - Show: Principal name, workflow scope, status

3. **Delegation Creation Dialog**
   - Select delegate type: Travel Agent (from list) or AI Agent
   - Select workflow scope: All workflows or specific workflow
   - Select permissions: Execute, View, etc.
   - Optional: Set expiration date
   - Create button

**UI Mockup:**
```
┌─────────────────────────────────────────┐
│ Delegations                              │
├─────────────────────────────────────────┤
│                                         │
│ My Delegations                          │
│ ┌─────────────────────────────────────┐ │
│ │ Travel Agent: John Smith            │ │
│ │ Scope: All workflows                │ │
│ │ Status: Active                      │ │
│ │ [Revoke]                            │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ AI Agent: FlowPilot Agent           │ │
│ │ Scope: Trip to Paris (w_xyz789)    │ │
│ │ Status: Active                      │ │
│ │ [Revoke]                            │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ [+ Delegate to Travel Agent]           │
│ [+ Delegate to AI Agent]               │
│                                         │
└─────────────────────────────────────────┘
```

## Implementation Phases

### Phase 1: Basic Delegation API (In-Memory)
- Simple in-memory graph storage
- CRUD operations for delegations
- Basic chain resolution
- Integration with authz-api

### Phase 2: MacOS App UI
- Delegation pane
- Create delegation dialog
- List and revoke delegations
- Visual delegation chain display

### Phase 3: ***REMOVED*** Integration (Optional)
- Migrate from in-memory to ***REMOVED***
- Leverage ***REMOVED***'s built-in ReBAC capabilities
- More complex delegation rules

### Phase 4: Advanced Features
- Delegation expiration
- Conditional delegations (time-based, cost-based)
- Delegation audit log
- Multi-level delegation visualization

## Security Considerations

1. **Delegation Validation:**
   - Only workflow owners can create delegations
   - Delegations are validated before every authorization check
   - Revoked delegations are immediately effective

2. **Scope Limitation:**
   - Delegations can be scoped to specific workflows
   - Prevents over-broad delegation

3. **Audit Trail:**
   - All delegation operations are logged
   - Track who delegated what to whom and when

4. **Expiration:**
   - Delegations can have expiration dates
   - Automatic cleanup of expired delegations

## Example Delegation Scenarios

### Scenario 1: Direct Delegation
```
Traveler (Carlo) → AI Agent
- Carlo creates a trip
- Delegates execution to AI Agent
- AI Agent can execute workflow items on Carlo's behalf
```

### Scenario 2: Two-Level Delegation
```
Traveler (Carlo) → Travel Agent (John) → AI Agent
- Carlo delegates to John (travel agent)
- John delegates to AI Agent
- AI Agent can execute on Carlo's behalf via John
```

### Scenario 3: Workflow-Specific Delegation
```
Traveler (Carlo) → AI Agent (only for workflow w_xyz789)
- Carlo delegates to AI Agent for specific trip
- AI Agent can only execute that specific workflow
- Other workflows require separate delegation
```

## API Design Details

### Create Delegation

```http
POST /v1/delegations
Authorization: Bearer <user_token>
Content-Type: application/json

{
  "delegate_id": "agent-runner",
  "delegate_type": "agent",
  "workflow_id": "w_xyz789",  // Optional: null for all workflows
  "scope": ["execute"],
  "expires_at": "2026-12-21T10:00:00Z"  // Optional
}
```

Response:
```json
{
  "delegation_id": "d_abc123",
  "principal_id": "700c733c-b51b-4c03-a151-660e5b1cc91a",
  "delegate_id": "agent-runner",
  "delegate_type": "agent",
  "workflow_id": "w_xyz789",
  "scope": ["execute"],
  "status": "active",
  "created_at": "2025-12-21T10:00:00Z",
  "expires_at": "2026-12-21T10:00:00Z"
}
```

### Validate Delegation

```http
GET /v1/delegations/validate?principal_id={id}&delegate_id={id}&workflow_id={id}
Authorization: Bearer <service_token>
```

Response:
```json
{
  "valid": true,
  "delegation_chain": [
    {
      "delegation_id": "d_abc123",
      "principal_id": "700c733c-b51b-4c03-a151-660e5b1cc91a",
      "delegate_id": "agent-runner",
      "direct": true
    }
  ],
  "reason": "Direct delegation found"
}
```

## Next Steps

1. **Create delegation-api service structure**
2. **Implement in-memory graph storage**
3. **Add delegation validation to authz-api**
4. **Update OPA policy to check delegation**
5. **Build MacOS app delegation UI**
6. **Add delegation creation from workflow creation flow**

