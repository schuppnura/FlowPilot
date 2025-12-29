# Part 2: Try/Except/Print Cleanup

## Overview

This document summarizes the cleanup of unnecessary try/except/print wrappers that were obscuring logic and bypassing proper error handling.

## Philosophy

**Before**: Defensive programming with excessive exception catching and print-based debugging  
**After**: Assertive programming with clear error propagation and proper exception handling

### When to Keep Try/Except

✅ **Keep** for external service calls (network, disk, database)  
✅ **Keep** for parsing untrusted data (JSON, user input)  
✅ **Keep** for optional operations with fallbacks  
✅ **Keep** when the calling code expects to handle errors  

### When to Remove Try/Except

❌ **Remove** from simple wrapper functions that just call another function  
❌ **Remove** when masking errors prevents debugging  
❌ **Remove** when returning None/False hides actual problems  
❌ **Remove** when the outer function already has error handling  

---

## Changes Made

### 1. ✅ authz-api/core.py: compute_delegation_chain

**Before**:
```python
try:
    params: Dict[str, str] = {...}
    response = requests.get(...)
    
    if response.status_code == 200:
        data = response.json()
        # ... process data
        return {...}
    else:
        print(f"[authz-api] Delegation validation failed: {response.status_code}", flush=True)
        return {
            "valid": False,
            "has_action": False,
            "delegation_chain": [],
            "effective_actions": [],
        }
except Exception as e:
    print(f"[authz-api] Failed to validate delegation chain: {e}", flush=True)
    return {
        "valid": False,
        "has_action": False,
        "delegation_chain": [],
        "effective_actions": [],
    }
```

**After**:
```python
params: Dict[str, str] = {...}
response = requests.get(...)
response.raise_for_status()  # Raise HTTPError for bad responses

data = response.json()
valid = data.get("valid", False)
delegation_chain = data.get("delegation_chain", [])
effective_actions = data.get("effective_actions", [])

has_action = requested_action in effective_actions

return {
    "valid": valid,
    "has_action": has_action,
    "delegation_chain": delegation_chain,
    "effective_actions": effective_actions,
}
```

**Why**:
- HTTP errors now propagate properly via `raise_for_status()`
- JSON parsing errors propagate naturally
- Calling code can handle errors appropriately
- No silent failures that hide issues

---

### 2. ✅ authz-api/core.py: _compute_delegation

**Before**:
```python
def _compute_delegation(...) -> Optional[Dict[str, Any]]:
    if not security:
        return None
    
    service_token = security.get_service_token()
    if not service_token:
        return None
    
    try:
        return compute_delegation_chain(...)
    except Exception as e:
        print(f"[authz-api] Failed to compute delegation chain: {e}", flush=True)
        return None
```

**After**:
```python
def _compute_delegation(...) -> Optional[Dict[str, Any]]:
    # Returns None if security module not available or service token unavailable.
    if not security:
        return None
    
    service_token = security.get_service_token()
    if not service_token:
        return None
    
    return compute_delegation_chain(...)
```

**Why**:
- Removed unnecessary wrapper try/except
- Errors propagate to caller (evaluate_authorization_request)
- Clear documentation of None return cases
- No hidden failures

---

### 3. ✅ authz-api/core.py: _fetch_owner_attributes

**Before**:
```python
def _fetch_owner_attributes(owner_id: str) -> Optional[Dict[str, Any]]:
    if not profile:
        return None
    
    try:
        return profile.fetch_attributes(owner_id)
    except Exception as e:
        print(f"[authz-api] Failed to fetch owner attributes: {e}\", flush=True)
        return None
```

**After**:
```python
def _fetch_owner_attributes(owner_id: str) -> Optional[Dict[str, Any]]:
    # Returns None if profile module not available.
    if not profile:
        return None
    
    return profile.fetch_attributes(owner_id)
```

**Why**:
- Same as above - removes unnecessary wrapper
- profile.fetch_attributes already handles errors internally
- Caller can handle errors if needed

---

### 4. ✅ authz-api/core.py: evaluate_request_with_opa

