# Policy Development

This guide explains how FlowPilot’s authorization policies are structured, how they are evaluated, and the role of the `authz-api` in the overall authorization flow.

It explains:
- How authorization policies are structured and evaluated
- How AuthZEN, OPA, and Rego fit together
- How policies are developed, tested, deployed, and governed in production

FlowPilot uses **Open Policy Agent (OPA)** with **Rego** policies to implement declarative access control. At its core, the policy engine answers the question:

> “Is this subject allowed to perform this action on this resource?”


## Policy Decision Flow

FlowPilot deliberately separates authorization responsibilities across three layers.

### Policy Decision Layer (PDP)

- Is implemented using **OPA**
- Is driven by declarative rules written in **Rego**
- Is limited to pure policy logic
- Performs no data fetching or external calls
- Receives fully prepared, decision-ready input via AuthZEN

### Policy Information Layer (Authz-API)

- Acts as the authorization orchestration layer
- Consolidates data from multiple Policy Information Points (PIPs)
- Validates and interprets JWT bearer tokens
- Fetches user profile data (ABAC attributes)
- Resolves delegation chains (ReBAC attributes)
- Normalizes, enriches, and hardens all inputs
- Invokes OPA with a complete and consistent policy context

### Policy Enforcement Layer (PEP)

- Submits AuthZEN requests that express **intent**
- Applies and enforces decisions returned by the PDP
- Never evaluates authorization logic locally
- Must delegate ALL authorization decisions to authz-api/OPA (including owner checks)

The FlowPilot reference implementation has a number of different PEPs:

- AI Agent runners (represented by `ai-agent-api`)
- Backend microservices (represented by `domain-services-api`)
- Web app and mobile/desktop app

Even though it is often tempting to do a check in-line locally, the reference implementation shows that PEPs *must not* contain inline authorization logic such as:
```python
# WRONG - PEP making policy decisions
if condition1 and condition2:
    # Proceed with action
```

Instead, all authorization requests *must* engage the PDP through `authz-api`:
```python
# CORRECT - PEP delegates to PDP
response = requests.post(f"{AUTHZ_API}/v1/evaluate", json=authzen_request)
if response.json()["decision"] == "allow":
    # Proceed with action
```

This model ensures:

- Single source of truth for all policy decisions
- Consistent policy enforcement across all services
- Complete audit trail of authorization decisions
- Policy changes don't require code changes in PEPs
- Application services stay simple and focused on business behavior

### Policy Language

OPA is a **CNCF Graduated** project (graduated January 29, 2021), which signals maturity, governance, and production readiness. However, it is not a formal international standard.

- OPA is open source and published under the Apache License 2.0
- **Rego**, the policy language used by OPA, is likewise not a formal standard

The authoritative definition of Rego semantics and behavior is provided by the OPA project itself:

- The OPA documentation serves as the canonical language reference
- Built-in functions are defined, versioned, and maintained by OPA

In practice, this means Rego policies are portable across OPA deployments, while remaining tightly aligned with the OPA project’s evolution.

## Policy Construction

### Decision framework

**Allowed actions** are the following:

- `execute` - Execute workflow items (book travel)
- `update` - Update workflow items (update an itinerary)
- `delete` - Delete workflow items (delete trip items from an itinerary)
- `read` - View workflows (read-only access)
- `create`- Set up a new workflow (define a new trip)

```rego
default allow := false
```
This means a *fail-closed by default*, so the decision is `deny` unless explicitly allowed.

**Decision routing** to obtain an `allow` goes as follows:

```rego
allow if {
  input.action.name ["execute", "update", "delete"]
  allow_execute
}
allow if {
  input.action.name == "read"
  allow_read
}
allow if {
  input.action.name == "create"
  valid_persona  # Any authenticated principal with a valid persona can create
}
```
This routes the decision to different rule sets depending on the requested action:

- `execute`, `update`, `delete` require full authorization gates
- `read` has simpler requirements (no ABAC checks)
- `create` has the simplest requirement: it only needs an authenticated user

### Execute Authorization

The `execute`, `update` and `delete` actions go through 7 gates that *all must pass* before the decision is `allow`

- Each gate is a separate rule evaluated independently
- If any gate fails, `allow_execute` is false

