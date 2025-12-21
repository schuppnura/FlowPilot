# Delegation Implementation Plan

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         MacOS App                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Workflows   │  │ Delegations  │  │ Authorization│          │
│  │    Pane      │  │    Pane      │  │    Check     │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Domain Services │  │ Delegation API  │  │   AuthZ API     │
│      API        │  │                 │  │                 │
│                 │  │  - CRUD         │  │  - Evaluate     │
│  - Create       │  │  - Validate     │  │  - Check        │
│  - Execute      │  │  - Chain Res.   │  │    Delegation   │
└─────────────────┘  └─────────────────┘  └─────────────────┘
         │                    │                    │
         │                    │                    │
         └────────────────────┴────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Graph Storage  │
                    │                 │
                    │  Option A:      │
                    │  ***REMOVED*** (ReBAC)  │
                    │                 │
                    │  Option B:      │
                    │  In-Memory      │
                    │  (networkx)    │
                    └─────────────────┘
```

## Delegation Flow

### Scenario: Traveler → Travel Agent → AI Agent

```
1. Traveler (Carlo) creates workflow
   └─> Domain Services API creates workflow
       └─> Delegation API: Create delegation Carlo → AI Agent (optional)

2. Traveler delegates to Travel Agent (John)
   └─> MacOS App → POST /v1/delegations
       └─> Delegation API: Create delegation Carlo → John

3. Travel Agent delegates to AI Agent
   └─> MacOS App (as John) → POST /v1/delegations
       └─> Delegation API: Create delegation John → AI Agent

4. AI Agent executes workflow item
   └─> AI Agent API → Domain Services API
       └─> Domain Services API → AuthZ API
           └─> AuthZ API → Delegation API: Validate chain
               └─> Delegation API: Check Carlo → John → AI Agent
                   └─> Returns: valid=true, chain=[...]
           └─> AuthZ API → OPA: Evaluate policy (with delegation context)
               └─> OPA: Check delegation + policy conditions
                   └─> Returns: allow/deny
```

## Implementation Phases

### Phase 1: Delegation API Service (Week 1)

**Create new service:** `flowpilot-delegation-api`

**Structure:**
```
services/flowpilot-delegation-api/
├── main.py          # FastAPI app with endpoints
├── core.py          # Graph storage and delegation logic
├── Dockerfile
└── requirements.txt
```

**Core Features:**
- In-memory graph storage (using Python `networkx` or simple dict structure)
- CRUD operations for delegations
- Chain resolution (find path from principal to delegate)
- Validation endpoint

**Endpoints:**
```python
POST   /v1/delegations              # Create delegation
GET    /v1/delegations/{id}         # Get delegation
GET    /v1/delegations              # List delegations (filtered)
DELETE /v1/delegations/{id}         # Revoke delegation
GET    /v1/delegations/validate     # Validate delegation chain
```

**Data Model:**
```python
@dataclass
class Delegation:
    delegation_id: str
    principal_id: str      # Who is delegating
    delegate_id: str       # Who receives delegation
    delegate_type: str     # "user" or "agent"
    workflow_id: Optional[str]  # None = all workflows
    scope: List[str]       # ["execute", "view"]
    status: str           # "active", "revoked", "expired"
    created_at: datetime
    expires_at: Optional[datetime]
```

### Phase 2: Integration with AuthZ API (Week 1-2)

**Modify:** `services/flowpilot-authz-api/main.py`

**Changes:**
1. Add delegation-api client
2. Before OPA evaluation, check delegation:
   ```python
   # In post_evaluate()
   delegation_result = delegation_api.validate_delegation(
       principal_id=principal_user["id"],
       delegate_id=agent_sub,
       workflow_id=workflow_id
   )
   
   if not delegation_result["valid"]:
       return {
           "decision": "deny",
           "reason_codes": ["delegation.missing"],
           "advice": [{"type": "error", "message": "No valid delegation found"}]
       }
   ```

3. Pass delegation context to OPA:
   ```python
   opa_input["delegation"] = {
       "valid": delegation_result["valid"],
       "chain": delegation_result.get("chain", [])
   }
   ```

**Update OPA Policy:**
```rego
# In auto_book.rego
allow {
    input.delegation.valid == true
    has_consent
    within_cost_limit
    sufficient_advance
    acceptable_risk
}

