# Microservices Architecture

FlowPilot implements a microservices architecture with clear separation of concerns. Each service has a specific responsibility and communicates via REST APIs defined using OpenAPI.

## Service Overview

| Service | Port | Type | Purpose |
|---------|------|------|----------|
| flowpilot-authz-api | 8002 | PDP | Authorization decisions |
| flowpilot-domain-services-api | 8003 | PEP | Workflow management |
| flowpilot-ai-agent-api | 8004 | PEP | AI agent execution |
| flowpilot-delegation-api | 8005 | PIP | Delegation graph |
| Firebase Authentication | - | IdP | Identity provider |
| OPA | 8181 | PDP | Policy engine |

## Communication Patterns

All services communicate through REST APIs:

- **Protected by TLS** - All inter-service communication uses TLS
- **Bearer token authentication** - JWT validation on all protected endpoints
- **Input sanitization** - All inputs validated before processing
- **Fail-closed** - Services deny by default

## Service Details

### 1. flowpilot-authz-api (Port 8002)

**Role:** Policy Decision Point (PDP) and Authorization Façade

**Responsibilities:**

- Accepts AuthZEN-compliant authorization requests
- Validates bearer tokens via JWKS
- Enforces delegation by calling delegation-api (ReBAC)
- Evaluates ABAC policies via OPA
- Returns structured authorization decisions with reason codes

**Key Endpoints:**

- `POST /v1/evaluate` - Evaluate authorization request
- `GET /health` - Health check

**Code Structure:**

```
authz-api/
├── main.py          # FastAPI app and routes
├── core.py          # Authorization logic
└── Dockerfile       # Container definition
```

**Key Files:**

- `main.py` - FastAPI application and route definitions
- `core.py` - Core authorization logic and OPA integration

**Environment Variables:**

```bash
OPA_URL=http://opa:8181
DELEGATION_API_BASE_URL=http://flowpilot-delegation-api:8000
KEYCLOAK_JWKS_URI=https://keycloak:8443/realms/flowpilot/protocol/openid-connect/certs
```

### 2. flowpilot-delegation-api (Port 8005)

**Role:** Policy Information Point (PIP) for ReBAC

**Responsibilities:**

- Manages delegation relationships (principal → delegate)
- Resolves delegation chains (transitive)
- Validates delegation scope and actions
- SQLite-backed persistence
- No policy logic - purely relationship management
- No PII - only pseudonymous identifiers

**Key Endpoints:**

- `POST /v1/delegations` - Create delegation
- `GET /v1/delegations` - List delegations
- `GET /v1/delegations/{id}` - Get delegation details
- `DELETE /v1/delegations/{id}` - Revoke delegation
- `POST /v1/delegations/validate` - Validate delegation chain
- `GET /health` - Health check

**Code Structure:**

```
delegation-api/
├── main.py          # FastAPI app and routes
├── core.py          # Delegation logic
└── Dockerfile       # Container definition
```

**Data Model:**

Delegations are stored as directional edges in a graph:

- `principal_id` - Who is delegating
- `delegate_id` - Who is being delegated to
- `workflow_id` - Optional workflow scope
- `scope` - Actions granted (e.g., `["read", "execute"]`)
- `created_at` - Timestamp
- `expires_at` - Optional expiry

**Delegation Chains:**

Transitive delegation is supported:

- A delegates to B
- B delegates to C
- C can act on behalf of A (if scope permits)
- Chain length is bounded to prevent privilege amplification

### 3. flowpilot-domain-services-api (Port 8003)

**Role:** Policy Enforcement Point (PEP) for Workflow Domain

**Responsibilities:**

- Creates and manages workflows (trips)
- Creates and manages workflow items (booking steps)
- System of record for travel booking workflows
- Calls authz-api for all authorization checks
- Auto-creates delegations when workflows are created

**Key Endpoints:**

- `POST /v1/workflows` - Create workflow
- `GET /v1/workflows` - List workflows
- `GET /v1/workflows/{id}` - Get workflow details
- `POST /v1/workflows/{id}/items` - Create workflow item
- `GET /v1/workflows/{id}/items` - List workflow items
- `GET /health` - Health check

**Code Structure:**

```
domain-services-api/
├── main.py          # FastAPI app and routes
├── core.py          # Domain logic
└── Dockerfile       # Container definition
```

**Authorization Pattern:**

Every operation calls authz-api:

```python
authz_request = {
    "subject": {"id": user_sub},
    "action": {"name": "create"},
    "resource": {
        "type": "workflow",
        "id": workflow_id
    },
    "context": {"principal": {"id": user_sub}}
}

response = requests.post(
    f"{AUTHZ_BASE_URL}/v1/evaluate",
    json=authz_request,
    headers={"Authorization": f"Bearer {token}"}
)

if not response.json()["decision"]:
    raise HTTPException(status_code=403, detail="Forbidden")
```

### 4. flowpilot-ai-agent-api (Port 8004)

**Role:** Policy Enforcement Point (PEP) for AI Agent Execution

**Responsibilities:**

- Executes workflow items on behalf of users
- Demonstrates agentic authorization patterns
- Service-to-service authentication using client credentials
- Calls authz-api before every execution

**Key Endpoints:**

- `POST /v1/execute` - Execute workflow item
- `GET /health` - Health check

**Code Structure:**

```
ai-agent-api/
├── main.py          # FastAPI app
└── Dockerfile       # Container definition
```

**Service Account:**

