# Persona Based Delegation

This guide explains FlowPilot's *delegation* model, including the data model, API operations, authorization rules, and technical implementation details.

## Overview

A *delegation* represents an explicit authorization relationship where a **principal** (resource owner) grants a **delegate** (user or agent) permission to act on their behalf within a specific context. Delegations are the core mechanism for implementing **relationship-based access control (ReBAC)** in FlowPilot's authorization model.

Delegations answer the fundamental authorization question: *"Is subject X allowed to act on behalf of principal Y in this context?"*

Rather than requiring direct ownership for every action, FlowPilot evaluates delegation chains to determine whether a delegate has been granted authority to perform actions on resources owned by another user.

### Key Concepts

- Delegations are **directional**: principal → delegate
- Delegations may be **workflow-scoped** (apply only to a specific workflow) or **unscoped** (apply to all workflows owned by the principal)
- Delegations have **explicit scope** (list of permitted actions: `read`, `execute`, etc.)
- Delegations have **explicit lifecycle**:
  - temporal validity (`expires_at`)
  - revocation status (`revoked_at`)
- Delegations support **transitive chains** (A → B → C) with configurable depth limits
- Delegations are **fail-closed**: if no delegation path with required permissions exists, authorization fails
- Delegations are **explicitly granted**: there are no implicit or inherited delegations

### Why Delegations Matter

Introducing delegations as a first-class authorization primitive enables several critical architectural properties:

#### 1. User-Managed Access (UMA)

Users control access to their own resources without requiring centralized administration:

- Resource owners explicitly grant and revoke delegations
- Delegation decisions are made closest to the source of authority
- No central administrator is required to manage who can act for whom
- Users maintain direct control over their authorization boundaries

#### 2. Separation of Concerns (ReBAC vs ABAC)

Delegation provides a clean separation between relationship-based and attribute-based authorization:

- **ReBAC (Delegation)**: Answers *"Can this delegate act for this principal?"*
- **ABAC (Policy)**: Answers *"Should this action be allowed based on attributes?"*

This separation ensures:
- Relationship validation happens before policy evaluation
- Policy logic remains business-focused, not relationship-focused
- Clear failure reasons: delegation failure vs policy denial

#### 3. Transitive Authority

Delegation chains enable realistic organizational scenarios:

- A user delegates to their assistant
- The assistant can sub-delegate (within granted scope) to other agents
- The entire chain is validated and auditable
- Depth limits prevent privilege amplification and unbounded traversal

#### 4. Explainable Authorization

Delegation chains provide transparency:

- Every authorization decision includes the delegation chain (if any)
- Users can see exactly who acted on their behalf
- Audit trails capture the complete delegation path
- Debugging authorization failures is straightforward

## Architectural Impact

FlowPilot delegations integrate seamlessly with personas and policies:

- **Personas** define *what* a user can do in a given role
- **Delegations** define *who* can act on someone's behalf
- **Policies** define *when* those actions should be allowed

Together, they provide:
- RBAC-like clarity through persona-based roles
- ReBAC-like flexibility through delegation relationships
- ABAC-like expressiveness through policy evaluation

At the same time, delegation-based authorization eliminates common access management antipatterns:

- No shared accounts or credentials
- No overprivileged service accounts
- No static permission assignment bottlenecks
- No implicit trust relationships

Instead, authorization becomes:
- explicit (delegations must be granted)
- decentralized (users manage their own delegations)
- auditable (delegation chains are tracked)
- time-bound (delegations expire)
- revocable (delegations can be revoked)

In FlowPilot, delegations place users at the center of access control, giving them explicit control over *who* can act on their behalf and *for how long*.

## Delegation Data Model

### Core Attributes

| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Unique database identifier for the delegation |
| `principal_id` | String | Owner's user ID (who is delegating authority) |
| `delegate_id` | String | Delegate's user ID or agent identifier (who receives authority) |
| `workflow_id` | String (optional) | Specific workflow ID to scope delegation (null = all workflows) |
| `scope` | Array[String] | List of permitted actions (e.g., `["read"]`, `["read", "execute"]`) |
| `expires_at` | ISO 8601 | Timestamp when delegation expires |
| `created_at` | ISO 8601 | Creation timestamp |
| `revoked_at` | ISO 8601 (optional) | Revocation timestamp (null = active) |