deny {
    not input.delegation.valid
    reason := "delegation.missing"
}
```

### Phase 3: MacOS App UI (Week 2-3)

**New Files:**
```
flowpilot-project/Flowpilot-app/
├── DelegationView.swift          # Main delegation pane
├── DelegationListView.swift      # List of delegations
├── CreateDelegationView.swift    # Create delegation dialog
└── DelegationApiClient.swift     # API client for delegation-api
```

**UI Components:**

1. **DelegationView** (New Tab)
   - Tab bar item: "Delegations"
   - Shows two sections:
     - "My Delegations" (outgoing)
     - "Delegations to Me" (incoming, if user is agent)

2. **DelegationRow** (List item)
   - Shows: Delegate name, scope, status
   - Action button: "Revoke"

3. **CreateDelegationSheet** (Modal)
   - Delegate type picker: Travel Agent / AI Agent
   - Travel Agent picker: Dropdown of available agents
   - Workflow scope: All workflows / Specific workflow
   - Permissions: Execute, View (checkboxes)
   - Expiration: Optional date picker
   - Create button

**Integration Points:**
- After workflow creation: Show option to delegate
- In workflow detail: Show delegation status
- In delegation list: Link to workflows

### Phase 4: Domain Services Integration (Week 2)

**Modify:** `services/flowpilot-domain-services-api/core.py`

**Optional Auto-Delegation:**
```python
# After workflow creation
def create_workflow_from_template(...):
    workflow = # ... create workflow ...
    
    # Optional: Auto-create delegation to AI agent
    if auto_delegate_to_ai:
        delegation_api.create_delegation(
            principal_id=owner_sub,
            delegate_id="agent-runner",
            workflow_id=workflow_id,
            scope=["execute"]
        )
    
    return workflow
```

### Phase 5: ***REMOVED*** Migration (Optional, Future)

**When to migrate:**
- If delegation graph becomes large
- Need complex delegation rules
- Want ***REMOVED***'s built-in ReBAC features

**Migration Steps:**
1. Replace in-memory graph with ***REMOVED*** API calls
2. Use ***REMOVED***'s relation API for delegations
3. Leverage ***REMOVED***'s permission resolution
4. Update manifest to include delegation relations

## Technical Decisions

### Graph Storage: In-Memory vs ***REMOVED***

**In-Memory (Phase 1):**
- ✅ Simple to implement
- ✅ No external dependencies
- ✅ Fast for demo scale
- ❌ Lost on restart (add persistence later)
- ❌ Doesn't scale to production

*****REMOVED*** (Future):**
- ✅ Production-ready
- ✅ Built-in ReBAC
- ✅ Persistence
- ✅ Complex permission resolution
- ❌ More complex setup
- ❌ Additional service to manage

**Recommendation:** Start with in-memory, migrate to ***REMOVED*** when needed.

### Delegation Scope

**Options:**
1. **Workflow-specific:** Delegation applies to one workflow
2. **All workflows:** Delegation applies to all user's workflows
3. **Time-limited:** Delegation expires after date
4. **Conditional:** Delegation based on conditions (cost, etc.)

**Phase 1:** Support workflow-specific and all workflows
**Phase 2:** Add time-limited delegations
**Phase 3:** Add conditional delegations

### Chain Resolution Algorithm

**Simple BFS (Breadth-First Search):**
```python
def find_delegation_chain(principal_id, delegate_id, workflow_id=None):
    # Find path: principal_id → ... → delegate_id
    # Returns: List of delegation IDs forming the chain
    # Or: None if no chain exists
```

**Optimization:** Cache resolved chains for performance.

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

### Validate Delegation

```http
GET /v1/delegations/validate?principal_id={id}&delegate_id={id}&workflow_id={id}
Authorization: Bearer <service_token>
```

Response:
```json
{
  "valid": true,
  "chain": [
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

1. **Authorization:**
   - Only workflow owners can create delegations
   - Only delegation creators can revoke
   - Service-to-service calls require service tokens

2. **Validation:**
   - Delegations validated on every authorization check
   - Revoked delegations immediately invalid
   - Expired delegations automatically rejected

3. **Audit:**
   - Log all delegation operations
   - Track who created/revoked what
   - Store delegation history

## Testing Strategy

1. **Unit Tests:**
   - Graph storage operations
   - Chain resolution algorithm
   - Validation logic

2. **Integration Tests:**
   - Delegation API endpoints
   - AuthZ API integration
   - End-to-end delegation flow

3. **UI Tests:**
   - Create delegation
   - List delegations
   - Revoke delegation
   - Visual delegation chain display

## Success Metrics

- ✅ Traveler can delegate to travel agent
- ✅ Travel agent can delegate to AI agent
- ✅ Two-level delegation chain works
- ✅ Authorization checks respect delegation
- ✅ MacOS app shows delegation UI
- ✅ Delegations can be revoked
- ✅ Workflow-specific delegations work

## Next Steps

1. **Create delegation-api service skeleton**
2. **Implement in-memory graph storage**
3. **Add validation endpoint**
4. **Integrate with authz-api**
5. **Update OPA policy**
6. **Build MacOS UI**
7. **Test end-to-end flow**

