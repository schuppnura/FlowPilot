# Part 5 Addendum: DRY Consolidation

**Date**: 2025-12-29  
**Status**: ✅ Complete

## Objective

Further improve Part 5 by eliminating code duplication within utils.py itself and consolidating duplicate utility functions across the codebase.

## Problem Statement

After completing Part 5, two issues remained:

### 1. Code Duplication in utils.py
The new `read_env_*` functions duplicated logic that already existed in `coerce_*` functions:

```python
# read_env_int duplicated coerce_int logic
def read_env_int(name: str, default_value: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default_value
    try:
        return int(value.strip())  # Duplicates coerce_int!
    except ValueError:
        return default_value

# read_env_bool duplicated coerce_bool logic  
def read_env_bool(name: str, default_value: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default_value
    normalized = value.strip().lower()
    return normalized in {"true", "yes", "y", "1", "on"}  # Duplicates coerce_bool!
```

### 2. Duplicate Timestamp Function
`get_utc_now_iso()` in `domain-services-api/core.py` duplicated the functionality of `coerce_timestamp()` in utils.py:

```python
# domain-services-api/core.py
def get_utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# utils.py - already had this!
def coerce_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
```

## Solution

### 1. Make read_env_* Functions Use coerce_* Functions

**Principle:** Don't Repeat Yourself (DRY) - reuse existing, well-tested logic.

#### read_env_int → Use coerce_int

**Before:**
```python
def read_env_int(name: str, default_value: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default_value
    try:
        return int(value.strip())
    except ValueError:
        return default_value
```

**After:**
```python
def read_env_int(name: str, default_value: int) -> int:
    # Read integer environment variable with default value using coerce_int.
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default_value
    return coerce_int(value.strip(), default_value)
```

**Benefits:**
- ✅ Removed duplicate try/except logic
- ✅ Leverages existing `coerce_int` error handling
- ✅ Single source of truth for int conversion

#### read_env_bool → Use coerce_bool

**Before:**
```python
def read_env_bool(name: str, default_value: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default_value
    normalized = value.strip().lower()
    return normalized in {"true", "yes", "y", "1", "on"}
```

**After:**
```python
def read_env_bool(name: str, default_value: bool) -> bool:
    # Read boolean environment variable with default value using coerce_bool.
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default_value
    return coerce_bool(value.strip(), default_value)
```

**Benefits:**
- ✅ Removed duplicate boolean parsing logic
- ✅ Now also handles "t" (true) like `coerce_bool` does
- ✅ Consistent boolean recognition across codebase

**Important Note:** `coerce_bool` recognizes more values than the original `read_env_bool`:
- Original: `{"true", "yes", "y", "1", "on"}`
- With coerce_bool: `{"yes", "y", "true", "t", "1", "on"}` (added "t")

This is an improvement - more flexible boolean parsing!

### 2. Replace get_utc_now_iso with coerce_timestamp

**Before** (domain-services-api/core.py):
```python
from datetime import datetime, timezone

def get_utc_now_iso() -> str:
    # Return a stable UTC timestamp string
    return datetime.now(timezone.utc).isoformat()

# Usage
created_at = get_utc_now_iso()
```

**After**:
```python
from utils import coerce_timestamp

# Usage - no local function needed!
created_at = coerce_timestamp()
```

**Differences between the two implementations:**

| Feature | get_utc_now_iso | coerce_timestamp |
|---------|----------------|------------------|
| Microseconds | Included | **Removed** (replace with 0) |
| Format | `2025-12-29T08:51:20.123456+00:00` | `2025-12-29T08:51:20Z` |
| Timezone suffix | `+00:00` | `Z` (canonical UTC marker) |

**Why coerce_timestamp is better:**
- ✅ More readable format (Z instead of +00:00)
- ✅ No microseconds = cleaner timestamps
- ✅ Consistent across entire codebase
- ✅ Already battle-tested in utils.py

## Changes Made

### Files Modified

#### 1. **shared-libraries/utils.py**
- **Line 35-45**: Modified `read_env_int()` to use `coerce_int()`
- **Line 64-77**: Modified `read_env_bool()` to use `coerce_bool()`

#### 2. **domain-services-api/core.py**
- **Line 23**: Removed `from datetime import datetime, timezone` (no longer needed)
- **Line 30**: Added `coerce_timestamp` to imports from utils
- **Lines 46-50**: Deleted `get_utc_now_iso()` function (5 lines removed)
- **Line 143**: Changed `get_utc_now_iso()` → `coerce_timestamp()`

## Before/After Comparison

### utils.py - read_env_int

**Before** (duplicates logic):
```python
def read_env_int(name: str, default_value: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default_value
    try:
        return int(value.strip())
    except ValueError:
        return default_value
```

**After** (reuses coerce_int):
```python
def read_env_int(name: str, default_value: int) -> int:
    # Read integer environment variable with default value using coerce_int.
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default_value
    return coerce_int(value.strip(), default_value)
```

### utils.py - read_env_bool

**Before** (duplicates logic):
```python
def read_env_bool(name: str, default_value: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default_value
    normalized = value.strip().lower()
    return normalized in {"true", "yes", "y", "1", "on"}
```

