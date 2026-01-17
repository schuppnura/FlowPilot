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
- Delegations are **fail-closed**: if no valid delegation exists, authorization fails
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
| `execute` | Delegate can execute actions (e.g., book travel, run workflows) |

**Scope Rules:**
- Default scope (when not specified): `["execute"]`
- Scope is always an array (supports multiple actions)
- Subdelegations cannot grant more permissions than the delegator has
- Action restrictions apply throughout the entire delegation chain

**Important:** The `scope` field defines what actions are *permitted* by the delegation relationship. Final authorization still requires policy (OPA) approval.

### Delegation States

A delegation is considered **valid** if:
- It exists in the database
- `revoked_at` is `NULL` (not revoked)
- `expires_at` is in the future (not expired)
- It matches the requested workflow scope (if workflow-scoped)
- A valid delegation chain exists within the configured hop limit (max_depth)

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

## Service Architecture

### Delegation-API

Purpose: Delegation relationship management and validation

Endpoints:

- `POST /v1/delegations` - Create delegation
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

### Storage Backend

FlowPilot uses **PostgreSQL** as the delegation graph database for both local development and production.

#### PostgreSQL Schema

```sql
CREATE TABLE delegations (
    id SERIAL PRIMARY KEY,
    principal_id TEXT NOT NULL,
    delegate_id TEXT NOT NULL,
    workflow_id TEXT,
    scope TEXT NOT NULL DEFAULT '["execute"]',
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(principal_id, delegate_id, workflow_id)
);

-- Indexes for efficient queries
CREATE INDEX idx_principal_id ON delegations(principal_id);
CREATE INDEX idx_delegate_id ON delegations(delegate_id);
CREATE INDEX idx_workflow_id ON delegations(workflow_id);
CREATE INDEX idx_expires_at ON delegations(expires_at);
CREATE INDEX idx_revoked_at ON delegations(revoked_at);
```

#### Connection Configuration

**Local Development (Docker Compose):**
```yaml
DB_HOST: postgres
DB_PORT: 5432
DB_NAME: flowpilot_delegations
DB_USER: postgres
DB_PASSWORD: <password>
```

**GCP Production (Cloud SQL):**
```yaml
DB_UNIX_SOCKET: /cloudsql/project-id:region:instance-name
DB_NAME: flowpilot_delegations
DB_USER: postgres
DB_PASSWORD: <password>
```

The database connection automatically uses unix sockets when `DB_UNIX_SOCKET` is set, otherwise falls back to TCP connection using `DB_HOST` and `DB_PORT`.

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
   - Returns: `{"valid": true, "delegation_chain": ["carlo-uuid", "yannick-uuid"], "delegated_actions": ["execute"]}`
5. Authz-api proceeds to OPA policy evaluation with delegation context
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
   - Returns: `{"valid": true, "delegation_chain": ["carlo-uuid", "martine-uuid", "sophie-uuid"], "delegated_actions": ["execute"]}`
4. Authz-api proceeds to policy evaluation
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
   - Returns: `{"valid": true, "delegated_actions": ["read"]}`
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
4. Delegation-api returns: `{"valid": false}` (no delegation exists)
5. Authz-api checks OPA policy gate: `has_consent`
   - Carlo's persona has `autobook_consent=true`
   - Policy allows autonomous execution without delegation
6. OPA evaluates business rules (cost limits, risk, leadtime, etc.)
7. Decision: **Allow** or **Deny** based on ABAC gates

**Key Points:**
- AI agents can operate autonomously when the user has granted consent via their persona
- Delegation is NOT required for autonomous execution (consent bypasses delegation check)
- This enables frictionless automation while maintaining user control

## Delegation Lifecycle

### 1. Creation

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

### 2. Listing

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

### 3. Validation

Validate whether a delegation chain exists:

```http
GET /v1/delegations/validate?principal_id=carlo-uuid&delegate_id=yannick-uuid&workflow_id=workflow-123
Authorization: Bearer <service-token>
```

**Response (valid delegation):**
```json
{
  "valid": true,
  "delegation_chain": ["carlo-uuid-1234", "yannick-uuid-5678"],
  "delegated_actions": ["read", "execute"]
}
```

**Response (invalid delegation):**
```json
{
  "valid": false,
  "delegation_chain": [],
  "delegated_actions": []
}
```

**Authorization:** This endpoint is typically called by service accounts (authz-api) during authorization evaluation.

### 4. Revocation

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

### 5. Expiration

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

## Technical Implementation

### Graph Traversal Algorithm

Delegation validation uses **Breadth-First Search (BFS)** to find delegation paths:

