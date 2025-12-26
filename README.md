# FlowPilot

FlowPilot is a reference implementation of a small “agentic” workflow with a dedicated authorization service. The project includes:
- A Swift demo client (traveller and travel agent personas)
- Backend microservices (services API, AI agent API, authz API)
- A local OIDC provider (Keycloak) for issuing bearer tokens
- An OPA (Open Policy Agent) policy engine that evaluates Rego policies

This repository previously experimented with ***REMOVED***, OCI policy bundles, and an HTTPS registry proxy. That approach has been removed from the default developer workflow in favor of a simpler, more transparent OPA server-mode setup.

## Architecture at a glance

1. PDP: OPA server for ABAC. It evaluates relationship-based delegation and permissions via an authorization graph.

2. An AuthZ integration layer that acts as integration between PEP and PDP and maintaining the graph for workflow ownership relations. It validates AuthZEN-compliant requests and extracts user claims from the AuthZEN context.principal.claims.

3. PEP using PDP authorization as a domain backend that owns workflow state (system of record) in the context of a travel agent use case: autonomous booking is gated by attribute-based policy conditions (consent, cost, advance days, airline risk) after delegation is verified.

4. Keycloak as the IdP with OIDC Authorization Code + PKCE for the desktop client and Client Credntails for Agentic AI servers. It shows end-to-end authentication: bearer token validation across all services with service-to-service authentication.

5. An Agentic AI server that executes workflow items item-by-item to produce mixed allow/deny outcomes in a single run.

## Security & Privacy

FlowPilot implements **defense-in-depth security** with multiple layers of protection:

### Key Security Features ✨

- **JWKS-based JWT validation** - Zero network calls per token validation, locally cached public keys
- **Comprehensive input validation** - 4-layer validation: Pydantic models, path parameters, string sanitization, request size limits
- **Injection attack prevention** - Automatic control character rejection, optional signature scanning for SQL/XSS/Command injection
- **Security headers** - 6 protective HTTP headers on all API responses
- **Production-safe error handling** - Sanitized error messages prevent information leakage
- **Privacy by design** - Zero PII exposure to LLMs, minimal PII handling (UUID only)

### Privacy by Design
- **Zero PII exposure to LLM**: No personally identifiable information is shared with AI agents
- **Minimal PII handling**: Backend services only process `sub` (UUID) from tokens
- **Authorization graph**: Delegation and permissions tracked by subject identifiers

### Authentication & Token Validation

All API endpoints (except health checks) require bearer token authentication using **JWKS-based JWT validation** (no network calls per request).

#### JWT Validation Checks (Best Practices) ✓

1. **Signature verification** - Validates JWT signature using JWKS public keys (cached locally)
2. **Expiration (exp)** - Required and verified, rejects expired tokens
3. **Not Before (nbf)** - Verified, rejects tokens not yet valid
4. **Issued At (iat)** - Required and checked for future-dated tokens
5. **Issuer (iss)** - Required and verified against expected issuer
6. **Audience (aud)** - Verified if configured
7. **Subject (sub)** - Required and must be non-empty
8. **Token Type (typ)** - Validates it's a proper Bearer/Access token
9. **Clock skew tolerance** - 10 seconds leeway for time differences
10. **Algorithm whitelist** - Only allows RS256/384/512 and ES256/384/512 (no HS algorithms)

**Protections:**
- Expired tokens
- Tokens used before their valid time
- Tokens from wrong issuers
- Tokens for wrong audiences
- Missing required claims
- Invalid signatures
- Time manipulation attacks
- Algorithm confusion attacks

**Configuration:**
```bash
# Required environment variables
export KEYCLOAK_JWKS_URI="https://keycloak.example.com/realms/myrealm/protocol/openid-connect/certs"
export KEYCLOAK_ISSUER="https://keycloak.example.com/realms/myrealm"
export KEYCLOAK_AUDIENCE="account"  # Optional
```

