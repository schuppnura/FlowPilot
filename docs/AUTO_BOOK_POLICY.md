# Auto-Book Policy with ABAC Conditions

## Overview

The auto-book policy enables autonomous booking by AI agents with attribute-based access control (ABAC) conditions. This feature combines relationship-based access control (ReBAC) for delegation with policy-based constraints to ensure safe autonomous operations.

## Architecture

### Hybrid ReBAC + ABAC Approach

1. **ReBAC Layer (***REMOVED***)**: Validates delegation relationship
   - Graph: `workflow_item --workflow--> workflow --owner--> user --delegate--> agent`
   - Checks if agent has `can_execute` permission via delegation chain

2. **ABAC Layer**: Evaluates policy conditions
   - **Current Implementation**: Python logic in AuthZ API
     - Simple, no external dependencies
     - Easy to understand and debug
     - Policy parameters stored in AuthZ API profile store
   - **Alternative (Future)**: ***REMOVED*** OPA/Rego policies
     - More declarative and portable
     - Leverages ***REMOVED***'s built-in policy engine
     - Better separation of policy from code
   - Both approaches check:
     - User consent for autonomous booking
     - Cost, departure date, and risk score constraints
     - Return specific deny reason codes for failed conditions

### Flow

```
Request → AuthZ API evaluate_request()
    ↓
1. Anti-spoofing check (principal matches workflow owner)
    ↓
2. ***REMOVED*** ReBAC check (agent delegated by user?)
    ↓
3. If action == "auto-book": ABAC condition check
    ↓
4. Progressive profiling check (identity presence)
    ↓
Decision: allow/deny with reason codes
```

## Policy Conditions

The auto-book policy evaluates four conditions:

### 1. User Consent
- **Condition**: `auto_book_consent == true`
- **Reason Code**: `auto_book.consent_missing`
- **Description**: User must explicitly consent to autonomous booking via profile API

### 2. Cost Limit
- **Condition**: `total_trip_cost <= auto_book_max_cost_eur`
- **Default Limit**: €1,500
- **Reason Code**: `auto_book.cost_exceeds_limit`
- **Description**: Total trip cost (sum of all items) must not exceed user's configured limit

### 3. Departure Advance
- **Condition**: `departure_date >= today + auto_book_min_days_advance`
- **Default Minimum**: 7 days
- **Reason Code**: `auto_book.insufficient_advance`
- **Description**: Departure must be at least N days in the future (allows time for cancellation)

### 4. Airline Risk Score
- **Condition**: `airline_risk_score < auto_book_max_airline_risk`
- **Default Threshold**: 5
- **Reason Code**: `auto_book.airline_risk_too_high`
- **Description**: Flight booking risk score must be below threshold (0=safest, 10=riskiest)

## Configuration

### Default Parameters

Set in `services/flowpilot-authz-api/main.py`:

```python
DEFAULT_CONFIG = {
    # ...
    "auto_book_consent": False,
    "auto_book_max_cost_eur": 1500,
    "auto_book_min_days_advance": 7,
    "auto_book_max_airline_risk": 5,
}
```

### User Override

Users can customize their auto-book parameters via the profile API:

```bash
curl -X PATCH http://localhost:8002/v1/profiles/{user_sub}/policy-parameters \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "parameters": {
      "auto_book_consent": true,
      "auto_book_max_cost_eur": 2000,
      "auto_book_min_days_advance": 14,
      "auto_book_max_airline_risk": 3
    }
  }'
```

## Action Types

### `book` (Manual)
- Requires human approval via desktop app
- No ABAC conditions applied
- Used for dry-run mode

### `auto-book` (Autonomous)
- Autonomous execution by AI agent
- ABAC conditions enforced
- Only available in non-dry-run mode

## Implementation Details

### AuthZ API Changes

**File**: `services/flowpilot-authz-api/core.py`

1. **New Function**: `check_auto_book_policy(policy_parameters, resource_properties)`
   - Evaluates all four ABAC conditions
   - Returns `None` if allowed, or reason code string if denied

2. **Updated Function**: `evaluate_request()`
   - After ***REMOVED*** ReBAC check passes
   - If `action.name == "auto-book"`: calls `check_auto_book_policy()`
   - Returns deny decision with specific reason code if conditions fail

3. **Profile Store**: `InMemoryProfileStore.__init__(default_policy_parameters)`
   - Now accepts default parameters from config
   - New profiles initialized with defaults

### Services API Changes

**File**: `services/flowpilot-services-api/core.py`

1. **Updated Function**: `_call_authz_for_item(trip, item, ...)`
   - Extracts `departure_date` from trip-level properties
   - Extracts `airline_risk_score` from item-level properties
   - Calculates total trip cost from all items
   - Includes all attributes in `resource.properties` for AuthZ evaluation

2. **Trip Creation**: `create_trip_from_template()`
   - Preserves `departure_date` from template to trip
   - Preserves `airline_risk_score` from template items

### Template Changes

**Files**: `data/trip_templates/*.json`

Added booking attributes:
```json
{
  "template_id": "template_all_ok",
  "name": "All Within Budget",
  "departure_date": "2025-12-31",
  "items": [
    {
      "type": "flight",
      "planned_price": {"currency": "EUR", "amount": 900},
      "airline_risk_score": 2
    }
  ]
}
```

## Testing

### Manual Testing

1. **Enable auto-book consent**:
   ```bash
   curl -X PATCH http://localhost:8002/v1/profiles/{user_sub}/policy-parameters \
     -H "Authorization: Bearer $TOKEN" \
     -d '{"parameters": {"auto_book_consent": true}}'
   ```