```python
def find_delegation_path(
    self,
    principal_id: str,
    delegate_id: str,
    workflow_id: str | None = None,
    max_depth: int = 5,
) -> dict[str, Any] | None:
    # BFS search with action tracking
    queue = [(principal_id, [principal_id], {"read", "execute"})]
    visited = {principal_id}
    valid_paths = []

    while queue and len(queue[0][1]) <= max_depth:
        current_id, path, path_actions = queue.pop(0)

        # Find outgoing delegations from current_id
        for edge in get_outgoing_delegations(current_id, workflow_id):
            next_id = edge.delegate_id
            edge_actions = set(edge.scope)

            # Compute effective actions (intersection)
            new_path_actions = path_actions & edge_actions

            if not new_path_actions:
                continue  # No valid actions, skip this edge

            if next_id == delegate_id:
                valid_paths.append({
                    "path": path + [next_id],
                    "delegated_actions": sorted(list(new_path_actions))
                })
                continue  # Found target, keep searching for better paths

            if next_id not in visited:
                visited.add(next_id)
                queue.append((next_id, path + [next_id], new_path_actions))

    # Return path with strongest permissions (prefer execute over read-only)
    if valid_paths:
        return max(valid_paths, key=lambda p: (
            1 if "execute" in p["delegated_actions"] else 0,
            -len(p["path"])
        ))

    return None
```

**Key Properties:**
- **BFS ensures shortest path**: Finds the delegation chain with fewest hops
- **Action intersection**: Effective permissions = intersection of all edges
- **Preference for stronger permissions**: Prefers paths with "execute" over "read-only"
- **Bounded depth**: Configurable `max_depth` prevents infinite loops and privilege amplification
- **Multiple valid paths**: Returns the strongest path if multiple exist

### Delegation vs Policy Evaluation Order

FlowPilot evaluates authorization in a specific order:

```
1. JWT Validation (security layer)
   ↓
2. Delegation Validation (ReBAC layer)
   → If subject == principal: SKIP (owner accessing own resources)
   → If subject != principal: REQUIRED (delegation must exist)
   → If delegation invalid: DENY immediately
   ↓
3. OPA Policy Evaluation (ABAC layer)
   → Evaluates business rules (consent, cost limits, risk, etc.)
   → Uses delegation context (chain, actions) in decision
   ↓
4. Authorization Decision (allow/deny + reason codes)
```

**Key Insight:** Delegation is a **prerequisite** for policy evaluation when subject ≠ principal. This ensures relationship validation happens before expensive policy computation.

### Integration with Authorization API

Authz-api consumes delegation-api during authorization evaluation:

```python
# In authz-api core.py
def evaluate_authorization(authzen_request: dict) -> dict:
    subject_id = authzen_request["subject"]["id"]
    principal_id = authzen_request["context"]["principal"]["id"]
    workflow_id = authzen_request["resource"].get("workflow_id")

    # Step 1: Delegation validation (ReBAC)
    if subject_id != principal_id:
        delegation_result = requests.get(
            f"{DELEGATION_API_BASE_URL}/v1/delegations/validate",
            params={
                "principal_id": principal_id,
                "delegate_id": subject_id,
                "workflow_id": workflow_id,
            },
            headers={"Authorization": f"Bearer {service_token}"}
        ).json()

        if not delegation_result.get("valid"):
            return {
                "decision": "deny",
                "context": {"reason_code": "delegation_invalid"}
            }

        # Add delegation context to OPA input
        authzen_request["context"]["delegation"] = delegation_result

    # Step 2: Policy evaluation (ABAC)
    opa_decision = requests.post(
        f"{OPA_URL}/v1/data/auto_book/allow",
        json={"input": authzen_request}
    ).json()

    return opa_decision
```

### Subdelegation Constraint Enforcement

When a user creates a delegation, the system validates they have sufficient permissions:

```python
# In delegation_core.py
def create_delegation(
    self,
    principal_id: str,
    delegate_id: str,
    scope: list[str] | None = None,
    delegator_id: str | None = None,
    ...
) -> dict[str, Any]:
    # Skip validation if:
    # 1. No delegator_id (system creating delegation)
    # 2. delegator_id == principal_id (owner delegating)
    # 3. Service account (trusted system component)
    if delegator_id and delegator_id != principal_id:
        # Validate delegator has permissions
        delegator_validation = self.validate_delegation(
            principal_id=principal_id,
            delegate_id=delegator_id,
            workflow_id=workflow_id,
        )

        if not delegator_validation.get("valid"):
            raise ValueError("You cannot delegate permissions you don't have")

        delegator_actions = set(delegator_validation.get("delegated_actions", []))
        requested_actions = set(scope) if scope else {"execute"}

        # Check subset constraint
        if not requested_actions.issubset(delegator_actions):
            raise ValueError(
                f"Cannot delegate {list(requested_actions)}. "
                f"You only have {list(delegator_actions)} permissions."
            )

    # Create delegation...
```

## Provisioning Delegations

### Manual Delegation Creation

Users create delegations via the API:

```bash
curl -X POST https://delegation-api/v1/delegations \
  -H "Authorization: Bearer <user-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "principal_id": "carlo-uuid",
    "delegate_id": "yannick-uuid",
    "workflow_id": "workflow-123",
    "scope": ["read", "execute"],
    "expires_in_days": 7
  }'
```