### Input Validation & Sanitization

All API endpoints implement comprehensive input validation:

#### 1. **Pydantic Model Validation**
- Length constraints (1-255 characters for IDs)
- Type validation (strings, booleans, dates)
- Custom validators for IDs, UUIDs, and ISO dates
- Automatic sanitization of all string inputs

#### 2. **Path Parameter Validation**
- All URL path parameters validated before processing
- ID format: alphanumeric, hyphens, underscores only
- Maximum length enforcement (255 characters)

#### 3. **String Sanitization**
- Control character rejection (prevents injection attacks)
- Hard length limits (10,000 characters default)
- Optional signature scanning for:
  - SQL injection patterns
  - XSS patterns
  - Command injection patterns
  - Path traversal patterns

#### 4. **Request Body Size Limits**
- Default: 1MB per request
- Configurable via `MAX_REQUEST_SIZE_MB` environment variable
- Protects against memory exhaustion attacks

**Configuration:**
```bash
# Optional: Enable payload signature scanning (disabled by default)
export ENABLE_PAYLOAD_SIGNATURE_SCAN=1

# Optional: Configure request size limits
export MAX_REQUEST_SIZE_MB=1
export MAX_STRING_LENGTH=10000

# Optional: Disable detailed error messages in production
export INCLUDE_ERROR_DETAILS=0
```

### Security Headers

All API responses include security headers:
- `X-Content-Type-Options: nosniff` - Prevents MIME sniffing
- `X-Frame-Options: DENY` - Prevents clickjacking
- `X-XSS-Protection: 1; mode=block` - XSS protection for older browsers
- `Content-Security-Policy: default-src 'none'` - Restrictive CSP
- `Referrer-Policy: no-referrer` - Prevents referrer leakage
- `Permissions-Policy` - Disables geolocation, microphone, camera

### Authorization Architecture

FlowPilot's authorization system is built around **Open Policy Agent (OPA)** with Rego policies, forming the **core authorization decision engine** for the platform. This ABAC (Attribute-Based Access Control) system evaluates authorization requests based on user attributes, resource properties, delegation relationships, and business rules.

- **`flowpilot-authz-api`** - Authorization façade for policy decisions
  - Validates access tokens via JWKS (for service-to-service authentication)
  - Validates AuthZEN-compliant requests (requires context.principal with id and claims)
  - Extracts user claims from AuthZEN context.principal.claims
  - Fetches owner information and delegation data from workflow properties and delegation-api (PIP)
  - Normalizes and coerces input data before policy evaluation (using `coerce_*` functions)
  - Calls OPA to evaluate Rego policies
  - Returns allow/deny decisions with optional reason codes and advice

- **`opa`** - Open Policy Agent in server mode
  - Evaluates attribute-based access control (ABAC) policies
  - Policies mounted from repository (`infra/opa/policies/`)
  - Supports relationship-based delegation via authorization graph
  - Local policy editing with hot reload

#### OPA Policy: The Core Authorization Engine

The `auto_book.rego` policy (`infra/opa/policies/auto_book.rego`) is the **core authorization logic** for FlowPilot. It implements a multi-gate authorization system that evaluates requests through a series of checks:

**Policy Package**: `auto_book`

**Main Decision Rule**: `allow` (boolean) - All gates must pass for authorization to succeed.

**Authorization Gates** (evaluated in order):

1. **Anti-Spoofing & Delegation Check** (`authorized_principal`)
   - Ensures the principal (user making the request) is authorized to act on the resource
   - **Owner-initiated execution**: Principal must be the owner AND selected persona must match owner's persona
   - **Delegated execution**: Principal must have a valid delegation chain from the owner AND selected persona must be "travel-agent"
   - Supports direct delegations and 2-hop delegation chains
   - Delegations can be workflow-scoped or general (applies to all workflows)

2. **Consent Gate** (`has_consent`)
   - User must have explicitly consented to auto-booking
   - Uses `user.autobook_consent` attribute (coerced to boolean)

