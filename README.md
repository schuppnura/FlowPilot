# FlowPilot

FlowPilot is a reference implementation and architectural exercise exploring modern authorization for agentic workflows.

It demonstrates how to combine:
1. AuthZEN as a clean, technology-agnostic interface between PEPs and PDPs
2. OPA (Open Policy Agent) as a declarative policy language and decision engine
3. ReBAC (Relationship-Based Access Control) using explicit delegation relationships
4. Bearer access tokens with personas, not identity payloads, as the primary authorization input

A second, equally important focus is infrastructure-level privacy and security:
- no proliferation of PII
- full validation of access tokens and request payloads at every boundary
- deterministic, fail-closed authorization behavior

The concrete domain used to ground the exercise is travel booking, but this is deliberately a metaphor for a generic “workflow execution” problem involving users, agents, and delegated authority.

The reference implementation provides for Policy Enforcement Points (PEP) in the application server, a single Policy Decision Point (PDP) and multiple Policy Information Points (PIP) to supply information, about the user, the resource and the context given a certain action.

---

## What this project is (and is not)

FlowPilot is:
- a realistic, end-to-end authorization architecture
- a working example of PEP ↔ PDP separation via AuthZEN
- a demonstration of ABAC + ReBAC combined coherently
- a foundation for agent-based systems that need strong authorization guarantees

FlowPilot is not:
- a production-ready travel platform
- an IAM product
- a UI-first demo
- an AI showcase that would ignore security and privacy concerns

---

## Conceptual pillars

### 1. AuthZEN as the PEP ↔ PDP contract

FlowPilot treats AuthZEN as the interface, not the implementation.
- PEPs submit AuthZEN-like requests:
  - subject
  - action
  - resource
  - context
- The PDP (via flowpilot-authz-api) is free to:
  - enrich the request
  - consult PIPs
  - evaluate policies using any engine

This keeps:
- application services simple
- authorization logic centralized
- the system evolvable without rewriting PEPs

AuthZEN is used explicitly as a boundary, not as an all-encompassing framework.

---

### 2. OPA as a declarative policy engine (ABAC)

OPA is used strictly for attribute-based policy decisions:
- Policies are written in Rego
- Policies are evaluated in OPA server mode
- Policies are:
  - declarative
  - testable
  - explainable

OPA answers questions such as:
- Is the user allowed and properly delegated to auto-execute a workflow?
- Is consent for executing a workflow present?
- Is the risk of executiong a workflow item below the configured threshold?

OPA itself uses AuthZEN as input and does not need to manage identity, delegation graphs, or relationships.

---

### 3. ReBAC with explicit delegation relationships

Delegation is modeled as a relationship graph, not as token bloat.

The flowpilot-delegation-api acts as a ReBAC PIP:
- Delegations are explicit:
  - principal → delegate
- Delegations can be:
  - workflow-scoped or global
  - time-bound
  - revoked
- Delegation chains are resolved transitively:
  - A → B → C
- Chain length is bounded to prevent privilege amplification

Delegation is evaluated before ABAC:
- if delegation fails, authorization fails immediately
- OPA is never consulted

This separation keeps:
- policies simpler
- delegation auditable
- authorization explainable

---

### 4. Bearer tokens with personas, not identity payloads

Access tokens intentionally carry minimal personal information:
- sub (the stable, pseudonoymous UUID)
- persona (business role)
- technical claims required for validation about issuance, purpose, expiry and crypto

They do not carry:
- names
- emails
- personal preferences
- consent details
- any other PII of any kind

This ensures:
- tokens remain small and stable
- privacy is preserved by design
- authorization decisions pull data only when needed

The token provides just enough information to identify the principal for AuthZEN and delegation.

---

## Travel booking as a workflow metaphor

The travel domain is used as a concrete narrative, not a limitation.

Conceptually:
- a trip is a workflow
- booking steps are workflow items
- a human being doing a booking is a principal
- travellers can delegate actions to other travelers, to travel agents and to an AI agent
- delegated parties can further delegate to other parties
- auto-execution preferences are used for policy-driven constraints

This maps cleanly to other domains:
- financial approvals
- medical record handling
- case management
- enterprise automation
- agent-based task execution

The travel example exists to make the architecture tangible, not to constrain it.

---

## Architecture at a glance

