# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

FlowPilot is a reference implementation of an agentic workflow system with dedicated authorization services. It demonstrates defense-in-depth security, relationship-based access control (ReBAC), and attribute-based access control (ABAC) using Open Policy Agent (OPA).

**Key Components:**
- **Backend Microservices**: Four Python FastAPI services (authz, delegation, domain-services, ai-agent)
- **Policy Engine**: OPA server evaluating Rego policies
- **Authentication**: Keycloak OIDC provider with JWKS-based JWT validation
- **Swift Client**: macOS desktop application for traveler/agent personas
- **Shared Security Library**: Common utilities for JWT validation, input sanitization, and security headers

## Architecture

### Service Architecture
The system follows a microservices pattern with clear separation of concerns:

1. **flowpilot-authz-api** (port 8002): Authorization façade (PEP/PDP integration)
   - Validates AuthZEN-compliant authorization requests
   - Enforces delegation (ReBAC) by calling delegation-api
   - Evaluates ABAC policies via OPA
   - Returns structured authorization decisions with reason codes

2. **flowpilot-delegation-api** (port 8005): Delegation graph management
   - Maintains authorization graph (who delegates to whom)
   - Validates delegation chains (direct and transitive)
   - SQLite-backed persistence
   - Supports workflow-scoped delegations

3. **flowpilot-domain-services-api** (port 8003): Workflow domain logic
   - Creates and manages workflows and workflow items
   - System of record for travel booking workflows
   - Calls authz-api for authorization checks
   - Auto-creates delegations when workflows are created

4. **flowpilot-ai-agent-api** (port 8004): AI agent execution
   - Executes workflow items on behalf of users
   - Demonstrates agentic authorization patterns
   - Service-to-service authentication using client credentials

5. **OPA** (port 8181): Policy decision point
   - Evaluates Rego policies (infra/opa/policies/)
   - File-system mounted policies with hot reload
   - Primary policy: `auto_book.rego` for autonomous booking decisions

6. **Keycloak** (ports 8080/8443): OIDC identity provider
   - Realm: `flowpilot`
   - Desktop client: `flowpilot-desktop` (Authorization Code + PKCE)
   - Service account: `flowpilot-agent` (Client Credentials)
   - Auto-provisioned via setup scripts

### Security Architecture

**Defense-in-Depth Layers:**
1. JWKS-based JWT validation (zero network calls per request)
2. 4-layer input validation (Pydantic, path params, string sanitization, request size limits)
3. Injection attack prevention (control character rejection, optional signature scanning)
4. Security headers on all responses (6 protective headers)
5. Production-safe error handling (sanitized error messages)
6. Zero PII exposure to LLMs

**Authentication Flow:**
- Desktop client → OIDC Authorization Code + PKCE → Access token
- Services → Client Credentials → Service-to-service token
- All services validate tokens locally using JWKS (cached public keys)

**Authorization Flow:**
1. Request arrives at domain-services-api or ai-agent-api (PEP)
2. PEP calls authz-api with AuthZEN request
3. AuthZ-api validates JWT, extracts `sub` claim
4. If subject ≠ principal: authz-api queries delegation-api (ReBAC check)
5. Authz-api builds OPA input and queries OPA (ABAC check)
6. OPA evaluates Rego policy and returns decision
7. Authz-api returns structured response (allow/deny + reason codes)

### Code Organization

```
flowpilot-services/
├── authz-api/          # Authorization service
│   ├── main.py         # FastAPI app and routes
│   ├── core.py         # Authorization logic and OPA integration
│   └── Dockerfile
├── delegation-api/     # Delegation management
│   ├── main.py
│   ├── core.py
│   └── Dockerfile
├── domain-services-api/ # Workflow domain logic
│   ├── main.py
│   ├── core.py
│   └── Dockerfile
├── ai-agent-api/       # AI agent execution
│   ├── main.py
│   └── Dockerfile
└── shared-libraries/   # Common utilities (copied at build time)
    ├── security.py     # JWT validation, input sanitization
    ├── api_logging.py  # Structured API logging
    ├── profile.py      # User profile management
    └── utils.py        # General utilities

infra/
├── opa/policies/       # Rego policies
├── keycloak/           # Realm config and certs
└── certs/              # TLS certificates

scripts/                # Setup and provisioning scripts
bin/                    # Stack management scripts
data/                   # Trip templates
tests/                  # Integration tests
docs/                   # Architecture documentation
```

**Important:** Shared libraries in `flowpilot-services/shared-libraries/` are copied into each service's Docker container at build time. When editing these files, rebuild containers to see changes.

## Common Development Commands

### Stack Management

