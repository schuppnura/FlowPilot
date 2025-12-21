# Delegation Architecture Proposal for FlowPilot

## Executive Summary

This document proposes a delegation system architecture that enables:
- **Traveler → Travel Agent** (direct delegation)
- **Traveler → AI Agent** (direct delegation)  
- **Traveler → Travel Agent → AI Agent** (chained delegation) - **Most interesting use case**

The architecture introduces a **Delegation API** service that maintains a graph database of delegation relationships, integrates with the existing AuthZ API and OPA PDP, and provides a macOS app UI for delegation management.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         macOS App                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Workflows   │  │ Delegations  │  │ Authorization│         │
│  │    Pane      │  │    Pane      │  │    Check     │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Domain Services │  │ Delegation API  │  │   AuthZ API     │
│      API        │  │                 │  │                 │
│                 │  │  - CRUD         │  │  - Evaluate     │
│  - Create       │  │  - Validate     │  │  - Check        │
│  - Execute      │  │  - Chain Res.   │  │    Delegation  │
└─────────────────┘  └─────────────────┘  └─────────────────┘
         │                    │                    │
         │                    │                    │
         └────────────────────┴────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Graph Storage  │
                    │                 │
                    │  In-Memory      │
                    │  (networkx)     │
                    │                 │
                    │  Future: ***REMOVED***  │
                    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │      OPA        │
                    │   (PDP)         │
                    └─────────────────┘
```

## Core Components

### 1. Delegation API Service (`flowpilot-delegation-api`)

**Purpose**: Maintains delegation graph and provides delegation validation services.

**Responsibilities**:
- Create, read, update, delete delegation relationships
- Maintain in-memory graph database (using `networkx` for demo, ***REMOVED*** for production)
- Validate delegation chains (direct and transitive)
- Provide delegation queries for authorization decisions

**Graph Structure**:
```
traveler (user) --delegates_to--> travel_agent (user)
traveler (user) --delegates_to--> ai_agent (service)
travel_agent (user) --delegates_to--> ai_agent (service)
```

**Key Endpoints**:
- `POST /v1/delegations` - Create a delegation
- `GET /v1/delegations/{delegation_id}` - Get delegation details
- `GET /v1/delegations?principal_id={id}` - List delegations for a principal
- `GET /v1/delegations?delegate_id={id}` - List delegations to a delegate
- `GET /v1/delegations/validate?principal_id={id}&delegate_id={id}&workflow_id={id}` - Validate delegation chain
- `DELETE /v1/delegations/{delegation_id}` - Revoke delegation

### 2. Integration with AuthZ API

**Flow**:
```
Request → AuthZ API
    ↓
1. Extract principal from AuthZEN context
    ↓
2. Query delegation-api: "Can agent X act on behalf of principal Y?"
    ↓
3. If delegation exists → Evaluate OPA policy (with delegation context)
    ↓
4. If no delegation → Deny immediately
```

**Implementation**: AuthZ API calls delegation-api before OPA evaluation to check if a valid delegation chain exists.

### 3. OPA Policy Updates

The OPA policy needs to be aware of delegation context:

```rego
# Check if delegation exists (provided by authz-api)
allow {
    input.delegation.valid == true
    has_consent
    within_cost_limit
    sufficient_advance
    acceptable_risk
}

# Deny if no valid delegation
deny {
    not input.delegation.valid
    reason := "delegation.missing"
}
```

### 4. macOS App UI

**New "Delegations" Pane**:
- **My Delegations** (Outgoing): List of people/services I've delegated to
- **Delegations to Me** (Incoming): List of people who delegated to me (if user is a travel agent)
- **Create Delegation Dialog**: Select delegate, workflow scope, permissions, expiration

## Data Model

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

1. **Direct**: `traveler --delegates_to--> ai_agent` ✓
2. **Indirect**: `traveler --delegates_to--> travel_agent --delegates_to--> ai_agent` ✓

The delegation-api resolves these chains automatically using graph traversal (BFS).

## Service Integration Details

### Domain Services API → Delegation API

**Optional**: When a workflow is created, auto-create delegation to AI agent:

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

**Required**: Before evaluating OPA policy:

```python
# In authz-api before OPA evaluation
delegation_result = delegation_api.validate_delegation(
    principal_id=principal_user["id"],
    delegate_id=agent_sub,
    workflow_id=workflow_id  # Optional: check workflow-specific delegation
)

if not delegation_result["valid"]:
    return {
        "decision": "deny",
        "reason_codes": ["delegation.missing"],
        "advice": [{"type": "error", "message": "No valid delegation found"}]
    }