### Core components
1. flowpilot-authz-api
   - Authorization façade (PEP ↔ PDP integration)
   - Validates AuthZEN requests
   - Validates bearer tokens via JWKS
   - Enforces delegation (ReBAC)
   - Evaluates policies via OPA (ABAC)
   - Returns allow/deny with reason codes
2. flowpilot-delegation-api
   - Manages delegation relationships
   - Resolves delegation chains
   - No policy logic
   - No PII
3. OPA
   - Declarative policy engine
   - Evaluates Rego policies
   - Stateless
4. Keycloak
   - OIDC provider
   - Issues bearer access tokens
   - Personas mapped to roles
   - Tokens validated locally by services
5. PEP services
   - Domain services
   - AI agent service
   - Always call authz-api before execution

---

## Privacy by design

Privacy is not an afterthought; it is structural.
- No PII in tokens
- No PII passed to AI agents
- Delegation graph uses identifiers only
- Profiles expose presence flags, not values
- Authorization decisions are reproducible without identity data

The result:
- minimal data surface
- lower breach impact
- clearer compliance story

---

## Security by architecture

Security is enforced at multiple layers:
- JWT validation (signature, issuer, audience, exp, nbf, iat, typ)
- JWKS-based local validation (no network calls per request)
- Strict AuthZEN request validation
- Delegation enforcement before policy evaluation
- Full payload sanitization
- Fail-closed behavior everywhere

The system assumes inputs are hostile by default.

---

## Why this matters

Most “agentic” demos ignore authorization, privacy, and delegation until late.

FlowPilot does the opposite:
- authorization is central
- delegation is explicit
- policy is declarative
- identity data is minimized

This repository is meant to be read, reasoned about, and adapted, not just run.

⸻

## Getting Started

### Prerequisites

**Required:**
- Docker Desktop 4.0+ with Docker Compose
- Python 3.11+ (for running regression tests locally)
- macOS (for Swift client)
- Available ports: 8002-8005, 8080, 8181, 8443

**Optional:**
- Black, Ruff, mypy, pylint (for code quality checks)

### Initial Setup

1. **Clone and navigate to repository:**
   ```bash
   git clone <repo-url>
   cd FlowPilot
   ```

2. **Create `.env` file** in the project root:
   ```bash
   KEYCLOAK_ADMIN_USERNAME=admin
   KEYCLOAK_ADMIN_PASSWORD=<your-secure-password>
   KEYCLOAK_CLIENT_SECRET=<your-client-secret>
   AGENT_CLIENT_SECRET=<your-agent-secret>
   ```
   
   **IMPORTANT:** Never commit `.env` to version control.

3. **Start the entire stack:**
   ```bash
   make up
   ```
   
   This single command:
   - Builds all Docker containers
   - Starts Keycloak, OPA, and all microservices
   - Waits for Keycloak to be ready (can take 60+ seconds)
   - Provisions users, clients, and delegations
   - Configures OIDC settings

4. **Verify services are running:**
   ```bash
   make status
   ```
   
   All services should show as "healthy" or "running".

5. **Check service health endpoints:**
   ```bash
   curl http://localhost:8002/health  # authz-api
   curl http://localhost:8003/health  # domain-services-api
   curl http://localhost:8004/health  # ai-agent-api
   curl http://localhost:8005/health  # delegation-api
   ```

### Quick Commands

```bash
make up      # Start entire stack
make down    # Stop all services
make logs    # View all service logs
make status  # Check service health
make reset   # Complete reset (wipes volumes)
make smoke   # Run smoke tests
```

### Service Endpoints

| Service | Port | Purpose |
|---------|------|----------|
| flowpilot-authz-api | 8002 | Authorization decisions (PDP) |
| flowpilot-domain-services-api | 8003 | Workflow management |
| flowpilot-ai-agent-api | 8004 | AI agent execution |
| flowpilot-delegation-api | 8005 | Delegation graph |
| Keycloak | 8080 (HTTP), 8443 (HTTPS) | OIDC provider |
| OPA | 8181 | Policy engine |

⸻

## Architecture Deep Dive

### Service Responsibilities

**flowpilot-authz-api** (port 8002)
- Acts as authorization façade (PEP/PDP integration point)
- Accepts AuthZEN-compliant requests
- Validates JWTs using JWKS (zero network calls per request)
- Enforces delegation by calling delegation-api (ReBAC layer)
- Evaluates ABAC policies via OPA
- Returns structured decisions with reason codes
- **Key file:** `flowpilot-services/authz-api/main.py`, `core.py`

