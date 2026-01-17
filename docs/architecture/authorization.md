# Authorization Architecture

Authorization decisions in FlowPilot are **persona-driven**, not identity-driven.

A **persona** represents the **business role** a subject assumes in a given context. A single person (principal) may have **one or more personas**, but each authorization request is evaluated against **exactly one active persona**.

The `persona` attribute is therefore a **core authorization input**.

## Authorization Flow

The complete authorization flow follows these steps:

### 1. Request Arrives at PEP

A request arrives at a Policy Enforcement Point (domain-services-api or ai-agent-api).

### 2. PEP Constructs AuthZEN Request

The PEP constructs an AuthZEN-compliant authorization request:

```json
{
  "subject": {
    "id": "agent-runner",
    "persona": "ai-agent"
  },
  "action": {
    "name": "execute"
  },
  "resource": {
    "type": "workflow_item",
    "id": "i_abc123",
    "workflow_id": "w_xyz789"
  },
  "context": {
    "principal": {
      "id": "user-uuid",
      "persona": "traveler"
    }
  }
}
```

### 3. AuthZ-API Validates JWT

The authz-api validates the bearer token:

- Validates using Firebase Admin SDK
- Verifies signature using Firebase public keys
- Checks issuer (Firebase), audience (project ID), expiry
- Extracts `uid` (mapped to `sub`) and custom claims

### 4. Delegation Check (ReBAC)

If `subject.id ≠ context.principal.id`, authz-api queries the delegation-api:

- Checks if a valid delegation exists
- Resolves delegation chains (transitive)
- Validates delegation scope and actions

### 5. Policy Enrichment

Authz-api enriches the request with policy-relevant attributes:

- User consent flags
- Auto-booking preferences
- Risk thresholds
- Resource properties

### 6. OPA Policy Evaluation (ABAC)

Enriched input is sent to OPA:

- OPA evaluates Rego policies
- Returns decision (allow/deny)
- Provides reason codes

### 7. Decision Returned to PEP

Authz-api returns structured response:

```json
{
  "decision": true,
  "reason": "Delegation valid and policy satisfied"
}
```

### 8. PEP Enforces Decision

The PEP grants or denies the requested action based on the decision.

## Autonomous AI Booking Policy

An `ai-agent` is allowed to book travel autonomously only when **all** of the following policy conditions are satisfied:

1. **The user has explicitly provided auto-book consent**
2. **The total trip cost is less than or equal to the configured threshold** (e.g., €1,500)
3. **The departure date is at least the configured lead time in the future** (e.g., 7 days)
4. **The airline risk score is below the configured threshold**

These conditions are evaluated declaratively using OPA (ABAC) and are independent of delegation relationships.

If any condition fails, autonomous booking is denied.

## Delegation Model

A user with persona `traveler` may delegate the execution of a booking workflow to users with one of the following personas:

- `travel-agent`
- `office-manager`
- `booking-assistant`

Delegation is **explicit**, **directional**, and **relationship-based** (ReBAC).

The delegation chain is validated and used by the attribute-based policy evaluation to make a decision.

Delegation can also be done for read-only access, for example to invite co-travelers (both with the persona `traveler`).

## Authorization Scenarios

The authorization layer distinguishes between the following scenarios:

### 1. Owner Acting Directly (Regular User)

- Subject is **not** an ai-agent
- `subject.id == resource.owner.id`
- No delegation needed

### 2. Owner Acting via an Agent-Runner

- Subject **is** an ai-agent
- `context.principal.id == resource.owner.id`
- Agent acts on direct behalf of user

### 3. Autonomous AI Agent

- Subject **is** an ai-agent
- Auto-book consent is present
- Policy conditions satisfied
- No delegation relationship required

### 4. Delegated Execution

- A valid delegation exists between principal and subject
- Delegation includes the required action (e.g., `execute`, `read`)
- May involve transitive delegation chains

## From AuthZEN Request to OPA Input

The authz-api translates intent into decision-ready authorization claims.

