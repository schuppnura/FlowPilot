# FlowPilot Demo

Agentic workflows with an AuthZEN-style PEP/PDP boundary, ReBAC delegation (***REMOVED***), and progressive profiling.

## Overview

FlowPilot is a reference demo that validates a reusable authorization and delegation architecture for “agentic” workflow execution across domains (travel today; nursing later).

It demonstrates:
- A domain backend that owns workflow state (system of record) and enforces authorization as a PEP.
- A dedicated AuthZ service that acts as PDP façade + PIP (enrichment) + adapter to the underlying PDP engine.
- A ReBAC-capable PDP (***REMOVED***) used to evaluate relationship-based delegation and permissions.
- An OSS IdP (Keycloak) with OIDC Authorization Code + PKCE for the desktop client.
- A workflow “agent-runner” that executes workflow items item-by-item to produce mixed allow/deny outcomes in a single run.
- Strict privacy discipline: no PII exposure to the LLM and no PII handling in the domain backend beyond `sub` (UUID).
- End-to-end authentication: bearer token validation across all services with service-to-service authentication.

Most components are domain-agnostic. Domain-specific behavior is isolated in the domain service and its templates.

---

## Target architecture (from FlowPilot.txt)

- Desktop client: collects intent, creates workflows, triggers dry runs, authenticates via OIDC + PKCE.
- Domain backend (`flowpilot-services-api`): system-of-record; PEP that builds minimal decision inputs and enforces dry_run semantics.
- Authorization service (`flowpilot-authz-api`): PIP + PDP façade; enriches with profile attrs and calls ***REMOVED***.
- Agent runner (`flowpilot-ai-agent-api`): iterates workflow items against domain APIs and aggregates outcomes.
- Identity provider: Keycloak.
- PDP: ***REMOVED*** (Directory + Authorizer) for ReBAC tuples and checks.

Key evaluation questions:
- “Can this agent act on behalf of this principal?”
- “Is this workflow item executable given relations and resource facts?”

---

## Design rules

### Authorization & delegation
- ***REMOVED*** is the PDP; domain services never embed auth logic.
- Two-token pattern: Actor (agent identity) + Principal (end-user `sub` when acting on behalf).
- Do not trust asserted principals; spoofing/wrong owner must deny with explicit reasons.

### Privacy & LLM safety
- LLM receives no PII and no stable identifiers.
- Domain backend stores no PII beyond `sub`.
- Long-term memory lives outside the LLM (domain history; profile store via AuthZ enrichment).

### Progressive profiling
- Minimal registration to start.
- If `dry_run=false` and required fields are missing: deny with advice.
- If `dry_run=true`: may allow, but still return advice for what would block production.

---

## Repository layout

- `services/flowpilot-authz-api/` — AuthZ façade + enrichment + ***REMOVED*** adapter
- `services/flowpilot-ai-agent-api/` — Worklist execution loop; domain-agnostic
- `services/flowpilot-services-api/` — Travel demo domain backend; templates and endpoints
- `infra/keycloak/` — Realm import and TLS assets
- `infra/***REMOVED***/` — ***REMOVED*** config, manifest, and persistent directory DB
- `data/trip_templates/` — Domain workflow templates (travel today)

---

## Getting started

### Prerequisites (macOS)
- Install Docker Desktop
- Ensure Docker Desktop is running before you start

Check:
```bash
docker --version
docker compose version
```

### Quick start

1) Setup secrets
```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your own secrets (or use defaults for development)
# For production, generate strong secrets:
# openssl rand -hex 32

# Generate Keycloak realm configuration with your secrets
./scripts/generate-realm-config.sh
```

2) Build & start
```bash
docker compose up -d --build
```

3) Verify
```bash
docker ps
```
You should see containers for Keycloak (8080/8443), ***REMOVED*** (9080, 9292, 9393–9395, 9494), AuthZ API (8002), Services API (8003), and AI Agent API (8004).

4) Logs
```bash
# all services
docker compose logs
# one service (example)
docker compose logs flowpilot-services-api
```

5) Stop
```bash
docker compose down
```

### Security note
**IMPORTANT**: The default configuration is for **DEVELOPMENT ONLY**. Before production:

**Critical security issues in development mode:**
- ❌ Keycloak runs in development mode (reduced security)
- ❌ SSL verification disabled (vulnerable to MITM attacks)
- ❌ All service ports exposed to host (attack surface)
- ❌ Self-signed certificates (not trusted)
- ❌ Demo passwords included

**For production deployment:**
1. Use production compose: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`
2. Generate strong secrets: `openssl rand -hex 32`
3. Obtain valid SSL certificates (Let's Encrypt, etc.)
4. Enable SSL verification: `KEYCLOAK_VERIFY_SSL=true` in `.env`
5. Use reverse proxy with rate limiting
6. Review [docs/PRODUCTION_SECURITY.md](docs/PRODUCTION_SECURITY.md)

**Never commit:**
- `.env` file with real secrets
- `realm-flowpilot.json` with production credentials
- Private keys or certificates

### Service endpoints
- Keycloak: https://localhost:8443 (bootstrap admin: admin/admin)
- ***REMOVED*** Directory API: http://localhost:9393
- AuthZ API: http://localhost:8002
- Services API: http://localhost:8003
- AI Agent API: http://localhost:8004

### OpenAPI specs
- `flowpilot.openapi.yaml` - Services API (domain backend)
- `flowpilot-authz.openapi.yaml` - AuthZ API
- `flowpilot-ai_agent.openapi.yaml` - AI Agent Runner API

### Authentication
All services enforce bearer token authentication by default (`AUTH_ENABLED=true`):
- Desktop app → APIs: User authenticates via Keycloak OIDC, obtains access token, includes in all API requests
- Service-to-service: AI agent obtains service token via client credentials grant, includes in calls to services API
- Token validation: All services validate tokens via Keycloak introspection endpoint

### Input Sanitization
All services include comprehensive input validation and injection attack prevention:

**Automatic protections:**
- Request body size limit: 1MB (HTTP 413 if exceeded)
- String length limit: 10,000 characters per field
- Connection limits: 100 concurrent, 10k max requests per worker
- Keep-alive timeout: 5 seconds

**Injection attack detection:**
- **SQL injection**: UNION, DROP, INSERT, DELETE, UPDATE, OR/AND attacks
- **XSS (Cross-Site Scripting)**: Script tags, event handlers, javascript: protocol
- **Command injection**: Shell command chaining, substitution, redirection
- **Path traversal**: ../ directory access, URL encoding variants

**Configuration:**
```bash
# Customize limits in .env
MAX_REQUEST_SIZE_MB=1      # Request body size in MB
MAX_STRING_LENGTH=10000    # Max characters per string field
```

All input is validated before processing. Attacks are rejected with specific error messages.

See `docs/SECURITY_SETUP.md` for hardening recommendations and `SECURITY.md` for vulnerability reporting.

---

## Why this architecture
- Consistent authorization semantics across domain backends
- Explicit, verifiable delegation (no trusting client assertions)
- Safe agentic execution with per-item auditability
- Strong privacy discipline (keep PII and long-term memory out of the LLM and domain services)

## Assumptions
- Demo stack favors clarity over production hardening
- Policy vocabulary is a versioned contract and will evolve
- ***REMOVED*** policy/types will expand from minimal checks to richer policy over time
