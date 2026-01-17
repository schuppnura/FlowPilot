# Policy Orchestration

Policy evaluation requires structured, policy-relevant information. In FlowPilot, this information is exchanged with the policy engine using **AuthZEN**.

The **authz-api** acts as the orchestration layer between Policy Enforcement Points (PEPs) and the Policy Decision Point (PDP). It receives AuthZEN requests from PEPs and produces enriched, normalized AuthZEN input for the PDP.

To achieve this, the authz-api performs the following steps:

1. **Validate JWTs** – Ensures bearer access tokens are valid and trustworthy
2. **Resolve Delegation** – Queries the delegation API to obtain ReBAC relationships
3. **Enrich Context** – Adds policy-relevant attributes such as consent flags and thresholds
4. **Normalize Data** – Coerces types and formats (for example, RFC 3339 timestamps, numeric values)
5. **Invoke OPA** – Submits the enriched input to the policy engine
6. **Return Decision** – Produces a structured allow/deny decision with reason codes

**Key insight:** PEPs submit **intent**, while the PDP receives **decision-ready facts**. The authz-api explicitly bridges this gap, ensuring that policies are evaluated against complete and consistent context rather than raw application requests.

## AuthZEN as an Interface Contract

AuthZEN defines a **standardized interface** between PEPs and PDPs, focusing on *how authorization context is exchanged*, not *how policy is implemented*.

Rather than prescribing a policy language or decision logic, AuthZEN standardizes:
- the structure of authorization requests and responses
- the separation of subject, action, resource, and context
- the contract between enforcement and decision components

In FlowPilot, AuthZEN serves as a stable integration boundary:
- PEPs remain agnostic of the underlying policy engine
- the PDP (OPA) is shielded from application-specific variability
- the authorization architecture can evolve without breaking callers

AuthZEN is not a formal international standard, but it provides a well-defined and interoperable contract that aligns with modern zero-trust and policy-as-code architectures.

## Manifest Structure

The manifest has an àttributes`that not only dfefines the persona custom attributes but also the corresponding properties of a workflow item in the AuthZEN document.

Their values are coerced automatically by the authz-api to the type specified. Their values are also defaulted in case they are optional and a default value is provided. A default value of `null` means that the attribute will only be created when it explicitly has a value. 

```yaml
attributes:
  # Persona custom attributes
  # ...
  
  # Resource attributes (from workflow/item properties)
  - name: planned_price
    type: float
    source: resource
    default: 0.0
    required: false
    description: "Planned cost of the trip"
  
  - name: departure_date
    type: date
    source: resource
    default: null
    required: true
    description: "Trip departure date (ISO 8601 format)"
  
  - name: airline_risk_score
    type: float
    source: resource
    default: null
    required: false
    description: "Airline risk score (1.0=lowest risk, 5.0=highest risk). Only present for flight items."
```

## AuthZEN Examples

This is an example of an AuthZEN document sent as payload to the authz-api:

```json
  "request_body": {
    "subject": {
      "id": "domain-services-api",
      "persona": "ai-agent",
      "type": "agent"
    },
    "action": {
      "name": "execute"
    },
    "resource": {
      "type": "workflow_item",
      "id": "i_31ea5dc0",
      "properties": {
        "domain": "flowpilot",
        "workflow_id": "w_0f7411ba",
        "workflow_item_id": "i_31ea5dc0",
        "workflow_item_kind": "transport",
        "planned_price": 4000.0,
        "departure_date": "2026-02-01T00:00:00Z",
        "airline_risk_score": 2.0,
        "owner": {
          "type": "user",
          "id": "d91fb602-29f2-43d0-8878-4d646f442967",
        }
      }
    },
    "context": {
      "policy_hint": "travel",
      "principal": {
        "type": "user",
        "id": "89eb5366-bab3-46e4-b8e1-abc5f2ea4631",
        "persona": "travel-agent"
      }
    }
  }
```

Here's the corresponding **enriched** AuthZEN payload that the authz-api sends to OPA:

```json

