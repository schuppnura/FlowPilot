# FlowPilot Test Suite

Automated integration tests for FlowPilot authorization system.

## Test Files

- **`regression_test.py`** - Comprehensive regression tests (API-level, no UI)
- **`user_based_testing.py`** - Interactive browser-based authentication tests

## Regression Test Suite

The regression test suite (`regression_test.py`) exercises the complete authorization flow programmatically without the UI.

### Prerequisites

1. **FlowPilot stack running**:
   ```bash
   docker compose up -d
   ```

2. **Test users provisioned in Keycloak**:
   - carlo (password: carlo123)
   - martine (martine123)
   - yannick (yannick123)
   - isabel (isabel123)

3. **Client secret configured**:
   Edit `tests/regression_test.py` and set `KEYCLOAK_CLIENT_SECRET` to match your `.env` file.

### Running Tests

```bash
# From project root
python3 tests/regression_test.py
```

### Test Scenarios

The suite covers 8 key authorization scenarios:

#### 1. **Autobook Checks - Baseline**
- User: carlo
- Persona: business-traveler
- Expected: 3 allowed (all items pass autobook checks)

#### 2. **Autobook Checks - Cost Limit**
- User: carlo (with autobook_price = 100 EUR)
- Expected: 2 allowed, 1 denied (one item exceeds cost limit)
- **Manual Step**: Requires updating carlo's autobook_price in Keycloak

#### 3. **Anti-Spoofing**
- User: martine tries to access carlo's workflow
- Expected: 0 allowed, 3 denied (no delegation exists)
- Reason: `auto_book.principal_spoofing` or `auto_book.insufficient_delegation_permissions`

#### 4. **Delegation - Wrong Persona**
- Carlo delegates to yannick with scope=["execute"]
- Yannick uses business-traveler persona
- Expected: 0 allowed, 3 denied
- Reason: `auto_book.persona_mismatch` (should be travel-agent)

#### 5. **Delegation - Correct Persona**
- Yannick uses travel-agent persona
- Expected: Same results as carlo (delegation works)

#### 6. **Persona Mismatch - Create with One Persona**
- Martine creates workflow with business-traveler persona
- Martine executes with business-traveler persona
- Expected: Allowed (persona matches)

#### 7. **Persona Mismatch - Switch Persona**
- Martine switches to traveler persona
- Tries to execute business-traveler workflow
- Expected: 0 allowed, 3 denied
- Reason: `auto_book.persona_mismatch`

#### 8. **Read-Only Delegation**
- Carlo invites isabel with scope=["read"]
- Isabel tries to execute
- Expected: 0 allowed, 3 denied
- Reason: `auto_book.insufficient_delegation_permissions`

### Test Output

```
======================================================================
FlowPilot Regression Test Suite
======================================================================

======================================================================
Test 1: Autobook Checks - Baseline
======================================================================
  Created workflow: w_abc123
  ✓ PASS: Carlo can execute all items
    Expected: Allow=3, Deny=0, Error=0
    Got:      Allow=3, Deny=0, Error=0

...

======================================================================
Test Results: 8/8 tests passed
======================================================================
```

### Configuration

Key configuration in `regression_test.py`:

```python
SERVICES_API_BASE = "http://localhost:8003"
AGENT_API_BASE = "http://localhost:8004"
DELEGATION_API_BASE = "http://localhost:8005"
KEYCLOAK_BASE_URL = "https://localhost:8443"
KEYCLOAK_CLIENT_ID = "flowpilot-agent"
KEYCLOAK_CLIENT_SECRET = "your-client-secret"  # ← Update this!
```

### Exit Codes

- `0` - All tests passed
- `1` - One or more tests failed or error occurred

### CI/CD Integration

The test can be integrated into CI/CD pipelines:

```bash
#!/bin/bash
# Start stack
docker compose up -d

# Wait for services to be ready
sleep 10

# Run tests
python3 tests/regression_test.py

# Capture exit code
TEST_RESULT=$?

# Cleanup
docker compose down

# Exit with test result
exit $TEST_RESULT
```

## Interactive Testing

For browser-based authentication testing, use:

```bash
python3 tests/user_based_testing.py
```

This opens a browser for OIDC login and tests anti-spoofing guardrails interactively.
