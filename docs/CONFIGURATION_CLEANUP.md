# Configuration Cleanup - Environment Variables

This document describes the environment variables that were added to replace hardcoded values in the FlowPilot codebase.

## Overview

Hardcoded values have been moved to environment variables to improve configurability and maintainability. All variables have sensible defaults that match the previous hardcoded values, ensuring backward compatibility.

## Authorization Configuration

### ALLOWED_ACTIONS
**Location**: `authz-api/core.py`  
**Default**: `"create,read,write,delete,execute"`  
**Format**: Comma-separated list of action names  
**Description**: Defines the set of valid AuthZEN-compliant action names that can be used in authorization requests.

**Example**:
```bash
ALLOWED_ACTIONS="read,write,execute"
```

### DEFAULT_AUTOBOOK_CONSENT
**Location**: `authz-api/core.py`  
**Default**: `"false"`  
**Format**: Boolean string (`"true"` or `"false"`)  
**Description**: Default autobook consent value when not present in Keycloak user attributes.

### DEFAULT_AUTOBOOK_PRICE
**Location**: `authz-api/core.py`  
**Default**: `"0"`  
**Format**: Integer (EUR amount)  
**Description**: Default maximum cost in EUR for autobook when not present in Keycloak user attributes.

### DEFAULT_AUTOBOOK_LEADTIME
**Location**: `authz-api/core.py`  
**Default**: `"10000"`  
**Format**: Integer (days)  
**Description**: Default minimum days in advance for autobook when not present in Keycloak user attributes.

### DEFAULT_AUTOBOOK_RISKLEVEL
**Location**: `authz-api/core.py`  
**Default**: `"0"`  
**Format**: Integer (risk level)  
**Description**: Default maximum airline risk level for autobook when not present in Keycloak user attributes.

## Delegation Configuration

### DELEGATION_ALLOWED_ACTIONS
**Location**: `delegation-api/main.py`, `delegation-api/core.py`  
**Default**: `"read,execute"`  
**Format**: Comma-separated list of action names  
**Description**: Defines the set of valid actions that can be included in delegation scopes. Also used for self-delegation (when delegate_id equals principal_id).

**Example**:
```bash
DELEGATION_ALLOWED_ACTIONS="read,execute,write"
```

### DELEGATION_DEFAULT_EXPIRY_DAYS
**Location**: `delegation-api/main.py`  
**Default**: `"7"`  
**Format**: Integer (days)  
**Description**: Default expiration time for delegations in days.

### DELEGATION_MIN_EXPIRY_DAYS
**Location**: `delegation-api/main.py`  
**Default**: `"1"`  
**Format**: Integer (days)  
**Description**: Minimum allowed expiration time for delegations.

### DELEGATION_MAX_EXPIRY_DAYS
**Location**: `delegation-api/main.py`  
**Default**: `"365"`  
**Format**: Integer (days)  
**Description**: Maximum allowed expiration time for delegations.

**Example**:
```bash
DELEGATION_DEFAULT_EXPIRY_DAYS=14
DELEGATION_MIN_EXPIRY_DAYS=1
DELEGATION_MAX_EXPIRY_DAYS=180
```

## Uvicorn Server Configuration

These settings apply to all services (authz-api, delegation-api, domain-services-api, ai-agent-api).

### UVICORN_MAX_REQUESTS
**Location**: All service `main.py` files  
**Default**: `"10000"`  
**Format**: Integer  
**Description**: Maximum number of requests a worker will process before being restarted. Helps prevent memory leaks.

### UVICORN_MAX_CONCURRENCY
**Location**: All service `main.py` files  
**Default**: `"100"`  
**Format**: Integer  
**Description**: Maximum number of concurrent connections per worker.

### UVICORN_KEEPALIVE_TIMEOUT
**Location**: All service `main.py` files  
**Default**: `"5"`  
**Format**: Integer (seconds)  
**Description**: Keep-alive timeout for HTTP connections.

**Example**:
```bash
UVICORN_MAX_REQUESTS=20000
UVICORN_MAX_CONCURRENCY=200
UVICORN_KEEPALIVE_TIMEOUT=10
```

## Persona Configuration

### AI_AGENT_PERSONA
**Location**: `domain-services-api/main.py`, `domain-services-api/core.py`  
**Default**: `"ai-agent"`  
**Format**: String (persona name)  
**Description**: Persona used for AI agent service account when making authorization requests. This identifies the service as an AI agent in the authorization policy.