### Delegation Scopes

Delegations include an explicit `scope` field that defines which actions the delegate may perform:

| Action | Description |
|--------|-------------|
| `read` | Delegate can view/read resources |
| `update` | Delegate can modify/update resources |
| `execute` | Delegate can execute actions (e.g., book travel, run workflows) |
| `delete` | Delegate can delete resources |

**Scope Rules:**
- Default scope (when not specified): `["execute"]`
- Scope is always an array (supports multiple actions)
- Subdelegations cannot grant more permissions than the delegator has
- Action restrictions apply throughout the entire delegation chain
- Available actions are configured via `DELEGATION_ALLOWED_ACTIONS` environment variable

**Important:** The `scope` field defines what actions are *permitted* by the delegation relationship. Final authorization still requires policy (OPA) approval.

### Delegation States

A delegation path exists and grants permissions for an action if:
- A delegation chain exists from owner to delegate
- All delegations in the chain have `revoked_at` = `NULL` (not revoked)
- All delegations in the chain have `expires_at` in the future (not expired)
- All delegations match the requested workflow scope (if workflow-scoped)
- The chain is within the configured hop limit (max_depth)
- The requested action is in the intersection of all `scope` arrays in the chain

### Example Delegation Document

```json
{
  "id": 42,
  "principal_id": "carlo-uuid-1234",
  "delegate_id": "yannick-uuid-5678",
  "workflow_id": "workflow-abc-123",
  "scope": ["read", "execute"],
  "expires_at": "2026-01-23T15:30:00Z",
  "created_at": "2026-01-16T10:00:00Z",
  "revoked_at": null
}
```

This delegation grants Yannick the ability to read and execute actions on Carlo's workflow `workflow-abc-123` until January 23, 2026.

## Delegation Lifecycle

### Delegation-API

Purpose: Delegation relationship management and validation

Endpoints:

- `POST /v1/delegations` - Create delegation (fails with HTTP 400 if duplicate exists)
- `GET /v1/delegations` - List delegations (by principal_id or delegate_id)
- `DELETE /v1/delegations` - Revoke delegation
- `GET /v1/delegations/validate` - Validate delegation chain

Authorization:

- All endpoints require JWT authentication
- Delegation creation validates subdelegation permissions
- Service accounts (persona=service) can create delegations on behalf of owners

Code Location: `flowpilot-services/delegation-api/`

Validation Rules:

- `principal_id` ≠ `delegate_id` (cannot delegate to yourself)
- `expires_in_days` must be between `DELEGATION_MIN_EXPIRY_DAYS` (1) and `DELEGATION_MAX_EXPIRY_DAYS` (365)
- `scope` must only contain allowed actions defined in `DELEGATION_ALLOWED_ACTIONS` environment variable
- Subdelegations require valid parent delegation with sufficient scope

### Create

Delegations are created via the delegation-api POST /v1/delegations endpoint.

**Request:**
```http
POST /v1/delegations
Authorization: Bearer <user-token>
Content-Type: application/json

{
  "principal_id": "carlo-uuid-1234",
  "delegate_id": "yannick-uuid-5678",
  "workflow_id": "workflow-abc-123",
  "scope": ["read", "execute"],
  "expires_in_days": 7
}
```

**Response:**
```json
{
  "principal_id": "carlo-uuid-1234",
  "delegate_id": "yannick-uuid-5678",
  "workflow_id": "workflow-abc-123",
  "scope": ["read", "execute"],
  "expires_at": "2026-01-23T15:30:00Z",
  "created_at": "2026-01-16T10:00:00Z",
  "revoked_at": null
}
```

**Authorization:** 
- User must be authenticated
- For owner delegations: JWT `sub` must match `principal_id`
- For subdelegations: Delegator must have sufficient permissions to delegate

**Uniqueness Enforcement:**
The database enforces a unique constraint on `(principal_id, delegate_id, workflow_id, scope)`. This scope-aware uniqueness allows multiple delegation types to coexist between the same two users. For example:

- Carlo → Yannick with scope `["read"]` (invite relationship)
- Carlo → Yannick with scope `["read", "execute"]` (delegate relationship)