```rego
allow_execute if {
  authorized_principal # Anti-spoofing and delegation check
  appropriate_persona  # Persona type check (agent vs owner personas)
  valid_persona        # Persona must be active and within valid time range
  has_consent          # User consent
  acceptable_risk      # Risk threshold
  within_cost_limit    # Cost ceiling
  sufficient_advance   # Lead time requirement
}
```

### Read Authorization

Read access follows simpler authorization rules compared to execute actions. The persona used for reading doesn't matter - if you have delegation with 'read' action, you can read. This treats 'delegation' and 'invitation' identically - both are just delegations with 'read' scope. No ABAC checks (cost, risk, lead time) are required - only identity and delegation validation.

Note that the policy requires explicit delegation for all non-owner access. Having a matching persona is not a sufficient but only a necessary coniditon. In fact, it is checked after first delegation is confirmed, and is not a bypass mechanism.

What this does:

- Owner access: Resource owner can always read their own resources
- Delegation required: Non-owners MUST have explicit delegation with read permission
- Persona validation: Delegated readers must have appropriate persona (agent or invitation personas)
- No ABAC checks: Read actions skip consent, cost, risk, and lead time checks
- AI-agent support: AI agents can read when acting as owner or with delegation

```rego
allow_read if {
  # Persona must have 'read' in allowed-actions
  action_allowed_for_persona  
  # And owner can always read their own workflows
  input.context.principal.id == input.resource.properties.owner.id
}

allow_read if {
  # Persona must have 'read' in allowed-actions
  action_allowed_for_persona  
  # And anyone with a delegation chain containing 'read' action can read
  input.context.principal.id != input.resource.properties.owner.id
  input.action.name in input.context.delegation.delegated_actions
}
```

**Key Differences from Execute:**

- No `has_consent` check (consent in this context only applies to autonomous execution)
- No `within_cost_limit`, `acceptable_risk`, or `sufficient_advance` checks
- Simpler persona requirements (agent personas OR invitation personas)
- Still requires delegation for non-owners


### Rule 1: Check Spoofing Attempt

What this does:

- Prevents principal spoofing (acting as someone else without permission)

Allows 2 scenarios:

  1. Owner access - Principal is the owner (covers both direct user access and agent activated by owner)
  2. Delegated access - Valid delegation chain exists with required action permissions

```rego
authorized_principal if {
  # Owner accessing their own resource (directly or via agent)
  input.context.principal.id == input.resource.properties.owner.id
}

authorized_principal if {
  # Valid delegation: any subject (regular user or ai-agent) with delegation
  # If the action is in delegated_actions, a delegation path must exist
  input.action.name in input.context.delegation.delegated_actions
}
```

**Authz-API role:**

- Queries `delegation-api` to get delegation information
- Includes `context.delegation.delegated_actions` array (empty if no delegation exists)
- Includes `context.delegation.delegation_chain` (empty if no delegation exists)
- Note: `delegation.valid` field is NOT sent to OPA - it's redundant since `delegated_actions` is empty when no valid path exists
- Ensures `context.principal` is always present:
  - If provided in request: uses the provided principal (delegated scenario)
  - If not provided: injects principal from owner information (agent acting for owner)
- Enriches `context.principal` with persona metadata (status, validity timestamps, attributes)


### Rule 2: Check Persona Validity

In addition to checking the persona **type** is appropriate, the policy enforces that the acting principal's persona is currently valid. This combines status and temporal checks:

```rego
valid_persona if {
  input.context.principal.persona_status == "active"
  valid_from := time.parse_rfc3339_ns(input.context.principal.persona_valid_from)
  valid_till := time.parse_rfc3339_ns(input.context.principal.persona_valid_till)
  now := time.now_ns()
  now >= valid_from
  now <= valid_till
}
```

This rule ensures:

1. Status is `active` - Persona is not suspended, inactive, or expired
2. Within time range - Current time is between `valid_from` and `valid_till`

Possible persona statuses:

- `active` - Normal operational state (only valid status)
- `pending` - Persona assignment is pending approval
- `inactive` - Disabled by user
- `suspended` - Temporarily disabled  
- `revoked` - Disabled by user-admin

**Use cases:**

- Time-limited personas (temporary roles, seasonal access)
- Trial periods with automatic expiration
- Future-dated persona activation

