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

This separation ensures that:

- Policies remain clean, declarative, and testable
- Authorization logic is centralized and auditable
- Application services stay simple and focused on business behavior

### Notes on OPA and Rego

OPA is a **CNCF Graduated** project (graduated January 29, 2021), which signals maturity, governance, and production readiness. However, it is not a formal international standard.

- OPA is open source and published under the Apache License 2.0
- **Rego**, the policy language used by OPA, is likewise not a formal standard
- The authoritative definition of Rego semantics and behavior is provided by the OPA project itself:
  - The OPA documentation serves as the canonical language reference
  - Built-in functions are defined, versioned, and maintained by OPA

In practice, this means Rego policies are portable across OPA deployments, while remaining tightly aligned with the OPA project’s evolution.


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

# Resource types this policy handles (for policy selection)
resource_types:
  - workflow
  - workflow_item
  - trip
```

**Manifest Fields:**

- `name` - Policy identifier (must match directory name)
- `package` - OPA Rego package name
- `resource_types` - List of resource types this policy handles (for routing)

Additionally, the manifest also defines the attributes of personas that are needed to take authorization decisions (see [Personas Guide](personas.md)).

### Policy Selection

The authz-api uses a **PolicyRegistry** to manage multiple policies and select the appropriate one per request.

**Selection Priority:**

1. **context.policy_hint** - Explicit policy name (highest priority)
2. **resource.type matching** - Matches policy's resource_types list
3. **ERROR** - No default fallback (fail-safe design)

**Example Request:**

```json
{
  "subject": {"id": "user-123"},
  "action": {"name": "execute"},
  "resource": {
    "type": "workflow_item"  // Matches travel policy
  },
  "context": {
    "policy_hint": "travel"  // Explicit override (optional)
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

## Policy Construction

### Decision framework

**Allowed actions** are specified as follows:

- `execute` - Execute workflow items (book travel)
- `read` - View workflows (read-only access)

```rego
default allow := false
```
This means a *fail-closed by default*, so the decision is `deny` unless explicitly allowed.

**Decision routing** is specified as follows:

```rego
allow if {
  input.action.name == "execute"
  allow_execute
}

allow if {
  input.action.name == "read"
  allow_read
}
```
This routes the decision to different rule sets depending on the requested action:
- `execute` requires full authorization gates
- `read` has simpler requirements

**Decisions Gates** are specified as follows:

```rego
allow_execute if {
  authorized_principal  # Anti-spoofing and delegation check
  appropriate_persona  # Persona type check (agent vs owner personas)
  valid_persona        # Persona must be active and within valid time range
  has_consent          # User consent
  acceptable_risk      # Risk threshold
  within_cost_limit    # Cost ceiling
  sufficient_advance   # Lead time requirement
}
```

This defines 7 gates that *all must pass* before the decision is `allow`
- Each gate is a separate rule evaluated independently
- If any gate fails, `allow_execute` is false

**Authz-API role:** Interprets `allow = false` as a deny decision. It also includes `action.name` in the OPA input based on the PEP's request. Provides all data needed for gate evaluation (more below)

### Anti-Spoofing Checks

```rego
# Owner directly accessing their own resource
authorized_principal if {
  input.subject.persona != "ai-agent"
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id == owner_id
}

# AI-agent activated by the owner
authorized_principal if {
  input.subject.persona == "ai-agent"
  principal_id := input.context.principal.id
  owner_id := input.resource.properties.owner.id
  principal_id == owner_id
}

# AI-agent in autonomous mode
authorized_principal if {
  input.subject.persona == "ai-agent"
  input.resource.properties.owner.autobook_consent == true
  not input.context.delegation.valid
}

# Valid delegation
authorized_principal if {
  has_valid_delegation_for_action
}
```

**What this does:**

- Prevents principal spoofing (acting as someone else without permission)
- Allows 4 scenarios:
  1. **Owner acting directly** - User executes their own workflow
  2. **Owner via agent** - User activates AI agent to execute
  3. **Autonomous AI** - AI acts independently with consent
  4. **Delegated user** - Another user with explicit delegation

**Authz-API role:**

- Queries **delegation-api** to get `context.delegation.valid`
- Includes `context.delegation.delegated_actions` array
- Ensures `context.principal` is set when subject ≠ owner


### Appropriate Persona Check

```rego
delegated_agent_personas := {"travel-agent", "ai-agent", "office-manager", "booking-assistant"}

# Owner executing directly
appropriate_persona if {
  input.subject.persona != "ai-agent"
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id == owner_id
  owner_persona := input.resource.properties.owner.persona
  input.subject.persona == owner_persona
}

# Owner executing via AI-agent
appropriate_persona if {
  input.subject.persona == "ai-agent"
  principal_id := input.context.principal.id
  owner_id := input.resource.properties.owner.id
  principal_id == owner_id
  owner_persona := input.resource.properties.owner.persona
  principal_persona := input.context.principal.persona
  principal_persona == owner_persona
}

# Human user delegated by owner, or other delegated user (in a chain of delegation)
appropriate_persona if {
  input.subject.persona != "ai-agent"
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  input.subject.persona != ""
  delegated_agent_personas[input.subject.persona]
}

# AI-agent activated by delegated user
appropriate_persona if {
  input.subject.persona == "ai-agent"
  principal_id := input.context.principal.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  principal_persona := input.context.principal.persona
  principal_persona != ""
  delegated_agent_personas[principal_persona]
}
```

**What this does:**

- Validates that the user's business role (*persona*) is appropriate for the action
- Delegated users must have agent personas (`travel-agent`, etc.)
- Owners must match their own persona
- This checks the **type** of persona, not its validity status or time range

**Authz-API role:**

- Extracts `persona` from JWT custom claims
- Fetches complete persona object from persona-api (includes autobook attributes, status, validity)
- Includes both `subject.persona` and enriched `owner` object in OPA input

Important: The `owner.persona` field contains the persona **title** (e.g., "traveler"), while the full persona data (with autobook attributes, status, and temporal validity) is fetched from persona-api and merged into `resource.properties.owner`. See [Personas Guide](personas.md) for more details.

### Persona Validity Check

In addition to checking the persona **type** is appropriate, the policy enforces that the owner's persona is currently valid. This combines status and temporal checks:

```rego
valid_persona if {
  # Persona status must be "active"
  input.resource.properties.owner.persona_status == "active"
  
  # Parse persona validity timestamps
  valid_from_str := input.resource.properties.owner.persona_valid_from
  valid_till_str := input.resource.properties.owner.persona_valid_till
  
  # Both timestamps must be present and valid
  valid_from_str != ""
  valid_till_str != ""
  
  # Parse timestamps to nanoseconds
  valid_from := time.parse_rfc3339_ns(valid_from_str)
  valid_till := time.parse_rfc3339_ns(valid_till_str)
  now := time.now_ns()
  
  # Current time must be within valid range
  now >= valid_from
  now <= valid_till
}
```

This rule ensures:

1. Status is `active` - Persona is not suspended, inactive, or expired
2. Within time range - Current time is between `valid_from` and `valid_till`
3. No backward compatibility - Both status and timestamps are **required**

Possible persona statuses:

- `active` - Normal operational state (only valid status)
- `pending` - Persona assignment is pending approval
- `inactive` - Disabled
- `suspended` - Temporarily disabled  
- `expired` - Past validity period

**Use cases:**

- Time-limited personas (temporary roles, seasonal access)
- Trial periods with automatic expiration
- Future-dated persona activation

**Authz-API role for persona attributes:**

- Queries persona-api: `GET /v1/users/{user_sub}/personas?status=active`
- Finds persona matching `owner.persona` title
- Extracts: `persona_status`, `valid_from`, `valid_till`, and all `autobook_*` fields
- Merges into `resource.properties.owner` for OPA evaluation

### User Consent Check

```rego
has_consent if {
  input.resource.properties.owner.autobook_consent == true
}
```

**What this does:**

- Requires explicit user opt-in for autonomous booking
- Consent is per-user, not per-workflow

**Authz-API role:**

- Fetches persona from persona-api
- Extracts `autobook_consent` boolean from persona record
- Includes in `resource.properties.owner.autobook_consent`

**Important:** Autobook consent is **per-persona**, not per-user. A user with multiple personas can have different consent settings for each.

### User Preferences Check

A user can set constraits to the AI-agent about when it can act autonomously.

In the use case of "travel", this reflects the risk a traveler is willing to take in terms of cost, transport risk, and time to change their mind.

```rego
within_cost_limit if {
  planned_price := input.resource.properties.planned_price
  planned_price <= input.resource.properties.owner.autobook_price
}
acceptable_risk if {
  risk := input.resource.properties.airline_risk_score
  risk <= input.resource.properties.owner.autobook_risklevel
}
sufficient_advance if {
  departure_date_str := input.resource.properties.departure_date
  departure_date := time.parse_rfc3339_ns(departure_date_str)
  now := time.now_ns()
  delta_days := (departure_date - now) / 1000000000 / 60 / 60 / 24
  delta_days >= input.resource.properties.owner.autobook_leadtime
}
```

**What this does:**

- Ensures booking cost doesn't exceed user's configured limit
- Cost limit is per-user preference
- Checks airline risk score against user's tolerance
- Allows execution if risk score is missing (optional field)
- Denies if risk exceeds configured threshold
- Requires minimum advance notice before departure
- Prevents last-minute autonomous bookings

**Authz-API role:**

- Extracts `planned_price` from workflow item resource
- Fetches `autobook_price` from user profile
- Extracts `airline_risk_score` from workflow item resource, if present
- Fetches `autobook_risklevel` from user profile
- Extracts `departure_date` from workflow item resource
- Fetches `autobook_leadtime` from user profile
- Converts and normalizes prices, risk scores and times

### Deny Reason Codes

The policy provides a structured reason code for every denial scenario. Reason codes follow the gate evaluation order:

```rego
# 1. Principal spoofing (no delegation)
reasons[code] if {
  input.action.name == "execute"
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  not input.context.delegation.valid
  code := "auto_book.principal_spoofing"
}

# 2. Insufficient delegation permissions
reasons[code] if {
  input.action.name == "execute"
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  input.context.delegation.valid == true
  not input.action.name in input.context.delegation.delegated_actions
  code := "auto_book.insufficient_delegation_permissions"
}

# 3. Persona type mismatch
reasons[code] if {
  input.action.name == "execute"
  code := "auto_book.persona_mismatch"
  authorized_principal
  not appropriate_persona
}

# 4. Persona invalid (status not active or outside time range)
reasons[code] if {
  input.action.name == "execute"
  code := "auto_book.persona_invalid"
  authorized_principal
  appropriate_persona
  not valid_persona
}

# 5. No autobook consent
reasons[code] if {
  input.action.name == "execute"
  code := "auto_book.no_consent"
  authorized_principal
  appropriate_persona
  valid_persona
  not has_consent
}

# 6. Airline risk too high
reasons[code] if {
  input.action.name == "execute"
  code := "auto_book.airline_risk_too_high"
  authorized_principal
  appropriate_persona
  valid_persona
  has_consent
  not acceptable_risk
}

# 7. Cost limit exceeded
reasons[code] if {
  input.action.name == "execute"
  code := "auto_book.cost_limit_exceeded"
  authorized_principal
  appropriate_persona
  valid_persona
  has_consent
  acceptable_risk
  not within_cost_limit
}

# 8. Insufficient advance notice
reasons[code] if {
  input.action.name == "execute"
  code := "auto_book.insufficient_advance_notice"
  authorized_principal
  appropriate_persona
  valid_persona
  has_consent
  acceptable_risk
  within_cost_limit
  not sufficient_advance
}
```

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

**What this does:**

- Provides structured reason codes for denials
- Each failed gate has a corresponding reason
- Reasons follow gate evaluation order (fail-fast)
- Supports debugging and audit trails
- Enables client-side error messages

**Authz-API role:**

- Collects `reasons` array from OPA response
- Returns reason codes to PEP for logging/debugging
- Maps codes to human-readable messages


### Data Sources for OPA Input

| Field | Source | Provider |
|-------|--------|----------|
| `subject.id` | AuthZEN request | PEP |
| `subject.persona` | JWT custom claims | Authz-API |
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
| `context.principal` | AuthZEN request or JWT | PEP / Authz-API |

## Best Practices

### For Policy Manifest Authors

1. **Descriptive names** - Use clear policy and attribute names
2. **Conservative defaults** - Start with restrictive defaults, relax as needed
3. **Document attributes** - Provide clear descriptions for each attribute
4. **Type appropriately** - Use correct types (integer for counts, float for money)
5. **Mark required fields** - Only make attributes required if truly mandatory
6. **List resource types** - Include all resource types the policy handles
7. **Version carefully** - Plan for policy evolution (future versioning support)

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
4. **Enforce decisions** - Always respect authz-api response

## Related Documentation

- [Authorization Architecture](../architecture/authorization.md) - Overall authorization flow
- [Persona Development Guide](personas.md) - How personas are managed
- [API Reference: Authz API](../api/authz.md) - Full API specification