**flowpilot-delegation-api** (port 8005)
- Maintains authorization graph (principal → delegate relationships)
- Validates delegation chains (direct and transitive)
- SQLite-backed persistence
- Supports workflow-scoped and global delegations
- No policy evaluation, purely relationship management
- **Key file:** `flowpilot-services/delegation-api/main.py`, `core.py`

**OPA** (port 8181)
- Evaluates Rego policies in `infra/opa/policies/`
- Primary policy: `auto_book.rego` for autonomous booking decisions
- File-system mounted policies with hot reload capability
- Stateless decision engine

**Keycloak** (ports 8080/8443)
- OIDC identity provider
- Realm: `flowpilot`
- Desktop client: `flowpilot-desktop` (Authorization Code + PKCE)
- Service account: `flowpilot-agent` (Client Credentials)
- Auto-provisioned via `scripts/setup_keycloak.sh`

**flowpilot-domain-services-api** (port 8003)
- System of record for workflows and workflow items (using 'travel' as use case)
- Creates travel booking workflows from templates
- Calls authz-api for all authorization checks
- Auto-creates delegations when workflows are created
- **Key file:** `flowpilot-services/domain-services-api/main.py`, `core.py`

**flowpilot-ai-agent-api** (port 8004)
- Executes workflow items on behalf of users (using 'travel' as use case)
- Demonstrates agentic authorization patterns
- Uses service-to-service authentication (client credentials)
- **Key file:** `flowpilot-services/ai-agent-api/main.py`

### Authorization Flow

1. Request arrives at domain-services-api or ai-agent-api (PEP)
2. PEP constructs AuthZEN request and calls authz-api
3. Authz-api validates JWT and extracts `sub` claim
4. If subject ≠ principal: authz-api queries delegation-api (ReBAC check)
5. If delegation valid: authz-api builds OPA input and queries OPA (ABAC check)
6. OPA evaluates Rego policy and returns decision
7. Authz-api returns structured response (allow/deny + reason codes)
8. PEP enforces decision and grants or refuses execution of a workflow item

### Authentication Flows

**Desktop Client → Services:**
- Authorization Code + PKCE flow
- User authenticates via Keycloak
- Access token with `sub` and `persona` claims

**Service → Service:**
- Client Credentials flow
- Service account: `flowpilot-agent`
- Example pattern used throughout:
  ```python
  response = requests.post(
      os.environ["KEYCLOAK_TOKEN_URL"],
      data={
          "grant_type": "client_credentials",
          "client_id": os.environ["AGENT_CLIENT_ID"],
          "client_secret": os.environ["AGENT_CLIENT_SECRET"],
      },
      verify=False  # Local dev only
  )
  token = response.json()["access_token"]
  ```

### Security Architecture

**Defense-in-Depth Layers:**
1. **JWT Validation:** JWKS-based, local validation (no network dependency)
2. **Input Validation:** 4-layer approach
   - Pydantic model validation
   - Path parameter validation
   - String sanitization (control character rejection)
   - Request size limits (default 1MB)
3. **Injection Prevention:** Optional signature scanning for attack patterns
4. **Security Headers:** 6 protective headers on all responses
5. **Error Handling:** Production-safe sanitized messages
6. **PII Protection:** Zero PII exposure to LLMs or logs

**Shared Security Library:**
- Located: `flowpilot-services/shared-libraries/security.py`
- Provides: JWT validation, input sanitization, security headers
- **IMPORTANT:** Changes require container rebuild (shared files are copied at build time)

⸻

## Development Workflow

### Project Structure

```
FlowPilot/
├── flowpilot-services/       # Microservices
│   ├── authz-api/
│   ├── delegation-api/
│   ├── domain-services-api/
│   ├── ai-agent-api/
│   └── shared-libraries/     # Common utilities (copied at build)
├── infra/
│   ├── opa/policies/         # Rego policies
│   ├── keycloak/             # Realm config and certs
│   └── certs/                # TLS certificates
├── flowpilot-project/        # Swift macOS client
├── flowpilot_openapi/        # OpenAPI specifications
├── flowpilot_testing/        # Integration tests
├── scripts/                  # Setup and provisioning
├── bin/                      # Stack management scripts
├── data/                     # Trip templates
├── docs/                     # Architecture documentation
└── docker-compose.yml        # Stack definition
```

### Making Code Changes