- Client ID: `flowpilot-agent`
- Uses client credentials flow
- Acts as `agent-runner` with persona `ai-agent`

### 5. OPA (Port 8181)

**Role:** Policy Decision Point (PDP) for ABAC

**Responsibilities:**

- Evaluates Rego policies
- Stateless decision engine
- Policies mounted from filesystem
- Hot-reload capability (restart recommended)

**Key Endpoints:**

- `POST /v1/data/auto_book/allow` - Evaluate auto-book policy
- `GET /health` - Health check
- `GET /v1/policies` - List loaded policies

**Policies:**

Located in `infra/opa/policies/`:

- `auto_book.rego` - Autonomous booking policy

**Policy Structure:**

```rego
package auto_book

default allow = false

allow {
    # Policy conditions here
}
```

**Updating Policies:**

```bash
# Edit policy
vim infra/opa/policies/auto_book.rego

# Restart OPA to reload
docker compose restart opa
```

### 6. Firebase Authentication

**Role:** Identity Provider (IdP) - Fully managed by Google

**Responsibilities:**

- Issues Firebase ID tokens (JWTs)
- Manages users and authentication
- Provides email/password authentication
- Supports multiple sign-in methods
- Automatic token refresh
- Built-in email verification and password reset

**Firebase Project:** `vision-course-476214`

**Authentication Methods:**

1. **Email/Password** - Primary method for users
   - Built-in validation
   - Password reset flows
   - Email verification

2. **Service Accounts** - For service-to-service auth
   - Google Cloud identity tokens
   - Automatic on Cloud Run

**Key Endpoints:**

- **Auth REST API:** `https://identitytoolkit.googleapis.com/v1/`
- **Token verification:** Firebase Admin SDK (no endpoint)

**User Data:**

- **Firebase Auth:** Core identity (`uid`, `email`, `displayName`)
- **Firestore:** User profiles and preferences (`users` collection)

## Shared Libraries

All services use shared libraries for common functionality:

**Location:** `flowpilot-services/shared-libraries/`

**Libraries:**

1. **security.py** - JWT validation, input sanitization, security headers
2. **api_logging.py** - Structured API logging
3. **profile.py** - User profile management
4. **utils.py** - General utilities

**IMPORTANT:** Shared libraries are copied into containers at build time. Changes require rebuilding all affected services:

```bash
docker compose up -d --build
```

## Service Communication Flow

### Workflow Creation Flow

1. **Client → domain-services-api:** `POST /v1/workflows`
2. **domain-services-api → authz-api:** Validate authorization
3. **authz-api validates JWT:** Using Firebase Admin SDK (local validation)
4. **authz-api → delegation-api:** Check delegation (if needed)
5. **authz-api → OPA:** Evaluate policy
6. **authz-api → domain-services-api:** Return decision
7. **domain-services-api → delegation-api:** Create delegation
8. **domain-services-api → Client:** Return workflow

### AI Agent Execution Flow

1. **ai-agent-api gets service token:** Google Cloud identity token (automatic on Cloud Run)
2. **ai-agent-api → domain-services-api:** Get workflow item details
3. **ai-agent-api → authz-api:** Request authorization
4. **authz-api → delegation-api:** Validate delegation chain
5. **authz-api → OPA:** Evaluate auto-book policy
6. **authz-api → ai-agent-api:** Return decision
7. **ai-agent-api:** Execute or deny based on decision

## API Documentation

OpenAPI specifications are available in `flowpilot-openapi/`:

- `authz.openapi.yaml` - Authorization API
- `delegation.openapi.yaml` - Delegation API
- `domain-services.openapi.yaml` - Workflow API
- `ai-agent.openapi.yaml` - AI Agent API
- `user-profile.openapi.yaml` - User Profile API

View these specs using Swagger Editor, Postman, or the embedded Swagger UI in the documentation site.

## Container Platform

All services are containerized using Docker:

- **Base images:** Python 3.11+ slim images
- **Platform:** Some services specify `linux/amd64` for compatibility
- **Networking:** Services communicate via Docker network
- **Volumes:** Persistent data stored in Docker volumes

## Development Workflow

### Rebuilding a Service

```bash
# Rebuild specific service
docker compose up -d --build flowpilot-authz-api

# View logs
docker compose logs -f flowpilot-authz-api
```

### Rebuilding All Services

```bash
# Rebuild everything
docker compose up -d --build
```

### Testing Service Health

```bash
# Test all health endpoints
for port in 8002 8003 8004 8005; do
  curl -s http://localhost:$port/health | jq
done
```

## Production Considerations

### Scalability

- All services are stateless (except delegation-api SQLite)
- Can be horizontally scaled behind load balancers
- OPA is fully stateless and horizontally scalable
- Consider moving delegation-api to PostgreSQL for production

### High Availability

- Deploy multiple instances of each service
- Use managed OIDC provider (or HA Keycloak cluster)
- Use managed OPA deployment
- Implement circuit breakers for inter-service calls

### Monitoring

- All services expose `/health` endpoints
- Structured logging via `api_logging.py`
- Consider adding:
  - Prometheus metrics endpoints
  - Distributed tracing (OpenTelemetry)
  - Centralized logging (ELK, Splunk)

### Security

- Use proper TLS certificates (not mkcert)
- Rotate secrets regularly
- Enable audit logging
- Set `INCLUDE_ERROR_DETAILS=0`
- Use managed secret storage (e.g., GCP Secret Manager)