**Authz-API role for persona attributes:**

- Fetches owner persona from persona-api
- Extracts: `persona_status`, `valid_from`, `valid_till`, and all `autobook_*` fields
- Merges into `resource.properties.owner` for OPA evaluation
- Fetches principal persona (if principal ≠ owner or no principal provided)
- Enriches `context.principal` with persona validity metadata:
  - `persona_status`, `persona_valid_from`, `persona_valid_till`
  - Policy-specific attributes (when applicable)
- When no principal provided in request: creates `context.principal` from owner data


### Rule 3: Check Persona for Delegation

What this does:

- Validates that the user's business role (*persona*) is appropriate for the action
- Delegated users must have agent personas (`travel-agent`, etc.)
- Owners must match their own persona
- This checks the **type** of persona, not its validity status or time range

```rego
import data.travel.delegation_personas
import data.travel.persona_titles

valid_delegation_personas_for_action contains persona if {
  # Delegation personas can execute/update/delete on behalf of owner
  action := input.action.name
  action in ["execute", "update", "delete"]
  persona := delegation_personas[action][_]
}

valid_delegation_personas_for_action contains persona if {
  # Service personas are always valid for execute/update/delete actions
  action := input.action.name
  action in ["execute", "update", "delete"]
  persona := {"ai-agent", "domain-services"}[_]
}

appropriate_persona_for_action if {
  # If acting on behalf of someone else (via delegation), must use a delegation persona
  input.context.principal.id != input.resource.properties.owner.id
  valid_delegation_personas_for_action[input.context.principal.persona_title]
}

appropriate_persona_for_action if {
  # If acting as owner, must use the same persona (title + circle)
  input.context.principal.id == input.resource.properties.owner.id
  input.context.principal.persona_title == input.resource.properties.owner.persona_title
  input.context.principal.persona_circle == input.resource.properties.owner.persona_circle
}
```

**Authz-API role:**

- Extracts `persona` from the AuthZEN document
- Fetches complete persona object from `persona-api` (includes autobook attributes, status, validity)
- Includes both `subject.properties.persona` and enriched `owner` object in OPA input

Important: The `owner.persona` field contains the persona **title** (e.g., "traveler"), while the full persona data (with autobook attributes, status, and temporal validity) is fetched from persona-api and merged into `resource.properties.owner`. See [Personas Guide](personas.md) for more details.


### Rule 4: Check User Auto-execute Consent

What this does:

- Requires explicit user opt-in for autonomous booking
- Consent is per-persona, not per-workflow

**Important:** Autobook consent is **per-persona**, not per-user. A user with multiple personas can have different consent settings for each.

```rego
has_consent if {
  input.resource.properties.owner.autobook_consent == true
}
```

**Authz-API role:**

- Fetches persona from persona-api
- Extracts `autobook_consent` boolean from persona record
- Includes in `resource.properties.owner.autobook_consent`


### Rule 5: Check User Auto-execute Constraints

A user can set constraits to the AI-agent about when it can act autonomously.

In the use case of "travel", this reflects the risk a traveler is willing to take in terms of cost, transport risk, and time to change their mind.

What this does:

- Ensures booking cost doesn't exceed user's configured limit
- Cost limit is per-user preference
- Checks airline risk score against user's tolerance
- Allows execution if risk score is missing (optional field)
- Denies if risk exceeds configured threshold
- Requires minimum advance notice before departure
- Prevents last-minute autonomous bookings

```rego
within_cost_limit if {
  # Skip if planned_price is absent
  not "planned_price" in object.keys(input.resource.properties)
}

within_cost_limit if {
  "planned_price" in object.keys(input.resource.properties)
  planned_price := input.resource.properties.planned_price
  max_cost := input.resource.properties.owner.autobook_price
  planned_price <= max_cost
}

acceptable_risk if {
  # Skip if airline_risk_score is absent
  not "airline_risk_score" in object.keys(input.resource.properties)
}

acceptable_risk if {
  "airline_risk_score" in object.keys(input.resource.properties)
  risk := input.resource.properties.airline_risk_score
  max_risk := input.resource.properties.owner.autobook_risklevel
  risk <= max_risk
}

sufficient_advance if {
  departure_date_str := input.resource.properties.departure_date
  departure_date := time.parse_rfc3339_ns(departure_date_str)
  now := time.now_ns()
  delta_days := (departure_date - now) / 1000000000 / 60 / 60 / 24
  delta_days >= input.resource.properties.owner.autobook_leadtime
}
```