3. **Cost Limit Gate** (`within_cost_limit`)
   - Total trip cost (`resource.planned_price`) must not exceed user's maximum (`user.autobook_price`)
   - Prevents unauthorized spending

4. **Advance Notice Gate** (`sufficient_advance`)
   - Departure date (`resource.departure_date`) must be at least `user.autobook_leadtime` days in the future
   - Ensures adequate planning time
   - Input must be in RFC3339 format (normalized before policy evaluation)

5. **Risk Gate** (`acceptable_risk`)
   - Airline risk score (`resource.airline_risk_score`) must not exceed user's threshold (`user.autobook_risklevel`)
   - If no risk score is provided, this gate passes (optional check)

**Persona-Based Authorization**:

The policy enforces persona matching to prevent unauthorized persona usage:

- **Owner execution**: Selected persona must match the persona that was active when the workflow was created
- **Delegated execution**: Selected persona must be "travel-agent" (delegation only works for travel agents)
- Prevents users from accessing resources using personas they don't own or aren't authorized to use

**Delegation System**:

- Delegations are managed via the `delegation-api` and passed to OPA as PIP (Policy Information Point) data
- Supports workflow-scoped delegations (applies only to a specific workflow) and general delegations (applies to all workflows)
- Delegations have expiration times and can be revoked
- Supports up to 2-hop delegation chains (owner → intermediate → delegate)
- Delegations are evaluated declaratively by the policy

**Reason Codes** (returned when authorization is denied):

The policy returns specific reason codes to help understand why authorization failed:

- `auto_book.not_delegated` - Travel agent tried to access a trip without delegation
- `auto_book.principal_spoofing` - Non-travel-agent principal tried to access without being owner or having delegation
- `auto_book.principal_missing` - Principal persona is not set/undefined (backward compatibility)
- `auto_book.persona_mismatch` - Owner's selected persona doesn't match the persona used when creating the workflow
- `auto_book.delegation_requires_travel_agent_persona` - Delegated execution requires "travel-agent" persona but different persona was selected
- `auto_book.no_consent` - User has not consented to auto-booking
- `auto_book.cost_limit_exceeded` - Trip cost exceeds user's maximum price limit
- `auto_book.insufficient_advance_notice` - Departure date is too soon (less than required lead time)
- `auto_book.airline_risk_too_high` - Airline risk score exceeds user's risk threshold

**Input Normalization**:

All input data is normalized **before** being passed to the OPA policy. The policy assumes all input is already in the correct format:

- **Dates**: Must be in RFC3339 format (e.g., `2026-01-16T00:00:00Z`). Date-only strings (e.g., `2026-01-16`) are converted to RFC3339 at midnight UTC by `coerce_date_to_rfc3339()`.
- **Booleans**: Must be boolean values. "Yes"/"No" strings are coerced to booleans by `coerce_yes_no_to_bool()`.
- **Numbers**: Must be numeric values. Strings are coerced to integers/floats by `coerce_int()`.

Normalization functions are defined in `shared-libraries/utils.py` and prefixed with `coerce_*`.

**Policy Input Structure**:

```rego
input = {
  "user": {
    "sub": "principal-subject-id",           # Principal making the request (from context.principal.id)
    "persona": "travel-agent",               # Principal's selected persona (from context.principal.persona)
    "autobook_consent": true,                # User's consent (from owner's Keycloak attributes)
    "autobook_price": 1500,                  # Maximum price limit (from owner's Keycloak attributes)
    "autobook_leadtime": 7,                  # Minimum days in advance (from owner's Keycloak attributes)
    "autobook_risklevel": 2                  # Maximum risk level (from owner's Keycloak attributes)
  },
  "action": {
    "name": "book",
    "properties": {}
  },
  "resource": {
    "workflow_id": "w_123",                  # Workflow ID (for delegation scope matching)
    "planned_price": 250,                    # Trip cost
    "departure_date": "2026-01-16T00:00:00Z", # Departure date (RFC3339 format)
    "airline_risk_score": 1,                 # Airline risk score
    "owner_id": "owner-subject-id",          # Workflow owner ID (from workflow properties)
    "owner_persona": "traveler"              # Owner's persona when workflow was created
  },
  "delegations": [                           # PIP data from delegation-api
    {
      "principal_id": "owner-id",
      "delegate_id": "delegate-id",
      "workflow_id": "w_123",                # null for general delegations
      "expires_at": "2026-01-02T00:00:00Z",
      "revoked_at": null
    }
  ]
}
```