Start entire stack (recommended):
```bash
make up
# Or directly:
./bin/stack-up.sh
```

This script handles complete initialization:
- Builds and starts all containers
- Waits for Keycloak readiness
- Provisions users and agent relationships
- Configures OIDC clients

Stop stack:
```bash
make down
# Or:
./bin/stack-down.sh
```

View logs:
```bash
make logs
# Or:
./bin/stack-logs.sh
```

Check service status:
```bash
make status
# Or:
./bin/stack-status.sh
```

Complete reset (wipe volumes):
```bash
make reset
# Or:
./bin/stack-reset.sh
```

### Docker Compose Operations

View service logs (specific service):
```bash
docker compose logs -f flowpilot-authz-api
docker compose logs -f opa
docker compose logs -f keycloak
```

Rebuild specific service:
```bash
docker compose up -d --build flowpilot-authz-api
```

Rebuild all services:
```bash
docker compose up -d --build
```

Check service health:
```bash
docker compose ps
```

### Policy Development

Edit policies:
```bash
# Policies are in infra/opa/policies/
# Example: infra/opa/policies/auto_book.rego
```

Reload policies (restart OPA):
```bash
docker compose restart opa
```

Test policy directly with OPA:
```bash
docker run --rm --network flowpilot_default curlimages/curl:8.5.0 -sS \
  -H "Content-Type: application/json" \
  -d '{"input": {...}}' \
  http://opa:8181/v1/data/auto_book/allow
```

Run OPA tests (if tests exist):
```bash
docker compose exec -T opa opa test /policies -v
```

### Testing

Run integration tests:
```bash
python3 tests/user_based_testing.py
```

Test specific service health:
```bash
curl http://localhost:8002/health  # authz-api
curl http://localhost:8003/health  # domain-services-api
curl http://localhost:8004/health  # ai-agent-api
curl http://localhost:8005/health  # delegation-api
```

### Code Quality (No automated commands currently)

The repository uses:
- **Black** for code formatting
- **Ruff** for linting
- **mypy** for type checking
- **pylint** for additional linting (config in .pylintrc)

Note: There is no `Makefile` target or script for running these tools. Run them manually:
```bash
# Example (if tools are installed in your environment):
black flowpilot-services/
ruff check flowpilot-services/
mypy flowpilot-services/
pylint flowpilot-services/
```

### Swift Client (macOS App)

Build and run:
```bash
# From flowpilot-project/
open flowpilot-project.xcodeproj
# Build in Xcode (Cmd+B) and run (Cmd+R)
```

Reset and rebuild:
```bash
./flowpilot-project/reset-and-build.sh
```

## Key Development Patterns

### Service-to-Service Authentication

Services authenticate to each other using client credentials flow:

```python
# Pattern used throughout the codebase
import requests

def get_service_token():
    response = requests.post(
        os.environ["KEYCLOAK_TOKEN_URL"],
        data={
            "grant_type": "client_credentials",
            "client_id": os.environ["AGENT_CLIENT_ID"],
            "client_secret": os.environ["AGENT_CLIENT_SECRET"],
        },
        verify=False,  # Local dev only
    )
    return response.json()["access_token"]

# Use token in subsequent requests
headers = {"Authorization": f"Bearer {get_service_token()}"}
```

### JWT Validation Pattern

All services use the shared security library for JWT validation:

```python
from fastapi import Depends
import security

# In main.py
def get_token_claims(
    token_claims: dict = Depends(security.verify_token)
) -> dict:
    return token_claims

# In route handlers
@app.post("/some-endpoint")
def handler(token_claims: dict = Depends(get_token_claims)):
    user_sub = token_claims["sub"]
    # Use validated claims
```

### Input Validation Pattern

All request bodies go through sanitization:

```python
import security

# Sanitize entire JSON payload
try:
    sanitized = security.sanitize_request_json_payload(request_body)
except security.InputValidationError as e:
    raise HTTPException(status_code=400, detail=str(e))
```

### AuthZEN Request Pattern

Services call authz-api with AuthZEN-like structure:

```python
authz_request = {
    "subject": {"id": agent_sub},  # Who is performing action
    "action": {"name": "execute"},
    "resource": {
        "type": "workflow_item",
        "id": item_id,
        "workflow_id": workflow_id,
    },
    "context": {
        "principal": {  # On whose behalf
            "id": owner_sub,
            "claims": {...}  # User claims for ABAC
        }
    }
}

response = requests.post(
    f"{AUTHZ_BASE_URL}/v1/evaluate",
    json=authz_request,
    headers={"Authorization": f"Bearer {token}"}
)
decision = response.json()
```

### Delegation Creation Pattern