### Automatic Delegation (Workflow Creation)

Domain-services-api automatically creates delegations to `agent-runner` when workflows are created:

```python
# In domain-services-api after workflow creation
def create_workflow(workflow_data: dict) -> dict:
    # Create workflow...
    workflow = db.insert_workflow(workflow_data)

    # Auto-delegate to AI agent
    delegation_response = requests.post(
        f"{DELEGATION_API_BASE_URL}/v1/delegations",
        json={
            "principal_id": workflow["owner_sub"],
            "delegate_id": "agent-runner",
            "workflow_id": workflow["workflow_id"],
            "scope": ["execute"],
            "expires_in_days": 30,
        },
        headers={"Authorization": f"Bearer {service_token}"}
    )

    return workflow
```

### Provisioning Scripts

For testing and development, use the seed scripts:

**Local Development (Keycloak):**
```bash
python3 flowpilot-provisioning/seed_keycloak_users.py \
  --csv flowpilot-provisioning/users_seed.csv
```

**GCP Production (Firebase):**
```bash
python3 flowpilot-provisioning/seed_firebase_users.py \
  --profile-api-url=https://flowpilot-persona-api-737191827545.us-central1.run.app \
  --csv=flowpilot-provisioning/users_seed.csv
```

These scripts provision users, personas, and optionally delegations based on CSV configuration.

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

### Database Connection Issues

Symptom: 500 Internal Server Error - "could not connect to server"

Causes (GCP):

1. Cloud SQL instance not running
2. Unix socket path incorrect
3. Database user credentials invalid

Resolution:

1. Verify Cloud SQL instance:
   ```bash
   gcloud sql instances describe <instance-name>
   ```

2. Check environment variables:
   ```bash
   # In cloud-run-envs/delegation-api.yaml
   DB_UNIX_SOCKET: /cloudsql/project-id:region:instance-name
   DB_NAME: flowpilot_delegations
   DB_USER: postgres
   ```

3. Test connection manually:
   ```bash
   gcloud sql connect <instance-name> --user=postgres --database=flowpilot_delegations
   ```

Causes (Local):

1. PostgreSQL container not running
2. Wrong hostname or port

Resolution:

1. Check container status:
   ```bash
   docker compose ps postgres
   ```

2. Verify connectivity:
   ```bash
   docker compose exec flowpilot-delegation-api pg_isready -h postgres -p 5432
   ```

## Configuration

### Environment Variables

**Core Configuration:**
```bash
# Database connection
DB_HOST=postgres                          # PostgreSQL hostname (local)
DB_UNIX_SOCKET=/cloudsql/...             # Unix socket path (GCP Cloud SQL)
DB_PORT=5432                              # PostgreSQL port
DB_NAME=flowpilot_delegations            # Database name
DB_USER=postgres                          # Database user
DB_PASSWORD=<password>                    # Database password

# Delegation expiry constraints
DELEGATION_DEFAULT_EXPIRY_DAYS=7         # Default expiration (days)
DELEGATION_MIN_EXPIRY_DAYS=1             # Minimum expiration (days)
DELEGATION_MAX_EXPIRY_DAYS=365           # Maximum expiration (days)

# Delegation allowed actions
DELEGATION_ALLOWED_ACTIONS=read,execute  # Comma-separated list of valid actions

# Security
KEYCLOAK_JWKS_URI=<jwks-url>             # JWT validation (Keycloak)
KEYCLOAK_ISSUER=<issuer-url>             # Expected JWT issuer
INCLUDE_ERROR_DETAILS=1                  # Show detailed errors (0=prod, 1=dev)
MAX_REQUEST_SIZE_MB=1                    # Request body size limit

# Service
REQUEST_TIMEOUT_SECONDS=10               # API request timeout
```

### Deployment Configuration

**Local Development (docker-compose.yml):**
```yaml
flowpilot-delegation-api:
  environment:
    DB_HOST: postgres
    DB_NAME: flowpilot_delegations
    DB_USER: postgres
    DB_PASSWORD: ${POSTGRES_PASSWORD}
    DELEGATION_ALLOWED_ACTIONS: read,execute
    KEYCLOAK_JWKS_URI: http://keycloak:8080/realms/flowpilot/protocol/openid-connect/certs
```

**GCP Production (cloud-run-envs/delegation-api.yaml):**
```yaml
DB_UNIX_SOCKET: /cloudsql/vision-course-476214:us-central1:flowpilot-postgres
DB_NAME: flowpilot_delegations
DB_USER: postgres
DB_PASSWORD: <secret>
DELEGATION_ALLOWED_ACTIONS: read,execute
INCLUDE_ERROR_DETAILS: "0"
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

## Related Documentation

- [Policy Development Guide](policies.md) - How OPA policies use delegation data
- [Persona Development Guide](personas.md) - How personas interact with delegations
- [Authorization Architecture](../architecture/authorization.md) - Overall authorization flow
- [API Reference: Delegation API](../api/delegation.md) - Full API specification