**Policy Evaluation Flow**:

1. PEP (domain-services-api or ai-agent-api) calls `authz-api` with an AuthZEN-compliant request
2. `authz-api` extracts principal information from `context.principal` (not `subject.id` which is the agent/service)
3. `authz-api` fetches owner information from workflow properties (set by domain-services-api when workflow was created)
4. `authz-api` fetches delegation data from `delegation-api` (PIP)
5. `authz-api` normalizes all input using `coerce_*` functions
6. `authz-api` builds OPA input document with normalized data
7. OPA evaluates the `auto_book.allow` rule and `auto_book.reasons` rule
8. `authz-api` maps OPA response to AuthZEN-compliant response with decision and reason codes

**Design Considerations**:

- **Policy-first approach**: Authorization logic lives in Rego, not in application code, enabling policy-as-code practices
- **Declarative delegation**: Delegation relationships are evaluated declaratively by the policy, not imperatively
- **Attribute-based**: Decisions are based on user attributes (consent, price limits, lead time, risk tolerance) rather than roles
- **Persona-aware**: Supports multiple personas per user with persona matching to prevent unauthorized persona usage
- **Normalized input**: All normalization happens before policy evaluation, keeping the policy focused on business logic
- **Auditable**: All authorization decisions include reason codes for audit trails and debugging

### Error Handling

- **Production-safe error messages**: Internal details hidden when `INCLUDE_ERROR_DETAILS=0`
- **Generic error responses**: Database, file system, network errors sanitized
- **404 responses**: Generic "not found" messages (no enumeration)
- **403 responses**: Generic "permission denied" (no detailed reasons)

### Security Quick Reference

**Authentication:**
- All endpoints (except `/health`) require valid JWT bearer tokens
- Tokens validated locally using JWKS (no network latency)
- 10 JWT claims verified per best practices

**Input Validation:**
- All request bodies validated with Pydantic models
- All path parameters sanitized and length-limited
- All strings checked for control characters and length limits
- Optional attack signature scanning (SQL, XSS, command injection, path traversal)

**Defense in Depth:**
- Request size limits (1MB default)
- Security headers on all responses
- Error message sanitization
- No PII exposure to AI agents

**Production Deployment:**
```bash
export INCLUDE_ERROR_DETAILS=0              # Hide internal error details
export ENABLE_PAYLOAD_SIGNATURE_SCAN=1      # Enable attack signature detection
export MAX_REQUEST_SIZE_MB=1                # Limit request body size
export MAX_STRING_LENGTH=10000              # Limit string field lengths
```

## Quick start (Docker Compose)

From the repo root:

```bash
docker compose up -d --build
docker compose ps
```

To see OPA startup logs:

```bash
docker compose logs -f opa
```

To see authz API logs:

```bash
docker compose logs -f flowpilot-authz-api
```

### Verify OPA is reachable (inside the compose network)

This avoids host-port assumptions and is the most reliable check:

```bash
docker run --rm --network flowpilot_default curlimages/curl:8.5.0 -sS   http://opa:8181/health
```

Expected output is JSON indicating healthy status (exact fields vary by OPA version).

### Verify the policy is loaded

Example: evaluate the `auto_book` policy directly in OPA (the repository includes `auto_book.rego` under the mounted policies directory).