{
  "type": "api_request",
  "timestamp": "2026-01-06T13:14:01.042085+00:00",
  "method": "POST",
  "path": "OPA /v1/data/auto_book/allow",
  "request_body": {
    "subject": {
      "type": "agent",
      "id": "c08d6b1a-10bd-4a02-9d5b-a28a0ff3bc53",
      "persona": "ai-agent"
    },
    "action": {
      "name": "execute"
    },
    "resource": {
      "type": "workflow_item",
      "id": "i_31ea5dc0",
      "properties": {
        "domain": "flowpilot",
        "workflow_id": "w_0f7411ba",
        "workflow_item_id": "i_31ea5dc0",
        "workflow_item_kind": "transport",
        "planned_price": 4000.0,
        "departure_date": "2026-02-01T00:00:00Z",
        "airline_risk_score": 2.0,
        "owner": {
          "type": "user",
          "id": "d91fb602-29f2-43d0-8878-4d646f442967",
          "persona": "traveler",
          "persona_id": "b9678f30-f4b0-4033-82db-846357311165",
          "persona_status": "active",
          "persona_valid_from": "2024-01-01T00:00:00Z",
          "persona_valid_till": "2026-12-31T23:59:59Z",
          "autobook_consent": true,
          "autobook_price": 10000,
          "autobook_leadtime": 7,
          "autobook_risklevel": 5
        }
      }
    },
    "context": {
      "principal": {
        "type": "user",
        "id": "89eb5366-bab3-46e4-b8e1-abc5f2ea4631",
        "persona": "travel-agent"
      },
      "delegation": {
        "valid": true,
        "delegation_chain": [
          "d91fb602-29f2-43d0-8878-4d646f442967",
          "30dc31a0-2061-43c7-aa2a-7f7760936fc9",
          "89eb5366-bab3-46e4-b8e1-abc5f2ea4631"
        ],
        "delegated_actions": [
          "execute"
        ]
      }
    }
  }
}
```

## The role of Authz-API

### AuthZ-API

Purpose: Fetches persona data for authorization decisions (acts as Policy Information Point)

Persona Fetching Logic:

1. Extract `owner.id` and `owner.persona` (title) from AuthZEN request
2. If `owner.persona_id` is present, fetch directly: `GET /v1/personas/{persona_id}`
3. If only `owner.persona` (title) is present, fetch by user and title: `GET /v1/users/{user_sub}/personas`
4. If fetch fails (404, 403, timeout), use default values (deny by default)
5. Augment `resource.properties.owner` with autobook attributes for OPA

Code Location: `flowpilot-services/authz-api/authz_core.py`

### OPA Integration

Persona data flows into OPA as part of the `resource.properties.owner` object:

```json
{
  "subject": {"id": "agent-runner", "persona": "ai-agent"},
  "action": {"name": "execute"},
  "resource": {
    "properties": {
      "owner": {
        "id": "user-uuid",
        "persona": "traveler",
        "persona_id": "b9678f30-f4b0-4033-82db-846357311165",
        "persona_status": "active",
        "persona_valid_from": "2024-01-01T00:00:00Z",
        "persona_valid_till": "2026-12-31T23:59:59Z",
        "autobook_consent": true,
        "autobook_price": 5000,
        "autobook_leadtime": 7,
        "autobook_risklevel": 3
      }
    }
  }
}
```

OPA policies use these attributes to evaluate authorization gates:

```rego
# Consent check
has_consent if {
  input.resource.properties.owner.autobook_consent == true
}

# Cost gate
within_cost_limit if {
  planned_price := input.resource.properties.planned_price
  max_cost := input.resource.properties.owner.autobook_price
  planned_price <= max_cost
}

# Persona status check
owner_persona_active if {
  input.resource.properties.owner.persona_status == "active"
}

# Persona temporal validity
owner_persona_valid_time if {
  valid_from_str := input.resource.properties.owner.persona_valid_from
  valid_till_str := input.resource.properties.owner.persona_valid_till
  valid_from := time.parse_rfc3339_ns(valid_from_str)
  valid_till := time.parse_rfc3339_ns(valid_till_str)
  now := time.now_ns()
  now >= valid_from
  now <= valid_till
}
```

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


## Related Documentation

- [API Reference: Authz API](../api/authz.md) - Full API specification
- [Policy Development Guide](policies.md) - How OPA policies use persona data
- [Persona Development Guide](personas.md) - How personas are managed
- [Authorization Architecture](../architecture/authorization.md) - Overall authorization flow
- [Authentication Architecture](../architecture/authentication.md) - Overall access token flow

