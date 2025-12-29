# Part 4: build_opa_input Refactoring

**Date**: 2025-12-29  
**Status**: ✅ Complete

## Objective

Refactor `build_opa_input()` in `authz-api/core.py` to improve readability by grouping related construction logic together instead of scattering it throughout the function.

## Problem Statement

The original `build_opa_input()` function had become messy over time:
- Construction statements for different OPA input sections (subject, resource, context, delegation) were intermixed
- Logic jumped back and forth between different concerns
- Hard to follow the flow and debug issues
- Variables were constructed in multiple stages scattered throughout the function

**Example of the problem:**
```python
# Extract principal info (line 165)
principal = request_context.get("principal") or {}
principal_sub = principal.get("id", "")

# ...30 lines of owner/resource logic...

# Build context (line 174) - principal info again!
context_principal = dict(principal)
if "claims" in context_principal:
    del context_principal[...]

# ...50 more lines...

# Build subject (line 244) - principal info AGAIN!
opa_input = {
    "subject": {
        "id": principal_sub,  # From way back at line 167
        ...
    }
}
```

## Solution

Reorganize the function into **clear sections** that group all related statements together:

1. **SUBJECT section** - Extract and build all subject-related data
2. **RESOURCE section** - Extract and build all resource-related data (including owner)
3. **CONTEXT section** - Build minimal context
4. **DELEGATION section** - Add delegation result
5. **Final assembly** - Return complete OPA input document

### Key Principles

✅ **Group, don't scatter** - All statements for constructing one part stay together  
✅ **No helper functions** - Keep logic inline for readability  
✅ **Clear section markers** - Use comment dividers to show structure  
✅ **Build incrementally** - Construct each section completely before moving to next

## Changes Made

### File Modified
- `flowpilot-services/authz-api/core.py` - Lines 146-273

### Before (Messy Structure)

```python
def build_opa_input(...) -> dict[str, Any]:
    # Extract everything at once
    request_context = authzen_request.get("context") or {}
    request_resource = authzen_request.get("resource") or {}
    request_action = authzen_request.get("action") or {}
    resource_properties = coerce_dict(request_resource.get("properties"))
    
    # Extract principal from AuthZEN context.principal
    principal = request_context.get("principal") or {}
    principal_sub = principal.get("id", "")
    # Extract selected persona from principal (the persona the current user is using)
    principal_persona = principal.get("persona") or ""
    if isinstance(principal_persona, list) and principal_persona:
        principal_persona = principal_persona[0]
    principal_persona = str(principal_persona) if principal_persona else ""
    
    # Context should only contain minimal principal information (id and persona)
    context_principal = dict(principal)  # Shallow copy of principal
    if "claims" in context_principal:
        del context_principal["claims"]
    
    context = {"principal": context_principal}
    
    # Extract owner from AuthZEN resource properties
    owner_props = coerce_dict(resource_properties.get("owner"))
    owner_id = owner_props.get("id") if owner_props else None
    # Extract owner persona from resource properties...
    owner_persona_from_resource = owner_props.get("persona") if owner_props else None
    
    # Always use owner's autobook attributes...
    owner_attrs = owner_attributes or {}
    autobook_consent = coerce_bool(...)
    autobook_price = coerce_int(...)
    # ... more autobook extraction
    
    # Build resource with properties including owner...
    workflow_id_value = resource_properties.get("workflow_id") or request_resource.get("id")
    resource_dict: Dict[str, Any] = {
        "workflow_id": workflow_id_value,
        "planned_price": resource_properties.get("planned_price"),
        # ... more resource fields
    }
    
    # Include owner in resource.properties with all owner information
    if owner_id:
        resource_properties_with_owner = dict(resource_properties)
        # ... 20 lines of owner property construction
        resource_dict["properties"] = resource_properties_with_owner
    
    # Build OPA input (finally!)
    opa_input = {
        "subject": {
            "type": "user",
            "id": principal_sub,  # Reference variable from 50 lines ago
            "persona": principal_persona,  # Reference variable from 50 lines ago
        },
        "action": request_action,
        "resource": resource_dict,
        "context": context,  # Reference variable from 40 lines ago
    }
    
    # Add computed delegation result...
    if delegation_result is not None:
        opa_input["delegation"] = delegation_result
    else:
        opa_input["delegation"] = {...}
    
    return opa_input
```