### AuthZEN Payload (PEP → AuthZ API)

The PEP sends a lightweight, portable request:

```json
{
  "subject": {
    "type": "agent",
    "id": "agent-runner",
    "persona": "ai-agent"
  },
  "action": {"name": "execute"},
  "resource": {
    "type": "workflow_item",
    "id": "i_bc722d96",
    "properties": {
      "workflow_id": "w_771ab24f",
      "planned_price": 500.0,
      "departure_date": "2026-01-30",
      "airline_risk_score": 7,
      "owner": {
        "id": "user-uuid",
        "persona": "traveler"
      }
    }
  },
  "context": {
    "principal": {
      "id": "agent-uuid",
      "persona": "travel-agent"
    }
  }
}
```

Key characteristics:

- Lightweight - no PII, no policy parameters
- Portable - works across PDP implementations
- Expresses intent and context, not policy

### Enriched OPA Input (AuthZ API → OPA)

Before calling OPA, authz-api enriches the request:

```json
{
  "subject": {
    "type": "agent",
    "id": "agent-runner",
    "persona": "ai-agent"
  },
  "action": {"name": "execute"},
  "resource": {
    "type": "workflow_item",
    "id": "i_bc722d96",
    "properties": {
      "workflow_id": "w_771ab24f",
      "planned_price": 500.0,
      "departure_date": "2026-01-30T00:00:00Z",
      "airline_risk_score": 7.0,
      "owner": {
        "id": "user-uuid",
        "persona": "traveler",
        "autobook_consent": true,
        "autobook_price": 10000,
        "autobook_leadtime": 7,
        "autobook_risklevel": 5
      }
    }
  },
  "context": {
    "delegation": {
      "valid": true,
      "delegation_chain": ["user-uuid-1", "user-uuid-2"],
      "delegated_actions": ["read", "execute"]
    },
    "principal": {
      "id": "agent-uuid",
      "persona": "travel-agent"
    }
  }
}
```

### Enrichment Steps

**1. Delegation (PIP for ReBAC)**

- A `context.delegation` block is added
- Captures:
  - Whether delegation is valid
  - The resolved delegation chain
  - The actions granted by delegation
- OPA does not resolve delegation itself; it consumes the result

**2. Policy Attributes (PIP for ABAC)**

Additional attributes are injected:

- `autobook_consent` - User consent flag
- `autobook_price` - Maximum price threshold
- `autobook_leadtime` - Minimum lead time (days)
- `autobook_risklevel` - Risk tolerance level

These values:

- Are derived from user profiles
- Contain no PII
- Are normalized to types suitable for Rego evaluation

**3. Normalization and Hardening**

- Dates converted to RFC 3339 timestamps
- Numeric values coerced to numbers
- Optional fields have consistent types or are absent
- Policy evaluation receives deterministic, safe input

## Why This Separation Matters

- **AuthZEN payloads** express intent and context
- **OPA input documents** express decision-ready facts
- **The translation layer:**
  - Enforces security invariants
  - Prevents PII leakage
  - Shields policies from upstream variability

This design keeps:

- **PEPs simple** - Minimal authorization logic
- **Policies declarative** - Distinct review, approval, and release cycle
- **Privacy preserved** - No PII in policy decisions
- **Authorization explainable** - Clear audit trail

## Summary

- **Personas** define *what role* a subject plays
- **Delegation** defines *who may act for whom*
- **OPA policies** define *under which conditions actions are allowed*
- **Autonomous AI execution** is strictly gated and opt-in

Together, these mechanisms ensure that authorization decisions are:

- Explicit
- Explainable
- Privacy-preserving
- Safe for agent-based execution

## References

- [API Reference: Authz API](../api/authz.md) - Full API specification
- [Policy Development Guide](../development/policies.md) - How OPA policies use persona data
- [Persona Development Guide](../development/personas.md) - How personas and delegation are managed
- [Authentication Architecture](../architecture/authentication.md) - Overall access token flow
