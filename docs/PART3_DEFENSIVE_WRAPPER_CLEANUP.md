# Part 3: Defensive Wrapper Function Cleanup

## Overview

This document summarizes the removal of unnecessary defensive wrapper functions that assumed modules might be missing. These wrappers were added for historical testing purposes but are no longer needed in production code.

## Philosophy

**Before**: Defensive programming assuming modules might not be available  
**After**: Assertive programming expecting required dependencies to be present

### Problem with Defensive Wrappers

```python
# Defensive wrapper pattern (BEFORE)
def _compute_delegation(...):
    if not security:  # Module might be missing?
        return None
    
    service_token = security.get_service_token()
    if not service_token:
        return None  # Silent failure
    
    return compute_delegation_chain(...)
```

**Issues**:
1. ❌ **Hidden failures** - Returns None instead of raising errors
2. ❌ **Unclear intent** - Why would security module be missing?
3. ❌ **Extra indirection** - Wrapper adds no value
4. ❌ **Harder debugging** - Silent None return hides real problems

### Assertive Pattern

```python
# Assertive pattern (AFTER)
# Just call the function directly
service_token = security.get_service_token()
if not service_token:
    raise RuntimeError("Service token not available")  # Fail loudly

delegation_result = compute_delegation_chain(...)
```

**Benefits**:
1. ✅ **Clear failures** - Errors are explicit
2. ✅ **Clear intent** - Dependencies are required
3. ✅ **No indirection** - Direct function calls
4. ✅ **Better debugging** - Stack traces show real problems

---

## Changes Made

### 1. ✅ Removed Optional Imports

**Before**:
```python
# Import profile and security for fetching owner attributes and service tokens
try:
    import profile
    import security
except ImportError:
    # Allow core.py to be imported without these if needed for testing
    profile = None
    security = None
```

**After**:
```python
# Required imports for fetching owner attributes and service tokens
import profile
import security
```

**Why**:
- These modules are always required in production
- If they're missing, the service should fail at startup, not at request time
- Test environments should provide these modules (or mock them properly)

---

### 2. ✅ Removed _compute_delegation Wrapper

**Before**:
```python
def _compute_delegation(owner_id: str, principal_id: str, workflow_id: Optional[str], requested_action: str) -> Optional[Dict[str, Any]]:
    # Compute delegation chain from delegation-api.
    # Returns None if security module not available or service token unavailable.
    if not security:
        return None
    
    service_token = security.get_service_token()
    if not service_token:
        return None
    
    return compute_delegation_chain(
        bearer_token=service_token,
        owner_id=owner_id,
        principal_id=principal_id,
        workflow_id=workflow_id,
        requested_action=requested_action,
    )

# Usage
delegation_result = _compute_delegation(owner_id, principal_id, workflow_id, action_name)
```

**After**:
```python
# Inlined directly in evaluate_authorization_request()
service_token = security.get_service_token()
if not service_token:
    raise RuntimeError("Service token not available - cannot validate delegation")

delegation_result = compute_delegation_chain(
    bearer_token=service_token,
    owner_id=owner_id,
    principal_id=principal_id,
    workflow_id=workflow_id,
    requested_action=action_name,
)
```

**Why**:
- No silent None return - raises clear error if token unavailable
- One less function to maintain
- Clearer flow - reader sees exactly what happens
- Error message explains the impact ("cannot validate delegation")

---

### 3. ✅ Removed _fetch_owner_attributes Wrapper

**Before**:
```python
def _fetch_owner_attributes(owner_id: str) -> Optional[Dict[str, Any]]:
    # Fetch owner's autobook attributes and persona from Keycloak.
    # Returns None if profile module not available.
    if not profile:
        return None
    
    return profile.fetch_attributes(owner_id)

# Usage
owner_attributes = _fetch_owner_attributes(owner_id)
```

**After**:
```python
# Inlined directly in evaluate_authorization_request()
owner_attributes = profile.fetch_attributes(owner_id)
```

**Why**:
- No defensive check needed - profile module is required
- One less function to maintain
- profile.fetch_attributes() already returns Optional[Dict], handles its own errors
- Direct call is clearer and simpler

---

### 4. ✅ Removed Defensive Security Check

