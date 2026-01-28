# FlowPilot

**Policy-driven authorization for agentic and delegated AI systems**

FlowPilot is an **open-source authorization framework** designed for modern applications that rely on AI agents, delegated authority, and multi-persona workflows.

It addresses a foundational problem in agentic AI:  
**who may do what, on whose behalf, and under which constraints** — in a way that is auditable, privacy-preserving, and suitable for real-world systems.

FlowPilot is developed and maintained by **Nura**, as part of its broader mission to help enterprises, founders, and the developer community think seriously about authorization for agentic AI.

---

## Open Source, by Design

FlowPilot is released as **open source**.

Authorization for agentic AI is not a proprietary trick; it is shared infrastructure. As AI systems gain autonomy and act on behalf of users and organizations, governance, delegation, and accountability must be transparent and inspectable.

By open-sourcing FlowPilot, we enable:

- Enterprises to evaluate and adopt rigorous authorization models
- Founders to build agentic systems without reinventing governance
- The community to experiment, contribute, and evolve the model
- Researchers and practitioners to reason about authorization using real code

FlowPilot reflects the same architectural rigor required in regulated and enterprise environments. It is not a toy project or a demo.

---

## Architectural Overview

FlowPilot combines complementary standards and techniques, each used where it is strongest:

- **AuthZEN** for standardized authorization requests and responses (PEP ↔ PDP contract)
- **Rego (OPA)** for deterministic, real-time policy evaluation
- **ODRL** for semantic modeling of rights, duties, constraints, and consent
- **Typed manifests** to define personas and delegation models that Rego intentionally omits
- **GitOps-based governance** for policy lifecycle management

An internal compiler translates ODRL policies into Rego, allowing policies to be authored at a semantic level while remaining efficient at runtime.

---

## Personas and Delegation

FlowPilot is **persona-driven**, not identity-driven.

A persona represents the business role a subject assumes in a given context.  
Delegation relationships are explicit, directional, time-bound, and auditable — between people and between people and AI agents.

This makes FlowPilot suitable for:

- Agentic execution under user-defined constraints
- Regulated workflows with accountability requirements
- Multi-party systems without role explosion

---

## Security and Privacy

Security is designed in, not added later:

- Strict input and output validation at all boundaries
- Fail-closed authorization behavior
- Pseudonymous authorization tokens optimized for performance
- No PII propagation to AI agents or downstream services
- Integration with existing IdPs (Keycloak, Auth0, Firebase, etc.)

FlowPilot does **not** replace your identity provider.  
Authentication and identity lifecycle remain with your existing systems.

---

## Governance Model

Authorization policies are treated as first-class infrastructure:

- Policies, manifests, and mappings are version-controlled
- Changes are reviewed, tested, and deployed via GitOps workflows
- Dry-runs and staged deployments are supported
- Rollbacks are instant and zero-downtime
- Full audit trails are preserved for compliance and forensics

---

## Repository Scope

This repository contains:

- Reference implementations for PEP integrations
- Example services and workflows
- Policy, persona, and delegation examples
- Documentation explaining the model and trade-offs

It is intended to be read, adapted, and extended.

---

## Commercial Services

While FlowPilot itself is open source, **Nura offers professional services** around:

- Architecture and policy design
- Enterprise integration
- Governance setup
- Security and compliance reviews

These services are optional and not required to use FlowPilot.

---

## Repository Structure