**1. Python Service Changes:**
```bash
# Edit code in flowpilot-services/<service>/
# Rebuild specific service
docker compose up -d --build flowpilot-authz-api

# View logs
docker compose logs -f flowpilot-authz-api
```

**2. Shared Library Changes:**
```bash
# Edit flowpilot-services/shared-libraries/*.py
# MUST rebuild ALL services that use them
docker compose up -d --build
```

**3. Policy Changes:**
```bash
# Edit infra/opa/policies/*.rego
# Restart OPA (has hot reload, but restart is more reliable)
docker compose restart opa

# Test policy directly
curl -X POST http://localhost:8181/v1/data/auto_book/allow \
  -H "Content-Type: application/json" \
  -d '{"input": {<your-test-input>}}'
```

**4. Environment Variable Changes:**
```bash
# Edit docker-compose.yml environment section
# Restart affected service
docker compose up -d flowpilot-authz-api
```

### Development Patterns

**JWT Validation Pattern:**
```python
from fastapi import Depends
import security

def get_token_claims(
    token_claims: dict = Depends(security.verify_token)
) -> dict:
    return token_claims

@app.post("/endpoint")
def handler(token_claims: dict = Depends(get_token_claims)):
    user_sub = token_claims["sub"]
    # Use validated claims
```

**AuthZEN Request Pattern:**
```python
authz_request = {
    "subject": {"id": agent_sub},
    "action": {"name": "execute"},
    "resource": {
        "type": "workflow_item",
        "id": item_id,
        "workflow_id": workflow_id,
    },
    "context": {
        "principal": {
            "id": owner_sub,
            "claims": {...}
        }
    }
}

response = requests.post(
    f"{AUTHZ_BASE_URL}/v1/evaluate",
    json=authz_request,
    headers={"Authorization": f"Bearer {token}"}
)
```

**Input Sanitization Pattern:**
```python
import security

try:
    sanitized = security.sanitize_request_json_payload(request_body)
except security.InputValidationError as e:
    raise HTTPException(status_code=400, detail=str(e))
```

### Testing

**Integration Tests:**
```bash
# Located in flowpilot_testing/
python3 flowpilot_testing/regression_test.py
```

**Service Health Checks:**
```bash
for port in 8002 8003 8004 8005; do
  curl -s http://localhost:$port/health | jq
done
```

**Manual Authorization Test:**
```bash
# Get service token
TOKEN=$(curl -s -X POST https://localhost:8443/realms/flowpilot/protocol/openid-connect/token \
  -d grant_type=client_credentials \
  -d client_id=flowpilot-agent \
  -d client_secret=<secret> \
  --insecure | jq -r .access_token)

# Test authorization endpoint
curl -X POST http://localhost:8002/v1/evaluate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"subject": {...}, "action": {...}, "resource": {...}}'
```

### Code Quality

The repository uses:
- **Black:** Code formatting
- **Ruff:** Fast linting
- **mypy:** Type checking
- **pylint:** Additional linting (config: `.pylintrc`)

No automated make targets exist. Run manually:
```bash
black flowpilot-services/
ruff check flowpilot-services/
mypy flowpilot-services/
pylint flowpilot-services/
```

### Swift Client (macOS App)

```bash
# Open in Xcode
open flowpilot-project/flowpilot-project.xcodeproj

# Or use reset script
./flowpilot-project/reset-and-build.sh
```

Client expects services on localhost. Update URLs if running remotely.

⸻

## Troubleshooting

### Keycloak Not Ready
**Symptom:** Provisioning fails with 401 errors during `make up`

**Solution:**
```bash
# Keycloak takes 60+ seconds to start
docker compose logs -f keycloak
# Wait for: "Listening on: https://0.0.0.0:8443"

# If setup failed, re-run manually
docker compose up keycloak-setup
```

### Agent Permission Denied
**Symptom:** "Allowed=0, Denied=3" in macOS app

**Causes:**
1. Delegations not created
2. OPA policy not loaded
3. Wrong agent identity

**Debug:**
```bash
# Check delegations exist
curl http://localhost:8005/v1/delegations?delegate_id=agent-runner \
  -H "Authorization: Bearer <token>"

# Test OPA directly
curl -X POST http://localhost:8181/v1/data/auto_book/allow \
  -d '{"input": {"principal": {...}}}'

# Check authz-api logs
docker compose logs flowpilot-authz-api | grep -i deny
```