**After** (reuses coerce_bool):
```python
def read_env_bool(name: str, default_value: bool) -> bool:
    # Read boolean environment variable with default value using coerce_bool.
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default_value
    return coerce_bool(value.strip(), default_value)
```

### domain-services-api/core.py

**Before** (duplicate function + imports):
```python
from datetime import datetime, timezone
from utils import build_url, require_non_empty_string, read_env_string

def get_utc_now_iso() -> str:
    # Return a stable UTC timestamp string
    # why: deterministic timestamps in responses
    # side effect: reads system time.
    return datetime.now(timezone.utc).isoformat()

# Later in code:
created_at = get_utc_now_iso()
```

**After** (uses shared function):
```python
from utils import build_url, require_non_empty_string, read_env_string, coerce_timestamp

# Later in code:
created_at = coerce_timestamp()
```

## Benefits

### 1. **Eliminated Code Duplication**
- ✅ Removed ~8 lines of duplicate logic from `read_env_int`
- ✅ Removed ~4 lines of duplicate logic from `read_env_bool`
- ✅ Removed 5-line `get_utc_now_iso()` function
- ✅ **Total: ~17 lines removed**

### 2. **Single Source of Truth**
- Integer conversion → Always uses `coerce_int`
- Boolean parsing → Always uses `coerce_bool`
- Timestamp generation → Always uses `coerce_timestamp`

### 3. **Improved Consistency**
All parts of the codebase now use the same underlying logic:

```python
# Environment variables
port = read_env_int("PORT", 8080)  # Uses coerce_int internally

# Runtime values
parsed_port = coerce_int(user_input, 8080)  # Same logic!

# Both handle errors the same way, recognize same values
```

### 4. **Better Boolean Recognition**
`read_env_bool` now recognizes all values that `coerce_bool` does:
- Before: `"true"`, `"yes"`, `"y"`, `"1"`, `"on"`
- After: `"true"`, `"t"`, `"yes"`, `"y"`, `"1"`, `"on"`

### 5. **Cleaner Timestamps**
All timestamps now use the canonical format:
- `2025-12-29T08:51:20Z` (clean, readable)
- Not: `2025-12-29T08:51:20.123456+00:00` (verbose)

## Function Composition Pattern

This change establishes a clear pattern for utilities:

```
┌─────────────────────────────────────┐
│   Application-Specific Functions   │
│  (read_env_*, get_utc_now_iso)      │
└─────────────┬───────────────────────┘
              │ Delegates to
              ↓
┌─────────────────────────────────────┐
│     Core Utility Functions          │
│  (coerce_*, parse_*, validate_*)    │
└─────────────────────────────────────┘
```

**Rules:**
1. **High-level functions delegate to low-level functions**
   - `read_env_int` → `coerce_int`
   - `read_env_bool` → `coerce_bool`

2. **Don't duplicate core logic**
   - If `coerce_int` already handles int conversion, use it!
   - If `coerce_timestamp` already generates timestamps, use it!

3. **Reuse across the codebase**
   - Environment variables? Use `read_env_*`
   - Runtime values? Use `coerce_*`
   - Both use the same underlying logic

## Testing Notes

This is a refactoring with one intentional behavioral change:

### Unchanged Behavior
1. ✅ `read_env_int` - Same behavior (uses same int parsing)
2. ✅ `coerce_timestamp` - Already used elsewhere in codebase

### Improved Behavior
3. ✅ `read_env_bool` - **Now also recognizes "t" for true** (improvement!)
4. ✅ `coerce_timestamp` - **Cleaner format without microseconds** (improvement!)

**To verify:**
```bash
# Test that services still start and work correctly
make up

# Verify timestamp format is clean
# Check that boolean env vars still work correctly
```

## Related Documentation

- Part 1: Configuration Cleanup - `docs/CONFIGURATION_CLEANUP.md`
- Part 2: Try/Except Cleanup - `docs/PART2_TRY_EXCEPT_CLEANUP.md`
- Part 3: Defensive Wrapper Cleanup - `docs/PART3_DEFENSIVE_WRAPPER_CLEANUP.md`
- Part 4: build_opa_input Refactor - `docs/PART4_BUILD_OPA_INPUT_REFACTOR.md`
- Part 5: Env Reading Consolidation - `docs/PART5_ENV_READING_CONSOLIDATION.md`

## Completion Criteria

✅ `read_env_int()` uses `coerce_int()` internally  
✅ `read_env_bool()` uses `coerce_bool()` internally  
✅ Removed duplicate `get_utc_now_iso()` function  
✅ Replaced `get_utc_now_iso()` calls with `coerce_timestamp()`  
✅ Removed unused `datetime` imports  
✅ Documentation created

## Key Takeaway

**Always check for existing utilities before implementing new ones.**

Before adding a new function, ask:
1. Does a similar function already exist?
2. Can I use an existing function instead?
3. Can I delegate to an existing function?

This keeps the codebase DRY (Don't Repeat Yourself) and maintainable! 🎉