**Authz-API role:**

- Extracts `planned_price` from workflow item resource
- Fetches `autobook_price` from user profile
- Extracts `airline_risk_score` from workflow item resource, if present
- Fetches `autobook_risklevel` from user profile
- Extracts `departure_date` from workflow item resource
- Fetches `autobook_leadtime` from user profile
- Converts and normalizes prices, risk scores and times


## Policy Architecture

FlowPilot supports **multiple policies** with dynamic selection based on resource type or explicit hints. Each policy is a self-contained package with:

- **Rego policy file** - Decision logic (e.g., `policy.rego`)
- **Manifest file** - Metadata, attributes, and configuration (`manifest.yaml`)

### Policy Directory Structure

```
infra/opa/policies/
├── travel/
│   ├── manifest.yaml    # Travel policy configuration
│   └── policy.rego      # Travel booking rules (package: auto_book)
└── nursing/
    ├── manifest.yaml    # Nursing policy configuration
    └── policy.rego      # Nursing care rules (package: nursing_care)
```

### Policy Manifest

Each policy has a `manifest.yaml` that defines:

```yaml
name: travel
package: auto_book
```

**Manifest Fields:**

- `name` - Policy identifier (must match directory name)
- `package` - OPA Rego package name

Additionally, the manifest also defines the attributes of personas that are needed to take authorization decisions (see [Personas Guide](personas.md)).

### Policy Selection

The authz-api uses a **PolicyRegistry** to manage multiple policies and select the appropriate one per request.

**Policy Selection:**

- **context.policy_hint** - Explicit policy name (REQUIRED)
- PEPs must always specify which policy to use
- No automatic policy selection or fallback

**Example Request:**

```json
{
  "subject": {"id": "user-123"},
  "action": {"name": "execute"},
  "resource": {
    "type": "workflow_item"
  },
  "context": {
    "policy_hint": "travel"  // REQUIRED
  }
}
```

**Policy Loading:**

The authz-api loads all policies at startup:

```
Loaded 2 policies: travel, nursing
```

### Attribute Defaults and Validation

The authz-api applies **defaults** and **validates** attributes before calling OPA:

**Default Application:**

1. Fetch persona from persona-api
2. Apply defaults for missing persona attributes
3. Extract resource attributes from request
4. Apply defaults for missing resource attributes
5. Pass complete attribute set to OPA

**Validation:**

1. Check all required attributes are present
2. If validation fails, return structured error:

```json
{
  "decision": "deny",
  "reason_codes": ["authz.missing_required_attributes"],
  "advice": [{"message": "Missing required resource attributes: departure_date"}]
}
```

### Data Sources for OPA Input

| Field | Source | Provider |
|-------|--------|----------|
| `subject.id` | AuthZEN request | PEP |
| `subject.properties.persona` | AuthZEN request | PEP |
| `action.name` | AuthZEN request | PEP |
| `resource.id` | AuthZEN request | PEP |
| `resource.properties.planned_price` | Workflow item data | PEP |
| `resource.properties.departure_date` | Workflow item data | PEP (normalized by authz-api) |
| `resource.properties.owner.persona` | Workflow creation | PEP |
| `resource.properties.owner.persona_id` | Persona lookup | User-Profile-API (via authz-api) |
| `resource.properties.owner.persona_status` | Persona lookup | User-Profile-API (via authz-api) |
| `resource.properties.owner.persona_valid_from` | Persona lookup | User-Profile-API (via authz-api) |
| `resource.properties.owner.persona_valid_till` | Persona lookup | User-Profile-API (via authz-api) |
| `resource.properties.owner.autobook_*` | Persona lookup | User-Profile-API (via authz-api) |
| `context.delegation.*` | Delegation graph | Delegation-API (via authz-api) |
| `context.principal` | AuthZEN request | PEP / Authz-API |

Note that `subject.properties.persona` represents the `persona` that the user is currently working with. It thus must be provided by the PEP that knows the context of the current user.

Note that `resource.properties.owner.persona` represents the `persona` that the original owner used when they created the workflow. It thus must also be provided by the PEP that remembers the context of the workflow creation.


