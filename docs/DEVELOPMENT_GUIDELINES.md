# FlowPilot Development Guidelines

Based on the recent cleanup work, here are the coding standards and preferences for future development.

## 1. Configuration Management

### All Configuration Must Be Explicit
- **Never use default values in code** - all configuration must be declared in `docker-compose.yml`
- Environment variables should be read using `utils.read_env_*()` functions **without defaults**
- If a required configuration is missing, services should **fail fast** with clear error messages
- Configuration should be **discoverable in one place** (docker-compose.yml)

**Bad:**
```python
timeout = int(os.environ.get("TIMEOUT", "10"))  # Hidden default
```

**Good:**
```python
timeout = read_env_int("TIMEOUT")  # Raises error if missing
# And in docker-compose.yml:
# TIMEOUT: "10"
```

### Centralize HTTP Client Configuration
- All HTTP requests must use centralized configuration via `get_http_config()`
- Never hardcode `verify=False`, `timeout=X`, or similar parameters
- HTTP settings (`HTTP_DEFAULT_TIMEOUT`, `HTTP_VERIFY_TLS`) defined once in docker-compose.yml

**Bad:**
```python
response = requests.post(url, json=body, timeout=10, verify=False)
```

**Good:**
```python
response = requests.post(url, json=body, **get_http_config())
```

### Global Constants at Module Top
- All global constants and variables must be consolidated at the start of each module
- This ensures visibility and makes it easy to evaluate necessity and placement
- Environment-read constants should be declared immediately after imports

## 2. Code Cleanliness

### No Defensive Programming That Obscures Logic
- **Remove try/except/print wrappers** that hide the real logic
- Let exceptions propagate naturally - don't catch and print
- If you need error handling, be specific about what you're catching

**Bad:**
```python
try:
    result = _fetch_data()
    return result
except Exception as e:
    print(f"Error: {e}")
    return None
```

**Good:**
```python
return _fetch_data()  # Let it fail naturally
```

### Eliminate Unnecessary Wrapper Functions
- Don't create wrapper functions that just call another function
- If a function doesn't add value (validation, transformation, or orchestration), remove it
- Keep the code path direct and obvious

**Bad:**
```python
def _compute_delegation(principal_id):
    return compute_delegation_chain(principal_id)
```

**Good:**
```python
# Just call compute_delegation_chain directly
```

### Function Parameters Should Have Justifiable Defaults
- Default parameter values are acceptable **only for business logic** (e.g., user preference defaults)
- Defaults should not hide bugs or API contract violations
- When receiving external data, validate strictly rather than accepting defaults

**Good use of defaults:**
```python
def coerce_int(value: Any, default: int) -> int:
    # Business logic: user preference with fallback
    if value is None:
        return default
    return int(value)
```

**Bad use of defaults:**
```python
def coerce_dict(value: Any, default: dict = {}) -> dict:
    # Hides bugs - should raise on invalid type instead
    return value if isinstance(value, dict) else default
```

## 3. Architecture Principles

### Respect PEP/PDP Separation
- **Policy Enforcement Points (PEP)** fetch data only
- **Policy Decision Points (PDP)** make authorization decisions
- Never filter or pre-process authorization data at the PEP level
- Pass complete information to OPA and let OPA make all decisions

**Bad (PEP filtering data):**
```python
has_action = action in effective_actions  # PEP making decision
opa_input["delegation"]["has_action"] = has_action
```

**Good (PEP provides raw data):**
```python
opa_input["delegation"]["effective_actions"] = effective_actions
# OPA decides: input.action.name in input.delegation.effective_actions
```

### Explicit Over Implicit
- Make business logic and authorization rules **visible and explicit**
- Avoid "magic" behavior or hidden assumptions
- If something can fail, make it fail loudly rather than silently continuing

## 4. Code Quality

### Run Linters Before Committing
- Use `ruff` and `pylint` to catch issues early
- Remove unused imports
- Avoid unnecessary f-strings (use regular strings when no interpolation needed)
- Fix all linting warnings before considering code complete

### Consistent Patterns Across Services
- When multiple services need the same functionality, use shared libraries
- Ensure all services follow the same patterns for:
  - HTTP client configuration
  - Environment variable reading
  - Error handling
  - Logging

## 5. Testing and Observability

### Test Output Should Be Informative
- Always show **detailed failure reasons**, not just counts
- Include context (item IDs, reason codes, advice messages)
- Make test output consistent across all test cases
- Don't hide information that would help debug issues

**Bad:**
```python
print(f"Results: Allow={allowed}, Deny={denied}")
```

**Good:**
```python
print(f"Results: Allow={allowed}, Deny={denied}")
if denied > 0:
    show_deny_details(results)  # Show item IDs and reason codes
```

### Regression Tests Are Critical
- All changes must pass existing regression tests
- Test count: **9/9 tests must pass**
- Tests validate: delegation chains, persona matching, anti-spoofing, cost limits, transitive delegations

## 6. Documentation

### Configuration Changes Require Documentation
- When adding new environment variables, document them in:
  - docker-compose.yml (with comments)
  - README.md or relevant documentation
  - Code comments explaining purpose

### Self-Documenting Code
- Variable names should clearly indicate purpose
- Avoid abbreviations unless universally understood
- Use type hints consistently
- Add docstrings for complex functions explaining "why" not just "what"

---

## Summary Checklist for New Code

Before submitting code, verify:

- [ ] All configuration explicit in docker-compose.yml
- [ ] No hardcoded defaults in environment variable reads
- [ ] HTTP calls use `get_http_config()`
- [ ] No hardcoded `verify=False` or timeout values
- [ ] No defensive try/except that obscures logic
- [ ] No unnecessary wrapper functions
- [ ] Function defaults justified (business logic only)
- [ ] PEP/PDP separation respected
- [ ] Linters pass (ruff, pylint)
- [ ] All 9/9 regression tests pass
- [ ] Test output shows detailed failure reasons
- [ ] Global constants at module top
- [ ] Code fails fast on misconfiguration

---

## Philosophy

**Make the code obvious, explicit, and fail-fast.**

Hidden defaults, defensive programming, and silent failures make debugging harder. Let things break loudly when they're wrong, and make all configuration and behavior visible.

When in doubt:
- Choose **explicit over implicit**
- Choose **fail-fast over fail-silent**
- Choose **visible over hidden**
- Choose **direct over wrapped**
