# FlowPilot

FlowPilot is a reference implementation of a small “agentic” workflow with a dedicated authorization service. The project includes:
- A Swift demo client (traveller and travel agent personas)
- Backend microservices (services API, AI agent API, authz API)
- A local OIDC provider (Keycloak) for issuing bearer tokens
- An OPA (Open Policy Agent) policy engine that evaluates Rego policies

This repository previously experimented with ***REMOVED***, OCI policy bundles, and an HTTPS registry proxy. That approach has been removed from the default developer workflow in favor of a simpler, more transparent OPA server-mode setup.

## Architecture at a glance

1. PDP: OPA server for ABAC. It evaluates relationship-based delegation and permissions via an authorization graph.

2. An AuthZ integration layer that acts as integration beteeen PEP and PDP and maintaing the graph for workflow ownership relations enriches requests with profile attributes.

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

- **`flowpilot-authz-api`** - Authorization façade for policy decisions
  - Validates access tokens via JWKS
  - Extracts identity context from JWT claims
  - Sanitizes all input payloads before processing
  - Calls OPA to evaluate Rego policies
  - Returns allow/deny decisions with optional reasons/obligations

- **`opa`** - Open Policy Agent in server mode
  - Evaluates attribute-based access control (ABAC) policies
  - Policies mounted from repository
  - Supports relationship-based delegation via authorization graph
  - Local policy editing with hot reload

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
        "auto_book_consent": true,
        "auto_book_max_cost_eur": 300,
        "auto_book_min_advance_hours": 24,
        "risk_profile": "medium"
      },
      "trip": {
        "total_cost_eur": 250,
        "departure_hours_from_now": 48,
        "risk_level": "low"
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