**Example**:
```bash
AI_AGENT_PERSONA="ai-agent"
# Or for a different agent type:
AI_AGENT_PERSONA="medical-assistant"
```

### DELEGATION_PERSONAS
**Location**: OPA policy `auto_book.rego` (documented)  
**Default**: `"ai-agent,travel-agent,secretary"` (hardcoded in policy)  
**Format**: Comma-separated list of persona names  
**Description**: Valid personas that can be delegated to execute workflows on behalf of others. Currently documented in OPA policy but not yet configurable at runtime.

**Note**: These personas are currently hardcoded in the OPA Rego policy. A future enhancement will allow passing these via policy input for full configurability.

**Current Policy Definition**:
```rego
valid_agent_personas := {"travel-agent", "ai-agent", "secretary"}
```

## Security Configuration (Improved)

### AGENT_CLIENT_ID (Usage Improved)
**Location**: `security.py`  
**Default**: N/A (must be set)  
**Description**: The hardcoded reference to `"flowpilot-agent"` in JWT validation logic has been removed. The validation now correctly uses the `AGENT_CLIENT_ID` environment variable that was already defined in docker-compose.yml.

**Before**: JWT validation had hardcoded checks for `"flowpilot-agent"`  
**After**: JWT validation uses `AGENT_CLIENT_ID` environment variable

## Docker Compose Integration

To use these new configuration options, add them to your `docker-compose.yml` service environment sections or to your `.env` file.

### Example docker-compose.yml additions:

```yaml
services:
  flowpilot-authz-api:
    environment:
      # Authorization policy defaults
      - DEFAULT_AUTOBOOK_CONSENT=false
      - DEFAULT_AUTOBOOK_PRICE=0
      - DEFAULT_AUTOBOOK_LEADTIME=10000
      - DEFAULT_AUTOBOOK_RISKLEVEL=0
      - ALLOWED_ACTIONS=create,read,write,delete,execute
      
      # Uvicorn server limits
      - UVICORN_MAX_REQUESTS=10000
      - UVICORN_MAX_CONCURRENCY=100
      - UVICORN_KEEPALIVE_TIMEOUT=5

  flowpilot-delegation-api:
    environment:
      # Delegation configuration
      - DELEGATION_ALLOWED_ACTIONS=read,execute
      - DELEGATION_DEFAULT_EXPIRY_DAYS=7
      - DELEGATION_MIN_EXPIRY_DAYS=1
      - DELEGATION_MAX_EXPIRY_DAYS=365
      
      # Uvicorn server limits
      - UVICORN_MAX_REQUESTS=10000
      - UVICORN_MAX_CONCURRENCY=100
      - UVICORN_KEEPALIVE_TIMEOUT=5

  flowpilot-domain-services-api:
    environment:
      # Persona configuration
      - AI_AGENT_PERSONA=ai-agent
      
      # Uvicorn server limits
      - UVICORN_MAX_REQUESTS=10000
      - UVICORN_MAX_CONCURRENCY=100
      - UVICORN_KEEPALIVE_TIMEOUT=5
```

## Migration Notes

### Backward Compatibility
All changes are **backward compatible**. If environment variables are not set, the defaults match the previously hardcoded values exactly.

### Testing
After deployment, verify that:
1. Authorization requests work with default and custom action sets
2. Delegation creation respects custom expiry limits
3. Service tokens are properly validated (no hardcoded client ID references)
4. All services start successfully with default values

### Production Considerations
1. **Autobook Defaults**: Review and set appropriate defaults for your production environment
2. **Delegation Expiry**: Consider reducing `DELEGATION_MAX_EXPIRY_DAYS` for tighter security
3. **Uvicorn Limits**: Adjust based on expected load and available resources
4. **Allowed Actions**: Ensure action sets are consistent across services

## Benefits

1. **Flexibility**: Configuration can be changed without code modifications
2. **Security**: Easier to enforce different policies per environment (dev/staging/prod)
3. **Maintainability**: Centralized configuration reduces code duplication
4. **Testability**: Different configurations can be tested without code changes
5. **Documentation**: Environment variables are self-documenting

## Related Files Modified

- `flowpilot-services/authz-api/core.py`
- `flowpilot-services/authz-api/main.py`
- `flowpilot-services/delegation-api/main.py`
- `flowpilot-services/delegation-api/core.py`
- `flowpilot-services/domain-services-api/main.py`
- `flowpilot-services/ai-agent-api/main.py`
- `flowpilot-services/shared-libraries/security.py`
