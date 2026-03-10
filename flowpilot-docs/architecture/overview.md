# Architecture Overview

FlowPilot is a reference implementation of a modern authorization architecture for agentic workflows. It demonstrates how to build secure, privacy-preserving systems that combine relationship-based access control (ReBAC) with attribute-based policy decisions (ABAC).

## What FlowPilot Is

FlowPilot is:

- **A realistic, end-to-end authorization architecture** - Complete implementation from authentication to policy decisions
- **A working example of PEP ↔ PDP separation** - Using AuthZEN as the interface layer
- **A demonstration of ABAC + ReBAC** - Combined coherently in a single system
- **A foundation for agent-based systems** - With strong authorization guarantees

## What FlowPilot Is Not

FlowPilot is not:

- **A production-ready travel platform** - Travel booking is used as a concrete metaphor
- **An IAM product** - This is a reference architecture, not a commercial product
- **A UI-first demo** - Focus is on backend authorization patterns
- **An AI showcase** - AI is used to demonstrate agentic authorization, not as the primary focus

## Conceptual Pillars

### 1. AuthZEN as the PEP ↔ PDP Contract

FlowPilot treats AuthZEN as the interface, not the implementation.

**Policy Enforcement Points (PEPs) submit AuthZEN-like requests:**

- `subject` - Who or what is performing the action
- `action` - What operation is being attempted
- `resource` - What is being acted upon
- `context` - Additional context for the decision

**The Policy Decision Point (PDP) via flowpilot-authz-api:**

- Enriches the request with additional data
- Consults Policy Information Points (PIPs)
- Evaluates policies using OPA
- Returns structured authorization decisions

This separation keeps:

- Application services simple
- Authorization logic centralized
- The system evolvable without rewriting PEPs

### 2. ReBAC with Explicit Delegation Relationships

Delegation is modeled as a relationship graph, not as token bloat.

The `flowpilot-delegation-api` acts as a ReBAC PIP:

- **Delegations are explicit:** principal → delegate relationships
- **Delegations can be:**
  - Workflow-scoped or global
  - Time-bound
  - Revocable
- **Delegation chains are resolved transitively:** A → B → C → D
- **Chain length is bounded** to prevent privilege amplification

### 3. OPA as a Declarative Policy Engine (ABAC)

OPA is used strictly for attribute-based policy decisions:

- **Policies are written in Rego** - Declarative policy language
- **Policies are evaluated in OPA server mode** - No embedded decision logic
- **Policies are:**
  - Declarative
  - Testable
  - Explainable

**OPA answers questions such as:**

- Is the user allowed and properly delegated to auto-execute a workflow?
- Is consent for executing a workflow present?
- Is the risk of executing a workflow item below the configured threshold?

OPA itself uses AuthZEN-enriched input and does not need to manage identity, delegation graphs, or relationships.

### 4. Bearer Tokens with Personas, Not Identity Payloads

Access-tokens intentionally carry minimal personal information.

**Tokens contain:**

- `sub` - Stable, pseudonymous UUID
- Technical claims (issuer, expiry, crypto validation)

**Tokens do NOT contain:**

- Names
- Usernames
- Email addresses
- Personal preferences
- Consent details
- Any other PII

**Benefits:**

- Tokens remain small and stable
- Privacy is preserved by design
- Authorization decisions pull data only when needed
- The token provides just enough information to identify the principal

## Travel Booking as a Workflow Metaphor

The travel domain is used as a concrete narrative, not a limitation.

**Conceptual Mapping:**

- A **trip** is a **workflow**
- **Booking steps** are **workflow items**
- A **human booking** is a **principal**
- **Travelers** can delegate actions to travel agents and AI agents
- **Delegated parties** can further delegate to other parties
- **Auto-execution preferences** provide policy-driven constraints

**This maps cleanly to other domains:**

- Financial approvals
- Medical record handling
- Case management
- Enterprise automation
- Agent-based task execution

The travel example exists to make the architecture tangible, not to constrain it.

## Microservices Architecture

FlowPilot consists of multiple microservices, each with a specific responsibility:

### flowpilot-authz-api (Port 8002)

Authorization façade (PEP ↔ PDP integration):

- Validates AuthZEN requests
- Validates bearer tokens via JWKS
- Enforces delegation (ReBAC)
- Evaluates policies via OPA (ABAC)
- Returns allow/deny with reason codes

### flowpilot-persona-api (Port 8006)

Persona management:

- Manages persona definitions
- Normlaizes and defaults attributes
- No policy logic
- No PII
- Implements a record per persona referring to the identity using `sub`

### flowpilot-delegation-api (Port 8005)

Delegation relationship management:

- Manages delegation relationships
- Resolves delegation chains
- No policy logic
- No PII
- Implements a directional graph

### OPA server (Port 8181)

Declarative policy engine:

- Evaluates Rego policies
- Stateless decision engine
- Policies mounted from filesystem

### Firebase Authentication

Identity provider (fully managed):

- Issues Firebase ID tokens (JWTs)
- Personas stored in Firestore and custom claims
- Tokens validated locally by services using Firebase Admin SDK
- Automatic key rotation and management

### flowpilot-domain-services-api (Port 8003)

Workflow domain logic (PEP):

- Creates and manages workflows
- System of record for travel bookings
- Calls authz-api for authorization checks
- Auto-creates delegations

### flowpilot-ai-agent-api (Port 8004)

AI agent execution (PEP):

- Executes workflow items on behalf of users
- Demonstrates agentic authorization patterns
- Service-to-service authentication

## Privacy by Design

Privacy is not an afterthought; it is structural:

- No PII in tokens - Only pseudonymous identifiers
- No PII passed to AI agents - Only workflow context
- Delegation graph uses identifiers only - No personal information
- Profiles expose presence flags, not values - Consent without details
- Authorization decisions are reproducible - Without identity data

**The result:**

- Minimal data surface
- Lower breach impact
- Clearer compliance story

## Security by Architecture

Security is enforced at multiple layers:

- JWT validation - Signature, issuer, audience, exp, nbf, iat, typ
- JWKS-based local validation - No network calls per request
- Strict AuthZEN request validation - Schema enforcement
- Full payload sanitization - Input validation at every boundary
- Fail-closed behavior - Everywhere by default

The system assumes inputs are hostile by default.

## Why This Matters

Most "agentic" demos ignore authorization, privacy, and delegation until late.

FlowPilot does the opposite:

- Authorization is central - Not bolted on
- Delegation is explicit - Not implicit or token-based
- Policy is declarative - Not hard-coded
- Identity data is minimized - By design

This repository is meant to be read, reasoned about, and adapted, not just run.