**Before**:
```python
# Sanitize and validate action name
if security:
    action_name = security.sanitize_string(action_name.strip(), 255)
else:
    action_name = action_name.strip()
```

**After**:
```python
# Sanitize and validate action name
action_name = security.sanitize_string(action_name.strip(), 255)
```

**Why**:
- security module is always available
- No need for fallback behavior
- Simpler code, same result

---

## Complete Example: Before and After

### Before (Defensive)

```python
# Optional imports
try:
    import profile
    import security
except ImportError:
    profile = None
    security = None

# Defensive wrapper functions
def _compute_delegation(...):
    if not security:
        return None
    service_token = security.get_service_token()
    if not service_token:
        return None
    return compute_delegation_chain(...)

def _fetch_owner_attributes(owner_id: str):
    if not profile:
        return None
    return profile.fetch_attributes(owner_id)

# Usage with defensive checks
def evaluate_authorization_request(authzen_request):
    ...
    if owner_id:
        delegation_result = _compute_delegation(...)  # Might return None
        owner_attributes = _fetch_owner_attributes(owner_id)  # Might return None
    
    # Process with potentially None values
    return evaluate_request_with_opa(
        delegation_result=delegation_result,  # Could be None
        owner_attributes=owner_attributes,   # Could be None
    )
```

### After (Assertive)

```python
# Required imports
import profile
import security

# No wrapper functions needed!

# Direct usage with clear error handling
def evaluate_authorization_request(authzen_request):
    ...
    if owner_id:
        # Get service token (fail loudly if unavailable)
        service_token = security.get_service_token()
        if not service_token:
            raise RuntimeError("Service token not available - cannot validate delegation")
        
        # Direct calls to actual functions
        delegation_result = compute_delegation_chain(
            bearer_token=service_token,
            owner_id=owner_id,
            principal_id=principal_id,
            workflow_id=workflow_id,
            requested_action=action_name,
        )
        
        owner_attributes = profile.fetch_attributes(owner_id)
    
    # Process with explicit None handling at call site
    return evaluate_request_with_opa(
        delegation_result=delegation_result,
        owner_attributes=owner_attributes,
    )
```

---

## Files Modified

1. **flowpilot-services/authz-api/core.py**
   - Removed try/except from imports (profile, security)
   - Deleted `_compute_delegation()` wrapper function
   - Deleted `_fetch_owner_attributes()` wrapper function
   - Inlined delegation and attribute fetching in `evaluate_authorization_request()`
   - Removed defensive `if security:` check in `validate_authzen_request()`

**Lines removed**: ~35 lines  
**Lines added**: ~15 lines  
**Net change**: -20 lines, clearer code

---

## Benefits Achieved

### 1. Clearer Dependencies
- Import errors happen at startup, not at request time
- Missing dependencies are immediately obvious
- No ambiguity about what's required

### 2. Better Error Messages
```python
# Before: Silent None return (why?)
delegation_result = None  # What went wrong?

# After: Clear error message
RuntimeError: Service token not available - cannot validate delegation
```

### 3. Simpler Code Flow
```python
# Before: Follow through wrapper
evaluate_authorization_request()
  → _compute_delegation()
    → compute_delegation_chain()

# After: Direct call
evaluate_authorization_request()
  → compute_delegation_chain()
```

### 4. Easier Testing
```python
# Before: Had to mock wrapper functions
@patch('core._compute_delegation')
def test_authz(...):
    ...

# After: Mock actual dependencies
@patch('core.security.get_service_token')
def test_authz(...):
    ...
```

### 5. Better Debugging
```python
# Before: Stack trace shows wrapper
  File "core.py", line 483, in evaluate_authorization_request
    delegation_result = _compute_delegation(...)
  File "core.py", line 433, in _compute_delegation
    return compute_delegation_chain(...)

# After: Stack trace is direct
  File "core.py", line 458, in evaluate_authorization_request
    delegation_result = compute_delegation_chain(...)
```

---

## Migration Impact

### Backward Compatibility

✅ **Fully compatible** for normal usage:
- Services that properly configure security and profile modules work unchanged
- Only breaks if modules were actually missing (which was already broken)