When creating workflows, automatically delegate to agent:

```python
# In domain-services-api after workflow creation
delegation_response = requests.post(
    f"{DELEGATION_API_BASE_URL}/v1/delegations",
    json={
        "principal_id": owner_sub,
        "delegate_id": "agent-runner",
        "workflow_id": workflow_id,
        "scope": ["execute"],
    },
    headers={"Authorization": f"Bearer {service_token}"}
)
```

## Environment Configuration

All services use environment variables defined in `docker-compose.yml`. Key variables:

**Security:**
- `KEYCLOAK_JWKS_URI`: JWKS endpoint for JWT validation
- `KEYCLOAK_ISSUER`: Expected JWT issuer
- `KEYCLOAK_AUDIENCE`: Expected JWT audience (optional)
- `ENABLE_PAYLOAD_SIGNATURE_SCAN`: Enable attack signature scanning (0/1)
- `MAX_REQUEST_SIZE_MB`: Request body size limit
- `INCLUDE_ERROR_DETAILS`: Show detailed errors (1 for dev, 0 for prod)

**Service Discovery:**
- `OPA_URL`: http://opa:8181 (authz-api → OPA)
- `DELEGATION_API_BASE_URL`: http://flowpilot-delegation-api:8000
- `AUTHZ_BASE_URL`: http://flowpilot-authz-api:8000
- `WORKFLOW_BASE_URL`: http://flowpilot-domain-services-api:8000

**Authentication:**
- `KEYCLOAK_TOKEN_URL`: Token endpoint for client credentials
- `AGENT_CLIENT_ID`: flowpilot-agent
- `AGENT_CLIENT_SECRET`: From .env file (never commit)

**Local .env file (required):**
```bash
KEYCLOAK_ADMIN_USERNAME=admin
KEYCLOAK_ADMIN_PASSWORD=<your-password>
KEYCLOAK_CLIENT_SECRET=<your-secret>
AGENT_CLIENT_SECRET=<your-secret>
```

## Troubleshooting

### Keycloak Not Ready
**Symptom:** Provisioning scripts fail with 401 errors

**Solution:** Wait longer for Keycloak to start (can take 60+ seconds)
```bash
docker compose logs -f keycloak
# Wait for "Listening on: https://0.0.0.0:8443"
```

### Agent Permission Denied
**Symptom:** "Allowed=0, Denied=3, Errors=0" in macOS app

**Causes:**
1. Delegations not created → Check delegation-api logs
2. OPA policy not loaded → Check OPA logs
3. Wrong agent identity → Verify `agent-runner` in delegation records

**Debug:**
```bash
# Check if delegation exists
curl http://localhost:8005/v1/delegations?delegate_id=agent-runner \
  -H "Authorization: Bearer <token>"

# Test OPA directly
curl -X POST http://localhost:8181/v1/data/auto_book/allow \
  -d '{"input": {...}}'
```

### Policy Changes Not Applied
**Symptom:** Authorization decisions don't reflect Rego changes

**Solution:** Restart OPA to reload policies
```bash
docker compose restart opa
```

### Container Build Issues
**Symptom:** Services fail to start after code changes

**Solution:** Rebuild with --no-cache
```bash
docker compose up -d --build --no-cache flowpilot-authz-api
```

### Service Cannot Reach Another Service
**Symptom:** Connection refused errors between services

**Causes:**
1. Using localhost instead of service name in container
2. Service not started or unhealthy

**Debug:**
```bash
# Check service is running
docker compose ps

# Check from inside container
docker compose exec flowpilot-authz-api curl http://opa:8181/health
```

## Important Notes

- **Shared Libraries:** Changes to `flowpilot-services/shared-libraries/` require container rebuilds (files are copied at build time)
- **Policy Hot Reload:** OPA watches `/policies` but container restart is more reliable
- **TLS in Dev:** Services use `verify=False` for TLS; never deploy this way
- **PII Handling:** Only `sub` (UUID) is processed; never log or expose other PII
- **Error Messages:** Set `INCLUDE_ERROR_DETAILS=0` in production to hide internal details
- **Client Secret:** Never commit `.env` file; it contains secrets
- **Port Conflicts:** Ensure ports 8080, 8181, 8443, 8002-8005 are available
- **macOS App:** Expects services on localhost; update URLs if running remotely

## Additional Resources

- **OpenAPI Specs:** `flowpilot-*.openapi.yaml` files in root
- **Architecture Docs:** `docs/` directory (DELEGATION_ARCHITECTURE.md, etc.)
- **Security Details:** README.md security section, SECURITY.md
- **Startup Guide:** STARTUP.md for manual startup procedures
