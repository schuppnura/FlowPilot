# FlowPilot Demo

Agentic workflows with an AuthZEN-style PEP/PDP boundary, ReBAC delegation (***REMOVED***), and progressive profiling.

## Overview

FlowPilot is a reference demo that validates a reusable authorization and delegation architecture for “agentic” workflow execution across domains (travel today; nursing later).

It demonstrates:
- A domain backend that owns workflow state (system of record) and enforces authorization as a PEP.
- A dedicated AuthZ integration service that acts as PDP façade + PIP (enrichment) + graph writer; maintains workflow ownership relations in ***REMOVED*** and enriches requests with profile attributes.
- A ReBAC-capable PDP (***REMOVED***) used to evaluate relationship-based delegation and permissions via an authorization graph.
- Hybrid ReBAC + ABAC authorization: autonomous booking is gated by attribute-based policy conditions (consent, cost, advance days, airline risk) after delegation is verified.
- An OSS IdP (Keycloak) with OIDC Authorization Code + PKCE for the desktop client.
- A workflow “agent-runner” that executes workflow items item-by-item to produce mixed allow/deny outcomes in a single run.
- Strict privacy discipline: no PII exposure to the LLM and no PII handling in the domain backend beyond `sub` (UUID).
- End-to-end authentication: bearer token validation across all services with service-to-service authentication.

Most components are domain-agnostic. Domain-specific behavior is isolated in the domain service and its templates.

---

## Target architecture (from FlowPilot.txt)

- Desktop client: collects intent, creates workflows, triggers dry runs, authenticates via OIDC + PKCE.
- Domain backend (`flowpilot-services-api`): system-of-record; PEP that builds minimal decision inputs and enforces dry_run semantics.
- Authorization integration service (`flowpilot-authz-api`): PIP + PDP façade + graph writer; enriches with profile attrs, maintains workflow-user relations in ***REMOVED***, and evaluates permissions.
- Agent runner (`flowpilot-ai-agent-api`): iterates workflow items against domain APIs and aggregates outcomes.
- Identity provider: Keycloak.
- PDP: ***REMOVED*** (Directory + Authorizer) for ReBAC tuples and checks.

Key evaluation questions:
- “Can this agent act on behalf of this principal?”
- “Is this workflow item executable given relations and resource facts?”

---

## Authorization Graph

FlowPilot uses **Relationship-Based Access Control (ReBAC)** via ***REMOVED*** to manage permissions through an authorization graph:

### Graph Structure
```
workflow_item --workflow--> workflow --owner--> user --delegate--> agent
```

### Permission Evaluation
When an agent attempts to execute a workflow item:
1. Agent-runner requests: "Can `agent-runner` execute `workflow_item_123`?"
2. ***REMOVED*** evaluates: `workflow_item.can_execute` permission
3. Permission resolves through the chain:
   - workflow_item links to workflow (via `workflow` relation)
   - workflow links to user (via `owner` relation)  
   - user links to agent (via `delegate` relation)
4. If the complete chain exists, permission is **allowed**

### Graph Maintenance
**User/Agent Relations** (provisioning time):
- Created by `provision_bootstrap.py` script
- Establishes which agents can act on behalf of which users

**Workflow Relations** (runtime):
- Created automatically when workflows are created via desktop app
- Services API calls AuthZ API's graph write endpoints:
  - `POST /v1/graph/workflows` - creates workflow + owner relation
  - `POST /v1/graph/workflow-items` - creates items + workflow relations

### Why This Architecture?
- **Decoupled authorization**: Domain services don't embed auth logic
- **Verifiable delegation**: No trusting client assertions; relations are explicit
- **Auditability**: Complete permission chain is traceable
- **Scalability**: Authorization logic is centralized and reusable across domains

## Policy Management Architecture

**For Security Auditors**: All authorization policy decisions are managed in ***REMOVED***. The AuthZ API does NOT make authorization decisions—it orchestrates checks and provides enrichment.

### Authorization Layers

1. **Anti-Spoofing (AuthZ API - PEP Guardrail)**
   - Validates request context (principal matches workflow owner)
   - Security guardrail, not policy decision
   - Prevents trivial spoofing attacks

2. **ReBAC - Relationship-Based Access Control (***REMOVED*** Directory)**
   - Policy Location: `infra/***REMOVED***/cfg/flowpilot-manifest.yaml`
   - Evaluates: Agent delegation via authorization graph
   - Example: Can `agent-runner` act on behalf of `user`?

3. **ABAC - Attribute-Based Access Control (***REMOVED*** OPA)**
   - Policy Location: `infra/***REMOVED***/cfg/policies/auto_book.rego`
   - Evaluates: Booking constraints (consent, cost, dates, risk)
   - Language: Rego (declarative policy as code)

4. **Progressive Profiling (AuthZ API - PIP Enrichment)**
   - Validates required identity fields are present
   - Returns advisory information for UX
   - Not an authorization decision—enrichment only

### Policy Change Process

- **ReBAC changes**: Update manifest YAML → reload via `***REMOVED*** directory set manifest`
- **ABAC changes**: Update Rego policy → automatic reload from volume mount
- **No code deployment required** for policy changes

### Audit Trail

- All policy decisions include `decision_id` for traceability
- ReBAC decisions logged by ***REMOVED*** Directory
- ABAC decisions logged by ***REMOVED*** Authorizer
- Anti-spoofing rejections logged by AuthZ API

See docs/AUTO_BOOK_POLICY.md for detailed ABAC policy documentation.

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

- `services/flowpilot-authz-api/` — AuthZ integration service: PDP façade, progressive profiling (PIP), and authorization graph writer (maintains workflow-user relations in ***REMOVED***)
- `services/flowpilot-ai-agent-api/` — Worklist execution loop; domain-agnostic
- `services/flowpilot-services-api/` — Travel demo domain backend; templates, endpoints, and PEP
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

1) Install ***REMOVED*** CLI (required for authorization)
```bash
# Install ***REMOVED*** CLI
brew tap aserto-dev/tap
brew install aserto-dev/tap/***REMOVED***
```

2) Setup secrets
```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your own secrets (or use defaults for development)
# For production, generate strong secrets:
# openssl rand -hex 32

# Generate Keycloak realm configuration with your secrets
./scripts/generate-realm-config.sh
```

3) Build & start
```bash
docker compose up -d --build
```

4) Load ***REMOVED*** manifest (required for authorization)
```bash
# Run this AFTER docker compose is up
***REMOVED*** directory set manifest infra/***REMOVED***/cfg/flowpilot-manifest.yaml \
  --plaintext --host localhost:9292
```

Note: This step requires the ***REMOVED*** CLI and must be run after services start.
It only needs to be done once (manifest persists in ***REMOVED*** database).

5) Provision users and delegate relations (required for authorization)
```bash
# Bootstrap users in Keycloak and create user->agent delegate relations in ***REMOVED***
cd flowpilot_provisioning_bootstrap
python3 provision_bootstrap.py --csv-path users_seed.csv --config provision_config.json
cd ..
```

This creates:
- Users in Keycloak (with credentials from CSV)
- User objects in ***REMOVED***
- Agent objects in ***REMOVED***
- Delegate relations: `user --delegate--> agent-runner`

Note: The CSV file uses semicolons as delimiters and supports multiple encodings.

6) Verify
```bash
docker ps
```
You should see containers for Keycloak (8080/8443), ***REMOVED*** (9080, 9292, 9393–9395, 9494), AuthZ API (8002), Services API (8003), and AI Agent API (8004).

7) Logs
```bash
# all services
docker compose logs
# one service (example)
docker compose logs flowpilot-services-api
```

8) Stop
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