2. **Create trip with template**: Use desktop app or API to create trip from template

3. **Execute with auto-book action**: Agent runner uses `auto-book` action for autonomous execution

### Test Scenarios

| Scenario | Consent | Cost | Days Advance | Risk | Expected Result |
|----------|---------|------|--------------|------|-----------------|
| No consent | false | 1000 | 10 | 2 | Deny: consent_missing |
| Cost too high | true | 1600 | 10 | 2 | Deny: cost_exceeds_limit |
| Too soon | true | 1000 | 3 | 2 | Deny: insufficient_advance |
| Risky airline | true | 1000 | 10 | 7 | Deny: airline_risk_too_high |
| All OK | true | 1000 | 10 | 2 | Allow (if ReBAC passes) |

### Unit Tests

See `test_auto_book_logic.py` for unit tests of the ABAC policy logic.

## API Examples

### Evaluate Auto-Book Request

```bash
curl -X POST http://localhost:8002/v1/evaluate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "subject": {"type": "agent", "id": "agent-runner"},
    "action": {"name": "auto-book"},
    "resource": {
      "type": "workflow",
      "id": "t_abc12345",
      "properties": {
        "domain": "flowpilot",
        "workflow_item_id": "i_xyz67890",
        "workflow_item_kind": "flight",
        "planned_price": 1200,
        "departure_date": "2025-12-31",
        "airline_risk_score": 3
      }
    },
    "context": {
      "principal": {"type": "user", "id": "user-uuid-here"}
    },
    "options": {
      "dry_run": false,
      "explain": true
    }
  }'
```

### Response Examples

**Allow Response**:
```json
{
  "decision": "allow",
  "decision_id": "dec_abc123",
  "reason_codes": [],
  "advice": [
    {
      "kind": "debug",
      "code": "policy_parameters",
      "message": "Non-PII policy parameters were included in evaluation context.",
      "details": {
        "policy_parameters": {
          "auto_book_consent": true,
          "auto_book_max_cost_eur": 1500,
          "auto_book_min_days_advance": 7,
          "auto_book_max_airline_risk": 5
        }
      }
    }
  ]
}
```

**Deny Response (Cost Exceeds Limit)**:
```json
{
  "decision": "deny",
  "decision_id": "dec_xyz789",
  "reason_codes": ["auto_book.cost_exceeds_limit"],
  "advice": [
    {
      "kind": "policy",
      "code": "auto_book.cost_exceeds_limit",
      "message": "Auto-book policy condition not met: auto_book.cost_exceeds_limit",
      "details": {
        "action": "auto-book",
        "policy_parameters": {
          "auto_book_consent": true,
          "auto_book_max_cost_eur": 1500,
          "auto_book_min_days_advance": 7,
          "auto_book_max_airline_risk": 5
        }
      }
    }
  ]
}
```

## Reason Codes

| Code | Meaning | User Action |
|------|---------|-------------|
| `auto_book.consent_missing` | User hasn't consented | Enable auto-book in profile settings |
| `auto_book.cost_exceeds_limit` | Trip cost too high | Increase cost limit or reduce trip cost |
| `auto_book.insufficient_advance` | Departure too soon | Book earlier or reduce min days advance |
| `auto_book.airline_risk_too_high` | Airline too risky | Choose different airline or increase risk tolerance |

## Future Enhancements

### Migration to ***REMOVED*** OPA/Rego
**Why**: ***REMOVED*** supports OPA (Open Policy Agent) policies written in Rego for ABAC evaluation. This would:
- Make policies declarative and easier to audit
- Enable policy versioning and A/B testing
- Centralize all authorization logic in ***REMOVED***
- Support more complex policy scenarios (e.g., combining multiple attributes)

**Example Rego Policy** (conceptual):
```rego
package flowpilot.auto_book

default allow = false

allow {
    input.user.auto_book_consent == true
    input.trip.total_cost <= input.user.auto_book_max_cost_eur
    days_until_departure >= input.user.auto_book_min_days_advance
    input.flight.airline_risk_score < input.user.auto_book_max_airline_risk
}

days_until_departure := time.diff(input.trip.departure_date, time.now_ns())
```

**Migration Steps**:
1. Define Rego policy in ***REMOVED*** policy directory
2. Update AuthZ API to call ***REMOVED*** policy endpoint instead of `check_auto_book_policy()`
3. Migrate profile parameters to ***REMOVED*** decision input
4. Test policy evaluation with various scenarios

### Additional Policy Features
1. **Destination-Based Rules**: Auto-book only for certain regions/countries
2. **Frequency Limits**: Max N auto-books per month
3. **Cost Categories**: Different limits for flights vs hotels
4. **Time-of-Day Rules**: Auto-book only during business hours
5. **Approval Chains**: Require manager approval for high-cost bookings
6. **Learning Mode**: Track denied requests to suggest limit adjustments
7. **Policy Versioning**: Support multiple policy versions for gradual rollout

## Security Considerations

1. **Anti-Spoofing**: Principal must match workflow owner (enforced before ABAC)
2. **ReBAC First**: ABAC only evaluated after delegation is verified
3. **Default Deny**: Consent defaults to `false` for new users
4. **Granular Reason Codes**: Specific feedback without leaking sensitive data
5. **Audit Trail**: All decisions logged with decision_id for traceability

## References

- [Authorization Graph Documentation](AUTHORIZATION_GRAPH.md)
- [AuthZ API OpenAPI Spec](../flowpilot-authz.openapi.yaml)
- [***REMOVED*** Manifest](../infra/***REMOVED***/cfg/flowpilot-manifest.yaml)