```
flowpilot/
├── flowpilot-services/        # Backend microservices (Python/FastAPI)
│   ├── authz-api/             # Authorization service (PDP + PEP façade)
│   ├── delegation-api/        # Delegation graph management
│   ├── persona-api/           # Persona lifecycle and attributes
│   ├── domain-services-api/   # Workflow domain logic (PEP integration example)
│   ├── ai-agent-api/          # AI agent execution service (PEP integration example)
│   └── shared-libraries/      # Common security, validation, and utility functions
│
├── flowpilot-web/             # React web application (TypeScript)
│   ├── src/components/        # UI components
│   ├── src/services/          # API clients and auth logic
│   └── src/state/             # Application state management
│
├── flowpilot-project/         # Swift macOS desktop client
│   └── Flowpilot-app/         # macOS app with OIDC + PKCE flow
│
├── infra/                     # Infrastructure as code
│   ├── opa/policies/          # Rego policies by domain (travel, nursing, etc.)
│   ├── database/              # Database schemas (PostgreSQL/SQLite)
│   ├── keycloak/              # Keycloak realm configuration
│   └── firebase/              # Firebase configuration
│
├── flowpilot-openapi/         # OpenAPI 3.0 specifications for all services
│
├── data/                      # Sample workflow templates (trip, nursing)
│
├── docker-compose.yml         # Local development stack
├── Makefile                   # Development commands
└── cloudbuild-*.yaml          # GCP Cloud Build configurations
```

---

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local testing)
- Node.js 18+ (for web app development)
- Xcode 14+ (for macOS client development)

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/schuppnura/FlowPilot.git
   cd FlowPilot
   ```

2. **Create environment file**
   ```bash
   cp .env.example .env
   # Edit .env and set required secrets
   ```

3. **Start the stack**
   ```bash
   make up
   ```
   This will:
   - Start Keycloak (OIDC provider)
   - Start OPA (policy decision point)
   - Build and start all microservices
   - Auto-provision test users and clients

4. **Verify services**
   ```bash
   make status
   ```

5. **View logs**
   ```bash
   make logs
   ```

### Service Endpoints (Local)

- **Keycloak**: https://localhost:8443
- **OPA**: http://localhost:8181
- **AuthZ API**: http://localhost:8002
- **Domain Services API**: http://localhost:8003
- **AI Agent API**: http://localhost:8004
- **Delegation API**: http://localhost:8005
- **Persona API**: http://localhost:8006

### Development Commands

```bash
make up          # Start all services
make down        # Stop all services
make logs        # View service logs
make status      # Check service health
make reset       # Wipe volumes and reset
make smoke       # Run smoke tests
```

---

## Key Concepts

### Services Architecture

**Authorization Service (authz-api)**  
Central authorization decision point implementing AuthZEN protocol. Evaluates delegation chains via delegation-api and policy decisions via OPA.

**Delegation API (delegation-api)**  
Manages authorization graph (ReBAC) with support for direct and transitive delegation. Persists to PostgreSQL (production) or SQLite (dev).

**Persona API (persona-api)**  
Manages persona lifecycle, attributes, and temporal constraints. Supports Firestore (production) or SQLite (dev).

**Domain Services API (domain-services-api)**  
Reference PEP integration showing how to protect domain logic with authorization checks.

**AI Agent API (ai-agent-api)**  
Reference implementation demonstrating agentic execution patterns with proper authorization.

### Policy Development

Policies are written in Rego and organized by domain:

```bash
infra/opa/policies/
├── travel/
│   ├── manifest.yaml          # Persona definitions and metadata
│   ├── persona_config.json    # Generated OPA input structure
│   └── policy.rego            # Authorization rules
└── nursing/
    ├── manifest.yaml
    ├── persona_config.json
    └── policy.rego
```

OPA hot-reloads policies automatically via `--watch` flag.

### Client Integration

Both web and desktop clients demonstrate:
- OIDC authentication (Authorization Code + PKCE)
- Token exchange for pseudonymous access tokens
- Authorization-aware UI (showing/hiding based on permissions)
- Delegation management
- Persona switching

---

## Documentation

Detailed documentation available at **https://docs.nura.pro**

**Topics covered:**
- Architecture deep-dive
- AuthZEN integration patterns
- Policy authoring guide
- Delegation models
- Persona design
- Security best practices
- Deployment guide (GCP Cloud Run)

**Live Demo:** https://travel.nura.pro

---

## Contributing

We welcome thoughtful contributions.  
See `CONTRIBUTING.md` for details.

---

## License

Apache License 2.0 © Nura and contributors