These are treated as **distinct delegation relationships** because they have different scopes, even though they connect the same principal and delegate.

Attempting to create a duplicate delegation (same principal, delegate, workflow, AND scope) raises a `ValueError` with HTTP 400 and a detailed error message:
```
Delegation from 'carlo-uuid' to 'yannick-uuid' for workflow 'workflow-123' with scope ["read", "execute"] already exists 
(expires: 2026-01-23T15:30:00Z). 
To modify the delegation, first revoke it using DELETE /v1/delegations, then create a new one. 
Or consider if the existing delegation already meets your needs.
```

**Idempotency Handling:**

The API is NOT idempotent by design. Duplicate creation attempts fail explicitly to:
- Prevent accidental expiry modifications without explicit revocation
- Ensure callers understand existing delegation state
- Maintain clear audit trail of delegation lifecycle (create → revoke → recreate)

For idempotent provisioning, scripts should implement their own logic by checking for existence first (GET /v1/delegations) or catching the 400 error and validating that the existing delegation meets requirements.

**Design Rationale:**

Treating delegations with different scopes as distinct relationships enables important use cases:

- **Invite vs Delegate**: An "invite" (read-only access) is fundamentally different from a "delegate" (read+execute authority)

- **Different Lifecycles**: Invites and delegations may have different expiration periods and revocation policies

- **Granular Control**: Users can independently manage read-only sharing and execution delegation

**Automatic Delegation Creation:**

When workflows are created via domain-services-api, the system automatically creates a delegation to the `agent-runner` service account:

```python
# Auto-created delegation for AI agent execution
delegation_response = requests.post(
    f"{DELEGATION_API_BASE_URL}/v1/delegations",
    json={
        "principal_id": owner_sub,
        "delegate_id": "agent-runner",
        "workflow_id": workflow_id,
        "scope": ["execute"],
        "expires_in_days": 30,
    },
    headers={"Authorization": f"Bearer {service_token}"}
)
```

This enables AI agents to execute workflows autonomously (if consent is granted).

Note: The domain-services-api handles duplicate delegation errors gracefully by catching the HTTP 400 response and logging it, allowing workflow creation to succeed even if the agent delegation already exists from a previous workflow.

### List

Users can list delegations they've granted (outgoing) or received (incoming):

**Outgoing delegations (principal_id):**
```http
GET /v1/delegations?principal_id=carlo-uuid
Authorization: Bearer <user-token>
```

**Incoming delegations (delegate_id):**
```http
GET /v1/delegations?delegate_id=yannick-uuid
Authorization: Bearer <user-token>
```

**Optional query parameters:**
- `workflow_id`: Filter by specific workflow
- `include_expired`: Include expired delegations (default: false)

**Response:**
```json
{
  "delegations": [
    {
      "principal_id": "carlo-uuid-1234",
      "delegate_id": "yannick-uuid-5678",
      "workflow_id": "workflow-abc-123",
      "scope": ["read", "execute"],
      "expires_at": "2026-01-23T15:30:00Z",
      "created_at": "2026-01-16T10:00:00Z",
      "revoked_at": null
    }
  ]
}
```

### Validate

Validate whether a delegation chain exists and determine which actions are available:

```http
GET /v1/delegations/validate?principal_id=carlo-uuid&delegate_id=yannick-uuid&workflow_id=workflow-123
Authorization: Bearer <service-token>
```

**Response (delegation exists):**
```json
{
  "delegation_chain": ["carlo-uuid-1234", "yannick-uuid-5678"],
  "delegated_actions": ["read", "execute"]
}
```

**Response (no delegation):**
```json
{
  "delegation_chain": [],
  "delegated_actions": []
}
```

**Interpretation:**
- If `delegated_actions` is non-empty, a valid delegation path exists with those permissions
- If `delegated_actions` is empty, no valid delegation path exists (or no permissions granted)

**Authorization:** This endpoint is typically called by service accounts (authz-api) during authorization evaluation.

### Revoke

Revoke a delegation:

```http
DELETE /v1/delegations
Authorization: Bearer <user-token>
Content-Type: application/json

{
  "principal_id": "carlo-uuid-1234",
  "delegate_id": "yannick-uuid-5678",
  "workflow_id": "workflow-abc-123"
}
```