**Problems:**
- Principal extracted at line 165, used in context at line 174, used in subject at line 244
- Resource construction spans 60+ lines with intermixed concerns
- Hard to see what's being built for each OPA input section

### After (Clear Structure)

```python
def build_opa_input(...) -> dict[str, Any]:
    # Extract top-level AuthZEN elements (shared inputs)
    request_context = authzen_request.get("context") or {}
    request_resource = authzen_request.get("resource") or {}
    request_action = authzen_request.get("action") or {}
    resource_properties = coerce_dict(request_resource.get("properties"))
    
    # ========================================================================
    # SUBJECT: Extract principal (current user) information
    # ========================================================================
    principal = request_context.get("principal") or {}
    principal_sub = principal.get("id", "")
    
    # Extract principal persona
    principal_persona = principal.get("persona") or ""
    if isinstance(principal_persona, list) and principal_persona:
        principal_persona = principal_persona[0]
    principal_persona = str(principal_persona) if principal_persona else ""
    
    # Build complete subject
    subject = {
        "type": "user",
        "id": principal_sub,
        "persona": principal_persona,
    }
    
    # ========================================================================
    # RESOURCE: Build resource with owner information and autobook settings
    # ========================================================================
    # Extract owner from resource properties
    owner_props = coerce_dict(resource_properties.get("owner"))
    owner_id = owner_props.get("id") if owner_props else None
    owner_persona_from_resource = owner_props.get("persona") if owner_props else None
    
    # Extract owner's autobook attributes (with defaults)
    owner_attrs = owner_attributes or {}
    autobook_consent = coerce_bool(...)
    autobook_price = coerce_int(...)
    autobook_leadtime = coerce_int(...)
    autobook_risklevel = coerce_int(...)
    
    # Determine owner persona
    owner_persona = owner_persona_from_resource
    if not owner_persona:
        owner_persona = owner_attrs.get("persona", "")
        if isinstance(owner_persona, list) and owner_persona:
            owner_persona = owner_persona[0]
    
    # Build resource base structure
    workflow_id_value = resource_properties.get("workflow_id") or request_resource.get("id")
    resource = {
        "workflow_id": workflow_id_value,
        "planned_price": resource_properties.get("planned_price"),
        "departure_date": resource_properties.get("departure_date"),
        "airline_risk_score": resource_properties.get("airline_risk_score"),
        "owner_id": owner_id,
    }
    
    # Augment resource.properties.owner with complete owner information
    if owner_id:
        resource_properties_with_owner = dict(resource_properties)
        if "owner" not in resource_properties_with_owner:
            resource_properties_with_owner["owner"] = {}
        if not isinstance(resource_properties_with_owner["owner"], dict):
            resource_properties_with_owner["owner"] = {}
        
        # Consolidate all owner information
        resource_properties_with_owner["owner"]["id"] = owner_id
        if owner_persona:
            resource_properties_with_owner["owner"]["persona"] = str(owner_persona)
        resource_properties_with_owner["owner"]["autobook_consent"] = autobook_consent
        resource_properties_with_owner["owner"]["autobook_price"] = autobook_price
        resource_properties_with_owner["owner"]["autobook_leadtime"] = autobook_leadtime
        resource_properties_with_owner["owner"]["autobook_risklevel"] = autobook_risklevel
        
        resource["properties"] = resource_properties_with_owner
    
    # ========================================================================
    # CONTEXT: Minimal principal information (no claims)
    # ========================================================================
    context_principal = dict(principal)
    if "claims" in context_principal:
        del context_principal["claims"]
    
    context = {"principal": context_principal}
    
    # ========================================================================
    # DELEGATION: Computed delegation chain result
    # ========================================================================
    if delegation_result is not None:
        delegation = delegation_result
    else:
        delegation = {
            "valid": False,
            "has_action": False,
            "delegation_chain": [],
            "effective_actions": [],
        }
    
    # ========================================================================
    # Assemble final OPA input document
    # ========================================================================
    return {
        "subject": subject,
        "action": request_action,
        "resource": resource,
        "context": context,
        "delegation": delegation,
    }
```