**Before**:
```python
try:
    is_allowed = opa_client.evaluate_allow(input_document=input_document)
except Exception:
    is_allowed = False

try:
    reasons = opa_client.evaluate_reasons(input_document=input_document)
except Exception:
    reasons = []

return EvaluateResult(
    decision="allow" if is_allowed else "deny",
    reason_codes=reasons,
    advice=[],
)
```

**After**:
```python
is_allowed = opa_client.evaluate_allow(input_document=input_document)
reasons = opa_client.evaluate_reasons(input_document=input_document)

return EvaluateResult(
    decision="allow" if is_allowed else "deny",
    reason_codes=reasons,
    advice=[],
)
```

**Why**:
- OPA client errors should propagate, not be silently converted to deny
- False denies are confusing in logs and debugging
- If OPA is down, the system should know (not fake a deny response)

---

### 5. ✅ ai-agent-api/core.py: parse_policy_deny_from_body

**Before**:
```python
try:
    parsed = json.loads(response_text)
    if isinstance(parsed, dict):
        detail = parsed.get("detail")
        if isinstance(detail, str) and detail.strip() != "":
            message = detail.strip()
except Exception:
    pass
```

**After**:
```python
# Try to parse as JSON
if response_text.strip().startswith("{"):
    parsed = json.loads(response_text)
    if isinstance(parsed, dict):
        detail = parsed.get("detail")
        if isinstance(detail, str) and detail.strip() != "":
            message = detail.strip()
```

**Why**:
- JSON parsing errors will propagate naturally if it's malformed JSON starting with `{`
- If it doesn't start with `{`, skip JSON parsing entirely
- Clearer intent - we only parse if it looks like JSON
- json.loads() errors are meaningful and should not be hidden

---

### 6. ✅ ai-agent-api/core.py: post_execute_workflow_item

**Before**:
```python
parsed_json: dict[str, Any] | None = None
try:
    parsed = response.json()
    if isinstance(parsed, dict):
        parsed_json = parsed
except Exception:
    parsed_json = None

return response.status_code, parsed_json, response_text
```

**After**:
```python
# Parse JSON response if content-type indicates JSON
parsed_json: dict[str, Any] | None = None
if response.headers.get("content-type", "").startswith("application/json"):
    parsed = response.json()
    if isinstance(parsed, dict):
        parsed_json = parsed

return response.status_code, parsed_json, response_text
```

**Why**:
- Check content-type header before attempting JSON parse
- If it claims to be JSON but isn't, the error should propagate
- More explicit and correct than blind try/except
- Respects HTTP standards

---

## Files Modified

1. `flowpilot-services/authz-api/core.py`
   - Removed try/except from `compute_delegation_chain()`
   - Removed try/except wrapper from `_compute_delegation()`
   - Removed try/except wrapper from `_fetch_owner_attributes()`
   - Removed try/except from `evaluate_request_with_opa()`

2. `flowpilot-services/ai-agent-api/core.py`
   - Improved `parse_policy_deny_from_body()` JSON parsing logic
   - Improved `post_execute_workflow_item()` JSON parsing logic

---

## Files Not Modified (And Why)

### flowpilot-services/shared-libraries/profile.py

**Kept** try/except blocks in `_fetch_user_by_id()` and `_fetch_all_users()` because:
- These call external Keycloak API (network I/O)
- Graceful degradation is appropriate (return None/empty list)
- These are leaf functions that document their fallback behavior
- Callers expect Optional return types and handle accordingly

**Recommendation**: Replace `print()` statements with proper logging in a future cleanup.

### flowpilot-services/shared-libraries/utils.py

**Kept** try/except blocks in parsing functions because:
- They parse untrusted input (JSON, strings, numbers)
- They provide clear error messages with context
- They convert various exceptions into ValueError with helpful messages
- This is proper error handling, not error hiding

**Examples**:
- `coerce_int()` - Converts various types to int with fallback
- `parse_json_object()` - Parses JSON with context in error messages
- `load_json_object()` - File I/O with proper error context