**Response:**
```json
{
  "principal_id": "carlo-uuid-1234",
  "delegate_id": "yannick-uuid-5678",
  "workflow_id": "workflow-abc-123",
  "revoked": true
}
```

**Authorization:** JWT `sub` must match `principal_id` (only the principal can revoke their own delegations).

**Important:** Revocation sets `revoked_at` to the current timestamp. The delegation record remains in the database for audit purposes but is immediately invalidated.

**Revocation Cascade:**

When a delegation is revoked, all downstream delegations in the chain are **immediately and automatically invalidated**. This ensures security and prevents orphaned delegations.

**Example:**
- Chain: Carlo → Alexia → Martine → Sarah
- Alexia revokes delegation to Martine
- Result: Both Martine and Sarah **immediately lose access** to Carlo's resources
- Reason: The delegation chain is broken at Alexia → Martine, making all downstream paths invalid

**Technical Implementation:**
- Delegation validation uses graph traversal (BFS) to find paths
- If **any edge** in the path is revoked or expired, the **entire chain fails validation**
- No explicit cascade delete is needed - validation naturally fails for broken chains
- This ensures **real-time enforcement** of revocations without database triggers or batch jobs

**Key Properties:**
- **Atomic:** Revocation takes effect immediately on next authorization check
- **Transitive:** Downstream delegates automatically lose access
- **Auditable:** All delegation records remain in database with timestamps
- **Efficient:** No recursive delete operations needed

### Expiration

Delegations automatically expire based on the `expires_at` timestamp:

- Expired delegations are excluded from validation queries by default
- Expired delegations can be included in listing queries via `include_expired=true`
- No automatic cleanup process (expired records remain for audit)

**Configuration:**
```bash
DELEGATION_DEFAULT_EXPIRY_DAYS=7    # Default when expires_in_days not specified
DELEGATION_MIN_EXPIRY_DAYS=1        # Minimum allowed expiry
DELEGATION_MAX_EXPIRY_DAYS=365      # Maximum allowed expiry
```

## Authorization Scenarios

### Scenario 1: Direct Delegation (Travel Agent)

Context:

- Carlo (traveler) creates a workflow
- Carlo delegates to Yannick (travel-agent) with scope `["execute"]`
- Yannick executes Carlo's workflow

Authorization Flow:

1. Domain-services-api receives request with Yannick's token
2. Authz-api extracts `sub=yannick-uuid` from JWT
3. Authz-api queries delegation-api: `validate_delegation(principal_id=carlo-uuid, delegate_id=yannick-uuid, workflow_id=workflow-123)`
4. Delegation-api performs BFS graph search:
   - Finds direct edge: carlo-uuid → yannick-uuid
   - Validates: not revoked, not expired, workflow matches (or unscoped)
   - Returns: `{"delegation_chain": ["carlo-uuid", "yannick-uuid"], "delegated_actions": ["execute"]}`
5. Authz-api proceeds to OPA policy evaluation with delegation context (`delegated_actions` is non-empty)
6. OPA evaluates business rules (autobook preferences, risk limits, etc.)
7. Decision: **Allow** or **Deny** based on policy gates

### Scenario 2: Transitive Delegation (Office Manager → Assistant)

Context:

- Carlo (traveler) delegates to Martine (office-manager) with scope `["read", "execute"]`
- Martine sub-delegates to Sophie (booking-assistant) with scope `["execute"]`
- Sophie executes Carlo's workflow

Authorization Flow:

1. Domain-services-api receives request with Sophie's token
2. Authz-api queries delegation-api: `validate_delegation(principal_id=carlo-uuid, delegate_id=sophie-uuid, workflow_id=workflow-123)`
3. Delegation-api performs BFS graph search:
   - Finds path: carlo-uuid → martine-uuid → sophie-uuid
   - Edge 1 (carlo → martine): scope `["read", "execute"]`
   - Edge 2 (martine → sophie): scope `["execute"]`
   - Computes effective actions: `["read", "execute"] ∩ ["execute"] = ["execute"]`
   - Returns: `{"delegation_chain": ["carlo-uuid", "martine-uuid", "sophie-uuid"], "delegated_actions": ["execute"]}`