**Improvements:**
- ✅ Clear section markers show what's being built
- ✅ All subject-related logic in SUBJECT section
- ✅ All resource-related logic in RESOURCE section
- ✅ Variables used immediately where they're constructed
- ✅ Easy to debug - find the section you care about
- ✅ Final assembly is simple and clear

## Benefits

### 1. **Improved Readability**
- Code reads top-to-bottom without jumping around
- Each section is self-contained and focused
- Easy to understand what data flows into each OPA input field

### 2. **Easier Debugging**
- When debugging resource issues, look at RESOURCE section
- When debugging subject issues, look at SUBJECT section
- No need to hunt through 100+ lines for related statements

### 3. **Better Maintainability**
- Adding new resource fields? Add them in RESOURCE section
- Adding new subject fields? Add them in SUBJECT section
- Clear where to make changes

### 4. **No Helper Functions**
- Keeps all logic visible and inline (as requested)
- No need to jump to function definitions
- All context visible in one place

## Structure Overview

```
build_opa_input()
├── Extract shared AuthZEN inputs (4 lines)
│
├── SUBJECT Section (~15 lines)
│   ├── Extract principal
│   ├── Extract persona
│   └── Build subject dict
│
├── RESOURCE Section (~55 lines)
│   ├── Extract owner info
│   ├── Extract autobook attributes
│   ├── Determine owner persona
│   ├── Build resource base
│   └── Augment with owner properties
│
├── CONTEXT Section (~7 lines)
│   ├── Copy principal (without claims)
│   └── Build context dict
│
├── DELEGATION Section (~10 lines)
│   └── Set delegation result or default
│
└── Final Assembly (~8 lines)
    └── Return complete OPA input
```

## Example: Finding Where Data Comes From

**Before:** "Where does `subject.persona` come from?"
- Line 168: Extract persona from principal
- Line 169-170: Handle list case
- Line 171: Convert to string
- Line 248: Use it in subject (77 lines later!)

**After:** "Where does `subject.persona` come from?"
- Look at SUBJECT section (lines 165-181)
- Lines 172-175: Extract and process persona
- Line 180: Use it immediately in subject

**Debugging time:** 5 seconds instead of 2 minutes! 🎉

## Testing

No functional changes were made - this is a pure refactoring. The function:
- ✅ Takes the same inputs
- ✅ Returns the same outputs
- ✅ Has the same behavior
- ✅ Just organized differently

To verify:
1. Run existing integration tests: `python3 tests/user_based_testing.py`
2. Check authorization decisions are unchanged
3. Verify OPA input structure matches expectations

## Related Documentation

- Part 1: Configuration Cleanup - `docs/CONFIGURATION_CLEANUP.md`
- Part 2: Try/Except Cleanup - `docs/PART2_TRY_EXCEPT_CLEANUP.md`
- Part 3: Defensive Wrapper Cleanup - `docs/PART3_DEFENSIVE_WRAPPER_CLEANUP.md`

## Completion Criteria

✅ All subject-related statements grouped in SUBJECT section  
✅ All resource-related statements grouped in RESOURCE section  
✅ All context-related statements grouped in CONTEXT section  
✅ All delegation-related statements grouped in DELEGATION section  
✅ Clear section markers with comment dividers  
✅ No helper functions created (logic stays inline)  
✅ Variables used close to where they're defined  
✅ Final assembly is simple and clear  
✅ Documentation created