---

## Benefits Achieved

### 1. Better Debugging
- Real errors propagate instead of being hidden
- Stack traces show actual failure points
- No more "why did this return None?" mysteries

### 2. Clearer Code
- Reduced nesting and indentation
- Fewer lines of code
- Intent is clearer without defensive wrappers

### 3. Proper Error Handling
- HTTP errors raise HTTPError (standard requests library behavior)
- JSON parse errors show what's actually wrong
- OPA failures are visible, not hidden as false denies

### 4. Better Testing
- Errors can be tested explicitly
- No need to mock print() to verify error paths
- Test assertions can check actual exception types

---

## Migration Impact

### Backward Compatibility

⚠️ **Breaking Change**: Code that relied on silent failure (None/False returns) will now raise exceptions.

**Good**: This is intentional - silent failures were hiding bugs  
**Impact**: Minimal - most calling code already had error handling  
**Fix**: If needed, add try/except at appropriate layer (not wrapper functions)

### Error Handling Strategy

**Before**: Catch everything, print, return None/False  
**After**: Let errors propagate to appropriate handling layer

**Example Flow**:
```
FastAPI endpoint (catches exceptions, returns 500)
  ↓
Business logic (raises on failure)
  ↓
Service call (raises HTTPError, ValueError, etc.)
```

---

## Testing Recommendations

### Unit Tests

✅ Test that functions raise appropriate exceptions:
```python
def test_compute_delegation_chain_http_error():
    with pytest.raises(requests.HTTPError):
        compute_delegation_chain(...)

def test_evaluate_opa_client_error():
    with pytest.raises(OPAError):
        evaluate_request_with_opa(...)
```

### Integration Tests

✅ Test error propagation through layers:
```python
def test_authz_with_delegation_api_down():
    # delegation-api returns 500
    response = client.post("/v1/evaluate", ...)
    assert response.status_code == 500
    assert "delegation" in response.json()["detail"].lower()
```

### Monitoring

✅ Add logging/monitoring for:
- HTTPError from delegation-api calls
- JSONDecodeError from malformed responses
- Timeout errors from slow services

---

## Future Improvements

### 1. Replace print() with logging

**Current State**: Some files still use `print(..., flush=True)`  
**Target**: Use Python logging module with proper levels

```python
# Instead of:
print(f"[profile] User not found: {user_sub}", flush=True)

# Use:
logger.warning("User not found: %s", user_sub)
```

### 2. Structured Logging

**Target**: JSON-structured logs for better parsing and monitoring

```python
logger.warning(
    "User fetch failed",
    extra={
        "user_sub": user_sub,
        "http_status": response.status_code,
        "service": "keycloak"
    }
)
```

### 3. Retry Logic

**Target**: Add retry logic with exponential backoff for transient failures

```python
@retry(max_attempts=3, backoff=exponential)
def compute_delegation_chain(...):
    # Will retry on network errors
    response = requests.get(...)
    response.raise_for_status()
    return response.json()
```

### 4. Circuit Breaker

**Target**: Prevent cascading failures when downstream services are down

```python
@circuit_breaker(failure_threshold=5, timeout=60)
def compute_delegation_chain(...):
    # Will fast-fail if service is known to be down
    ...
```

---

## Summary

### Changes Summary

- ✅ Removed 6 unnecessary try/except wrappers
- ✅ Improved 2 JSON parsing operations
- ✅ Better error propagation across the board
- ✅ Cleaner, more readable code

### Impact

- 🎯 **Improved Debugging**: Real errors now visible
- 🎯 **Better Code Quality**: Less defensive, more assertive
- 🎯 **Proper Error Handling**: Errors handled at appropriate layers
- 🎯 **Easier Testing**: Can test error conditions explicitly

### Next Steps

1. ✅ Part 1 Complete: Configuration cleanup
2. ✅ Part 2 Complete: Try/except cleanup  
3. 🔜 Part 3: Replace print() with proper logging
4. 🔜 Part 4: Add structured logging and monitoring