```bash
docker run --rm --network flowpilot_default curlimages/curl:8.5.0 -sS   -H "Content-Type: application/json"   -d '{
    "input": {
      "user": {
        "sub": "test-user-id",
        "autobook_consent": true,
        "autobook_price": 1500,
        "autobook_leadtime": 7,
        "autobook_risklevel": 2,
        "claims": {}
      },
      "action": {"name": "book"},
      "resource": {
        "planned_price": 250,
        "departure_date": "2026-01-16",
        "airline_risk_score": 1
      }
    }
  }'   http://opa:8181/v1/data/auto_book/allow
```

Expected result:

```json
{"result":true}
```

If you see `{"result":false}`, check the input payload against the policy conditions and/or query the policy reason:

```bash
docker run --rm --network flowpilot_default curlimages/curl:8.5.0 -sS   -H "Content-Type: application/json"   -d '{"input":{...}}'   http://opa:8181/v1/data/auto_book/reason
```

## Policy development workflow

### Policy location

The compose file mounts a policy directory into the OPA container. Recommended layout:

- `infra/opa/policies/`
  - `auto_book.rego`
  - other policy modules
- `infra/opa/data/` (optional)
  - static data documents consumed by policy

If you prefer to keep policies alongside the authz service, that also works as long as the OPA container mounts the correct path.

### Validate and test policies locally

Run tests inside the OPA container:

```bash
docker compose exec -T opa opa test /policies -v
```

(Adjust `/policies` if your compose mounts to a different path.)

### Reload policies

The simplest workflow is a container restart:

```bash
docker compose restart opa
```

If you want automatic reload on file changes, you can run OPA with `--watch` in the compose `command:` (see `docker-compose.yml`), but note that file watching behavior depends on the container filesystem and your Docker Desktop configuration.

## flowpilot-authz-api integration

`flowpilot-authz-api` talks to OPA over HTTP. In Compose, the correct way to refer to OPA is via the service name (`opa`), not `127.0.0.1`:

- `OPA_URL=http://opa:8181`
- Policy package/rule typically:
  - package: `auto_book`
  - decision rule: `allow` (boolean)

If you expose authz-api to the host, call it using its published port (see `docker-compose.yml`). The OpenAPI specification is available in `flowpilot-authz.openapi.yaml`.

## Troubleshooting

### OPA is running but requests fail

- Confirm you are calling the correct network endpoint:
  - Inside compose network: `http://opa:8181/...`
  - From the host: only works if the OPA service publishes a host port.

### `MANIFEST_UNKNOWN`, registry, HTTPS proxy errors (legacy)

Those errors are typically caused by OCI/registry-based policy distribution attempts (OCI manifest types, Accept headers, TLS, namespace rewrite rules). The current default FlowPilot workflow does not require an OCI registry, nginx registry proxy, or ***REMOVED***.

If you still have legacy services in your compose file (registry, registry-proxy, ***REMOVED***), remove or disable them so they cannot interfere with your network and ports.

### Authz API cannot reach OPA

If you see connection errors in `flowpilot-authz-api` logs:
- Ensure the `opa` service is running: `docker compose ps`
- Ensure the authz container uses `OPA_URL=http://opa:8181` (service name routing), not `localhost`.

## Repository structure (selected)

- `services/flowpilot-authz-api/` authorization API
- `services/flowpilot-domain-services-api/` travel domain APIs
- `services/flowpilot-ai-agent-api/` AI agent API
- `services/shared-libraries/` shared Python utilities
- `infra/opa/` OPA policy and data (recommended)
- `infra/keycloak/` Keycloak realm config and certs

## Notes

This repo is intended as a practical reference implementation. The design goal for policy loading is to keep the developer loop short and observable:
- edit Rego locally
- restart (or watch) OPA
- call OPA directly to validate
- call flowpilot-authz-api to validate end-to-end behavior