### Deny Reason Codes

To allow OPA to return a structured reason code for every denial scenario, additional 'rules' connect a `deny`with a reason.

What this does:

- Provides structured reason codes for denials
- Each failed gate has a corresponding reason
- Reasons follow gate evaluation order (fail-fast)
- Supports debugging and audit trails
- Enables client-side error messages

**Reason Code Categories:**

| Code | Description | Gate |
|------|-------------|------|
| `auto_book.principal_spoofing` | No valid delegation exists | Anti-spoofing |
| `auto_book.insufficient_delegation_permissions` | Delegation lacks execute action | Anti-spoofing |
| `auto_book.persona_mismatch` | Subject persona type doesn't match requirements | Persona type validation |
| `auto_book.persona_invalid` | Persona status not active OR outside validity time range | Persona validity |
| `auto_book.no_consent` | Autobook consent is false | Consent |
| `auto_book.airline_risk_too_high` | Risk score exceeds threshold | Risk gate |
| `auto_book.cost_limit_exceeded` | Price exceeds configured limit | Cost gate |
| `auto_book.insufficient_advance_notice` | Departure too soon | Lead time gate |

Reason codes follow the gate evaluation order:

```rego
reasons[code] if {
  input.action.name in ["execute", "update", "delete"]
  not authorized_principal
  code := "auto_book.unauthorized_principal"
}
reasons[code] if {
  input.action.name in ["execute", "update", "delete"]
  code := "auto_book.persona_mismatch"
  authorized_principal
  not appropriate_persona_for_action
}
reasons[code] if {
  input.action.name in ["execute", "update", "delete"]
  code := "auto_book.persona_invalid"
  authorized_principal
  appropriate_persona_for_action
  not valid_persona
}
reasons[code] if {
  input.action.name in ["execute", "update", "delete"]
  code := "auto_book.no_consent"
  authorized_principal
  not has_consent
}
reasons[code] if {
  input.action.name in ["execute", "update", "delete"]
  code := "auto_book.airline_risk_too_high"
  authorized_principal
  has_consent
  not acceptable_risk
}
reasons[code] if {
  input.action.name in ["execute", "update", "delete"]
  code := "auto_book.cost_limit_exceeded"
  authorized_principal
  has_consent
  acceptable_risk
  not within_cost_limit
}
reasons[code] if {
  input.action.name in ["execute", "update", "delete"]
  code := "auto_book.insufficient_advance_notice"
  authorized_principal
  has_consent
  acceptable_risk
  within_cost_limit
  not sufficient_advance
}
```

**Authz-API role:**

- Collects `reasons` array from OPA response
- Returns reason codes to PEP for logging/debugging
- Maps codes to human-readable messages

## Best Practices

### For Policy Manifest Authors

1. **Descriptive names** - Use clear policy and attribute names
2. **Conservative defaults** - Start with restrictive defaults, relax as needed
3. **Document attributes** - Provide clear descriptions for each attribute
4. **Type appropriately** - Use correct types (integer for counts, float for money)
5. **Mark required fields** - Only make attributes required if truly mandatory
6. **Version carefully** - Plan for policy evolution (future versioning support)

### For Policy Authors

1. **Fail-closed** - Default to deny
2. **Explicit rules** - Make allow conditions clear
3. **Reason codes** - Provide debugging information
4. **Type safety** - Rely on authz-api normalization and defaults

### For Authz-API Developers

1. **Normalize data** - Convert types before OPA
2. **Validate inputs** - Ensure required fields exist
3. **Enrich completely** - Provide all data OPA needs
4. **Handle errors** - Graceful degradation on PIP failures
5. **Log decisions** - Audit all authorization outcomes

### For PEP Developers

1. **Minimal requests** - Send only intent, not policy data
2. **Consistent format** - Use AuthZEN structure
3. **Include context** - Provide principal when subject ≠ owner
4. **Include policy_hint** - Always specify which policy to use in context.policy_hint
5. **Enforce decisions** - Always respect authz-api response

## Related Documentation

- [Authorization Architecture](../architecture/authorization.md) - Overall authorization flow
- [Persona Development Guide](personas.md) - How personas are managed
- [API Reference: Authz API](../api/authz.md) - Full API specification