4. Authz-api proceeds to policy evaluation (`delegated_actions` contains "execute")
5. Decision: **Allow** or **Deny** based on policy

**Key Points:**
- Delegation chains are resolved transitively (up to `max_depth=5` by default)
- Effective permissions are the intersection of all edges in the chain
- If any edge is revoked or expired, the entire chain is invalid

### Scenario 3: Workflow-Scoped vs Unscoped Delegations

Context:

- Carlo creates two workflows: `workflow-A` and `workflow-B`
- Carlo delegates to Yannick with `workflow_id=workflow-A` (scoped delegation)
- Carlo also has an unscoped delegation to Martine (`workflow_id=null`)

Authorization Flow:

**Yannick executes workflow-A:**
- Delegation validation: ✓ (workflow-A matches delegation scope)
- Result: **Allowed** (if policy passes)

**Yannick executes workflow-B:**
- Delegation validation: ✗ (workflow-B does not match delegation scope)
- Result: **Denied** with reason: `delegation_invalid`

**Martine executes workflow-A or workflow-B:**
- Delegation validation: ✓ (unscoped delegation matches any workflow)
- Result: **Allowed** (if policy passes)

**Key Points:**
- Workflow-scoped delegations (`workflow_id` set) only apply to that specific workflow
- Unscoped delegations (`workflow_id` is null) apply to all workflows owned by the principal
- Both scoped and unscoped delegations are considered when validating (most permissive wins)

### Scenario 4: Subdelegation Validation

Context:

- Carlo delegates to Martine with scope `["read"]` (read-only)
- Martine attempts to sub-delegate to Sophie with scope `["execute"]`

Authorization Flow:

1. Martine calls `POST /v1/delegations` with:
   ```json
   {
     "principal_id": "carlo-uuid",
     "delegate_id": "sophie-uuid",
     "scope": ["execute"]
   }
   ```
2. Delegation-api extracts `sub=martine-uuid` from Martine's JWT
3. Delegation-api validates Martine's permissions:
   - Queries: `validate_delegation(principal_id=carlo-uuid, delegate_id=martine-uuid)`
   - Returns: `{"delegated_actions": ["read"]}`
4. Delegation-api checks: `["execute"] ⊆ ["read"]` → **False**
5. Result: **400 Bad Request** - "Cannot delegate [execute]. You only have [read] permissions."

**Key Points:**
- Subdelegations cannot grant more permissions than the delegator possesses
- Delegation creation automatically validates subdelegation constraints
- Service accounts (persona=service) bypass subdelegation validation (trusted system components)

### Scenario 5: Autonomous AI Agent (No Delegation Required)

Context:

- Carlo (traveler) has `autobook_consent=true` in his persona
- AI agent attempts to execute Carlo's workflow
- No delegation exists from Carlo to the AI agent

Authorization Flow:

1. AI-agent-api calls domain-services-api with service token
2. AuthZEN request: `subject.persona="ai-agent"`, `context.principal.id=carlo-uuid`
3. Authz-api queries delegation-api: `validate_delegation(principal_id=carlo-uuid, delegate_id=ai-agent)`
4. Delegation-api returns: `{"delegated_actions": []}` (no delegation exists)
5. Authz-api checks OPA policy gate: `has_consent`
   - Carlo's persona has `autobook_consent=true`
   - Policy allows autonomous execution without delegation
6. OPA evaluates business rules (cost limits, risk, leadtime, etc.)
7. Decision: **Allow** or **Deny** based on ABAC gates

**Key Points:**
- AI agents can operate autonomously when the user has granted consent via their persona
- Delegation is NOT required for autonomous execution (consent bypasses delegation check)
- This enables frictionless automation while maintaining user control


## Troubleshooting

### Delegation Not Found

Symptom: Authorization denied with `delegation_invalid` reason code

Causes:

1. Delegation never created
2. Delegation expired
3. Delegation revoked
4. Workflow-scoped delegation doesn't match requested workflow

Debug Steps:

1. Check if delegation exists:
   ```bash
   curl -H "Authorization: Bearer <user-token>" \
     "https://delegation-api/v1/delegations?principal_id=<principal-id>&delegate_id=<delegate-id>"
   ```