⚠️ **Breaking for tests** that relied on optional imports:
- Tests must now properly mock security and profile modules
- This is better - tests should be explicit about dependencies

### Error Behavior Changes

| Scenario | Before | After |
|----------|--------|-------|
| Security module missing | Silent None return | ImportError at startup |
| Service token unavailable | Silent None return | RuntimeError with message |
| Profile module missing | Silent None return | ImportError at startup |
| Keycloak fetch fails | None return (from profile) | Exception from profile module |

**All changes are improvements** - failures are now explicit and debuggable.

---

## Testing Recommendations

### Unit Tests

Update tests to properly mock dependencies:

```python
# Before: Tests relied on optional imports
def test_without_security():
    # security = None was valid
    result = _compute_delegation(...)
    assert result is None

# After: Mock the required module
@patch('core.security')
def test_authorization(mock_security):
    mock_security.get_service_token.return_value = "token"
    result = evaluate_authorization_request(...)
    assert result.decision == "allow"
```

### Integration Tests

```python
def test_missing_service_token():
    """Test that missing service token fails explicitly"""
    with patch('security.get_service_token', return_value=None):
        with pytest.raises(RuntimeError, match="Service token not available"):
            evaluate_authorization_request(...)

def test_delegation_api_failure():
    """Test that delegation API errors propagate"""
    with patch('requests.get', side_effect=ConnectionError()):
        with pytest.raises(ConnectionError):
            evaluate_authorization_request(...)
```

---

## Related Changes

This cleanup builds on previous parts:

- **Part 1**: Removed hardcoded configuration values
- **Part 2**: Removed try/except wrappers that hid errors
- **Part 3**: Removed defensive wrapper functions (this document)

---

## Future Improvements

### 1. Startup Validation

Add explicit dependency checks at service startup:

```python
def validate_dependencies():
    """Validate all required dependencies are available"""
    try:
        import security
        import profile
    except ImportError as e:
        raise RuntimeError(f"Missing required dependency: {e}")
    
    # Validate environment variables
    if not os.getenv("KEYCLOAK_TOKEN_URL"):
        raise RuntimeError("KEYCLOAK_TOKEN_URL not configured")
    
    # Test connections
    token = security.get_service_token()
    if not token:
        raise RuntimeError("Cannot obtain service token")

# Call at startup
validate_dependencies()
```

### 2. Dependency Injection

For better testability, consider dependency injection:

```python
class AuthzService:
    def __init__(self, security_client, profile_client, opa_client):
        self.security = security_client
        self.profile = profile_client
        self.opa = opa_client
    
    def evaluate_authorization_request(self, authzen_request):
        token = self.security.get_service_token()
        # ...
```

### 3. Health Checks

Add health check endpoint that validates dependencies:

```python
@app.get("/health")
def health():
    checks = {
        "service_token": bool(security.get_service_token()),
        "opa_connection": check_opa_connection(),
        "delegation_api": check_delegation_api(),
        "keycloak": check_keycloak_connection(),
    }
    
    if all(checks.values()):
        return {"status": "healthy", "checks": checks}
    else:
        return {"status": "unhealthy", "checks": checks}, 503
```

---

## Summary

### Changes Summary

- ✅ Removed optional imports (made them required)
- ✅ Deleted 2 defensive wrapper functions
- ✅ Inlined 2 function calls
- ✅ Removed 1 defensive check
- ✅ Added explicit error for missing service token

### Impact

- 🎯 **Clearer Code**: -20 lines, more readable
- 🎯 **Better Errors**: Explicit failures instead of silent None
- 🎯 **Easier Debugging**: Direct stack traces
- 🎯 **Simpler Testing**: Mock actual dependencies, not wrappers
- 🎯 **Faster Failures**: Import errors at startup, not runtime

### Philosophy

**Defensive → Assertive Programming**

Stop assuming things might be broken. If dependencies are required, make them required. If failures should be visible, make them visible. Clear code with explicit errors beats defensive code with hidden failures.

---

## Completed Work

1. ✅ Part 1: Configuration cleanup
2. ✅ Part 2: Try/except cleanup
3. ✅ Part 3: Defensive wrapper cleanup
4. 🔜 Next: Consider logging improvements, dependency injection, health checks