# Pass delegation context to OPA
opa_input["delegation"] = {
    "valid": delegation_result["valid"],
    "chain": delegation_result.get("chain", [])
}
```

## Implementation Phases

### Phase 1: Delegation API Service (Week 1)

**Create new service**: `services/flowpilot-delegation-api/`

**Structure**:
```
services/flowpilot-delegation-api/
├── main.py          # FastAPI app with endpoints
├── core.py          # Graph storage and delegation logic
├── Dockerfile
└── requirements.txt
```

**Core Features**:
- In-memory graph storage (using Python `networkx`)
- CRUD operations for delegations
- Chain resolution (find path from principal to delegate)
- Validation endpoint

**Dependencies**:
- `fastapi` - REST API framework
- `networkx` - Graph database
- `pydantic` - Data validation
- Shared libraries: `security.py`, `api_logging.py`, `utils.py`

### Phase 2: Integration with AuthZ API (Week 1-2)

**Modify**: `services/flowpilot-authz-api/main.py` and `core.py`

**Changes**:
1. Add delegation-api client
2. Before OPA evaluation, check delegation
3. Pass delegation context to OPA

### Phase 3: OPA Policy Updates (Week 2)

**Modify**: `infra/opa/policies/auto_book.rego`

**Changes**:
- Add delegation validation check
- Update allow/deny rules to include delegation context

### Phase 4: macOS App UI (Week 2-3)

**New Files**:
```
flowpilot-project/Flowpilot-app/
├── DelegationView.swift          # Main delegation pane
├── DelegationListView.swift      # List of delegations
├── CreateDelegationView.swift    # Create delegation dialog
└── DelegationApiClient.swift     # API client for delegation-api
```

**UI Components**:
1. **DelegationView** (New Tab in ContentView)
2. **DelegationRow** (List item)
3. **CreateDelegationSheet** (Modal)

### Phase 5: Domain Services Integration (Week 2)

**Optional**: Auto-create delegation to AI agent when workflow is created.

## Technical Decisions

### Graph Storage: In-Memory vs ***REMOVED***

**Phase 1: In-Memory (networkx)**
- ✅ Simple to implement
- ✅ No external dependencies
- ✅ Fast for demo scale
- ❌ Lost on restart (add persistence later)
- ❌ Doesn't scale to production

**Future: ***REMOVED*****
- ✅ Production-ready
- ✅ Built-in ReBAC
- ✅ Persistence
- ✅ Complex permission resolution
- ❌ More complex setup

**Recommendation**: Start with in-memory, migrate to ***REMOVED*** when needed.

### Delegation Scope

**Phase 1**: Support workflow-specific and all workflows
**Phase 2**: Add time-limited delegations
**Phase 3**: Add conditional delegations

### Chain Resolution Algorithm

**Simple BFS (Breadth-First Search)**:
```python
def find_delegation_chain(principal_id, delegate_id, workflow_id=None):
    # Find path: principal_id → ... → delegate_id
    # Returns: List of delegation IDs forming the chain
    # Or: None if no chain exists
```

**Optimization**: Cache resolved chains for performance.

## API Contracts

### Create Delegation

```http
POST /v1/delegations
Authorization: Bearer <user_token>
Content-Type: application/json

{
  "delegate_id": "agent-runner",
  "delegate_type": "agent",
  "workflow_id": "w_xyz789",  // null for all workflows
  "scope": ["execute"],
  "expires_at": "2026-12-21T10:00:00Z"  // optional
}
```

**Response**:
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

**Response**:
```json
{
  "valid": true,
  "delegation_chain": [
    {
      "delegation_id": "d_abc123",
      "principal_id": "700c733c-...",
      "delegate_id": "agent-runner",
      "direct": true
    }
  ],
  "reason": "Direct delegation found"
}
```

## Security Considerations

1. **Authorization**:
   - Only workflow owners can create delegations
   - Only delegation creators can revoke
   - Service-to-service calls require service tokens

2. **Validation**:
   - Delegations validated on every authorization check
   - Revoked delegations immediately invalid
   - Expired delegations automatically rejected

3. **Audit**:
   - Log all delegation operations
   - Track who created/revoked what
   - Store delegation history

## Example Delegation Scenarios

### Scenario 1: Direct Delegation
```
Traveler (Carlo) → AI Agent
- Carlo creates a trip
- Delegates execution to AI Agent
- AI Agent can execute workflow items on Carlo's behalf
```

### Scenario 2: Two-Level Delegation (Most Interesting)
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

## Next Steps

1. **Create delegation-api service skeleton**
2. **Implement in-memory graph storage**
3. **Add validation endpoint**
4. **Integrate with authz-api**
5. **Update OPA policy**
6. **Build macOS UI**
7. **Test end-to-end flow**

## Success Metrics

- ✅ Traveler can delegate to travel agent
- ✅ Travel agent can delegate to AI agent
- ✅ Two-level delegation chain works
- ✅ Authorization checks respect delegation
- ✅ macOS app shows delegation UI
- ✅ Delegations can be revoked
- ✅ Workflow-specific delegations work