### Policy Changes Not Applied
**Symptom:** Authorization decisions don't reflect Rego changes

**Solution:**
```bash
docker compose restart opa
# Verify policies loaded
docker compose exec opa ls -la /policies
```

### Service Cannot Reach Another Service
**Symptom:** Connection refused between services

**Causes:**
1. Using `localhost` instead of service name in container
2. Service not started or unhealthy

**Debug:**
```bash
# Check all services running
docker compose ps

# Test connectivity from inside container
docker compose exec flowpilot-authz-api curl http://opa:8181/health
```

### Container Build Fails
**Symptom:** Services fail to start after code changes

**Solution:**
```bash
# Force rebuild without cache
docker compose up -d --build --no-cache flowpilot-authz-api

# Or rebuild everything
make reset
make up
```

### Port Conflicts
**Symptom:** "port is already allocated" error

**Solution:**
```bash
# Find process using port
lsof -i :8002

# Kill process or stop conflicting service
kill -9 <PID>
```

### Shared Library Changes Not Reflected
**Symptom:** Code changes in `shared-libraries/` not working

**Cause:** Libraries are copied at build time, not mounted

**Solution:**
```bash
# MUST rebuild all services
docker compose up -d --build
```

⸻

## Environment Configuration

### Key Environment Variables

**Security (all services):**
```bash
KEYCLOAK_JWKS_URI=https://keycloak:8443/realms/flowpilot/protocol/openid-connect/certs
KEYCLOAK_ISSUER=https://localhost:8443/realms/flowpilot
KEYCLOAK_AUDIENCE=flowpilot-desktop
ENABLE_PAYLOAD_SIGNATURE_SCAN=0  # 1 to enable attack signature detection
MAX_REQUEST_SIZE_MB=1
INCLUDE_ERROR_DETAILS=1  # Set to 0 in production
```

**Service Discovery:**
```bash
OPA_URL=http://opa:8181
DELEGATION_API_BASE_URL=http://flowpilot-delegation-api:8000
AUTHZ_BASE_URL=http://flowpilot-authz-api:8000
WORKFLOW_BASE_URL=http://flowpilot-domain-services-api:8000
```

**Authentication:**
```bash
KEYCLOAK_TOKEN_URL=https://keycloak:8443/realms/flowpilot/protocol/openid-connect/token
AGENT_CLIENT_ID=flowpilot-agent
AGENT_CLIENT_SECRET=<from .env file>
```

**Local .env File (required, never commit):**
```bash
KEYCLOAK_ADMIN_USERNAME=admin
KEYCLOAK_ADMIN_PASSWORD=<your-password>
KEYCLOAK_CLIENT_SECRET=<your-secret>
AGENT_CLIENT_SECRET=<your-secret>
```

⸻

## API Documentation

OpenAPI specifications available in `flowpilot_openapi/`:
- `authz.openapi.yaml` - Authorization API
- `delegation.openapi.yaml` - Delegation API
- `domain-services.openapi.yaml` - Workflow API
- `ai-agent.openapi.yaml` - AI Agent API

View specs using Swagger Editor or similar tool.

⸻

## Important Notes

- **Shared Libraries:** Changes to `flowpilot-services/shared-libraries/` require container rebuilds
- **Policy Hot Reload:** OPA watches `/policies` but restart is more reliable
- **TLS in Dev:** Services use `verify=False` for TLS; **NEVER deploy this way**
- **PII Handling:** Only `sub` (UUID) is processed; never log or expose other PII
- **Error Messages:** Set `INCLUDE_ERROR_DETAILS=0` in production
- **Client Secret:** Never commit `.env` file
- **Port Requirements:** Ensure 8002-8005, 8080, 8181, 8443 are available
- **macOS App:** Expects services on localhost
- **Container Platform:** Some services specify `platform: linux/amd64` for compatibility

⸻

## Additional Resources

- **Architecture Documentation:** `docs/` directory
- **Security Details:** `SECURITY.md`
- **Startup Guide:** `STARTUP.md` (manual startup procedures)
- **Development Guidelines:** `DEVELOPMENT_GUIDELINES.md`
- **Testing Guide:** `flowpilot_testing/README.md`
- **Project Rules:** `WARP.md` (AI assistant guidance)

⸻

## Contributing

See `CONTRIBUTING.md` for contribution guidelines and `CODE_OF_CONDUCT.md` for community standards.