2. Validate delegation explicitly:
   ```bash
   curl -H "Authorization: Bearer <service-token>" \
     "https://delegation-api/v1/delegations/validate?principal_id=<principal-id>&delegate_id=<delegate-id>&workflow_id=<workflow-id>"
   ```

3. Check delegation-api logs:
   ```bash
   # Local
   docker compose logs -f flowpilot-delegation-api

   # GCP
   gcloud logging read "resource.labels.service_name=flowpilot-delegation-api" --limit=50
   ```

### Subdelegation Denied

Symptom: 400 Bad Request - "Cannot delegate [execute]. You only have [read] permissions."

Causes:

1. Delegator attempting to grant more permissions than they possess
2. Delegation chain has restricted scope

Resolution:

1. Check delegator's permissions:
   ```bash
   curl -H "Authorization: Bearer <service-token>" \
     "https://delegation-api/v1/delegations/validate?principal_id=<owner-id>&delegate_id=<delegator-id>"
   ```

2. Adjust requested scope to match delegator's permissions:
   ```json
   {
     "scope": ["read"]  // Instead of ["execute"]
   }
   ```

### Transitive Delegation Fails

Symptom: Delegation validation returns `valid: false` despite multi-hop chain existing

Causes:

1. One edge in the chain is expired or revoked
2. Effective permissions reduced to empty set via intersection
3. Chain exceeds `max_depth` limit (default: 5)

Debug Steps:

1. Check each edge in the chain individually:
   ```bash
   # Edge 1: A → B
   curl "https://delegation-api/v1/delegations?principal_id=A&delegate_id=B"

   # Edge 2: B → C
   curl "https://delegation-api/v1/delegations?principal_id=B&delegate_id=C"
   ```

2. Verify scope compatibility:
   - If A→B has scope `["read"]` and B→C has scope `["execute"]`
   - Effective scope: `["read"] ∩ ["execute"] = []` (empty, invalid)

3. Increase max_depth if needed (only if chain length is legitimate):
   ```python
   # In delegation_core.py
   path_result = self.graphdb.find_delegation_path(
       principal_id=principal_id,
       delegate_id=delegate_id,
       workflow_id=workflow_id,
       max_depth=10,  # Increase from default 5
   )
   ```

## Best Practices

1. **Use workflow-scoped delegations for sensitive operations** - Limit delegation scope to specific workflows when possible
2. **Set reasonable expiration times** - Default 7 days is appropriate for most use cases; avoid excessive expiry periods
3. **Revoke delegations when no longer needed** - Explicit revocation is better than waiting for expiration
4. **Use unscoped delegations sparingly** - Workflow-scoped delegations provide better security boundaries
5. **Monitor delegation chains** - Keep chains short (1-2 hops) to maintain clarity and auditability
6. **Grant minimal scope** - Start with `["read"]` and expand to `["execute"]` only when necessary
7. **Validate subdelegations carefully** - Ensure delegators understand they can only grant permissions they possess
8. **Use automatic delegation for AI agents** - Let domain-services-api create agent delegations automatically
9. **Include delegation context in audit logs** - Track delegation chains for security and compliance
10. **Test delegation scenarios thoroughly** - Verify both direct and transitive delegations work as expected
11. **Document delegation relationships** - Maintain clear documentation of who can delegate to whom
12. **Use service accounts for system delegations** - Service accounts bypass subdelegation validation (trusted components)
13. **Configure appropriate max_depth** - Default 5 hops is usually sufficient; increase only for specific use cases
14. **Handle duplicate creation errors gracefully** - The API enforces uniqueness by failing duplicate creates with HTTP 400; provisioning code should check for existence first or catch duplicate errors
15. **Implement idempotency in provisioning scripts** - Scripts should verify existing delegations match desired state before attempting to create new ones

## Related Documentation

- [Policy Development Guide](policies.md) - How OPA policies use delegation data
- [Persona Development Guide](personas.md) - How personas interact with delegations
- [Authorization Architecture](../architecture/authorization.md) - Overall authorization flow
- [API Reference: Delegation API](../api/delegation.md) - Full API specification
