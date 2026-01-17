# FlowPilot

**Authorization-as-a-Service for Agentic Workflows**

FlowPilot is a managed authorization platform that handles complex access control for applications with AI agents, delegated authority, and multi-persona workflows.

## What is FlowPilot?

FlowPilot provides **Authorization-as-a-Service for AI agents** that need:

- **Policy-based Authorization** - Control what agents can do on behalf of users with declarative policies
- **Persona-based Policies** - Same user, different roles (traveler, agent, admin)
- **Persona-based Delegation** - Users delegate authority to agents or other users
- **Privacy-First Design** - No PII proliferation, minimal token claims

### How It Works

1. Your app authenticates users with Firebase (or bring your own identity provider)
2. Your app makes REST API calls to FlowPilot for authorization decisions
3. FlowPilot evaluates policies, delegation chains, and user attributes
4. Your app enforces the decision (allow/deny with reason codes)

## The Travel Booking Metaphor

The concrete domain used is **travel booking**, but this is deliberately a metaphor for a generic "workflow execution" problem involving users, agents, and delegated authority.

- **Trips / Itineraries** are workflows
- **Booking steps** are workflow items
- **Travelers** can delegate actions to travel agents and AI agents
- **Auto-execution preferences** drive policy-driven constraints

This maps cleanly to other domains:

- **Financial approvals** - Multi-level approval workflows with delegation
- **Medical record handling** - Role-based access with patient consent
- **Case management** - Workflow delegation between case workers
- **Enterprise automation** - AI agents executing tasks within policy constraints
- **Agent-based task execution** - Autonomous agents with user-defined limits

### Multiple Policies, One Platform

FlowPilot supports multiple authorization policies side-by-side:

- **Travel Policy** - Autonomous booking with cost, risk, and lead time constraints
- **Nursing Policy** - Healthcare workflows with certification and patient load limits
- **Custom Policies** - Define your own with typed attributes and validation rules

Policies are automatically selected based on resource type or explicit hints, with manifest-driven configuration for attributes, defaults, and validation.

## For Developers Building

- **AI-powered applications** with autonomous agents
- **Workflow automation systems** with delegated execution
- **Multi-tenant SaaS** with complex permission models
- **Enterprise apps** requiring auditability and compliance
- **Healthcare/Finance apps** with strict access control requirements

### Why Not Just Use OAuth/OIDC?

OAuth/OIDC handles **authentication** (who are you?), but FlowPilot handles **authorization** (what can you do?):

- OAuth: "This is Alice"
- FlowPilot: "Alice (as a traveler) can delegate to Agent-X, who can auto-book if risk < 50 and consent = true"

FlowPilot integrates **with** your auth provider (Firebase, Auth0, Keycloak, etc.), not instead of it.

**Token Separation for Privacy**

FlowPilot implements a three-tier token architecture that separates authentication from authorization:

1. **ID tokens** (from your IdP) - Contain user PII, used client-side for UI display only
2. **FlowPilot access tokens** - Pseudonymous tokens (UUID only), used for all backend API calls  
3. **Service tokens** - For internal service-to-service communication

When your app authenticates a user with Firebase/Auth0/etc., you exchange the id-token for a pseudonymous FlowPilot access-token via the `/v1/token/exchange` endpoint. This access-token contains only the user's UUID (`sub`) with zero PII, preventing personal information from proliferating across your backend services.

Persona titles (business roles) are passed as request parameters selected by the user, not embedded in tokens. This allows users to switch personas without re-authentication and prevents token bloat. The combintaion of a persona title and the user's `sub` uniquely identifies the persona record of the user.

## Quick Links

<div class="grid cards" markdown>

-   :material-code-braces:{ .lg .middle } __Integrate with Your App__

    ---

    Add FlowPilot authorization to your web or mobile app

    [:octicons-arrow-right-24: Integration Guide](getting-started/integration.md)

-   :material-api:{ .lg .middle } __API Reference__

    ---

    Explore the REST APIs with interactive documentation

    [:octicons-arrow-right-24: API Docs](api/authz.md)

-   :material-account-key:{ .lg .middle } __Understanding Personas & Delegation__

    ---

    Learn how multi-persona auth and delegation work

    [:octicons-arrow-right-24: Concepts](development/personas.md)

-   :material-file-document-edit:{ .lg .middle } __Writing Policies__

    ---

    Create custom authorization policies for your use case

    [:octicons-arrow-right-24: Policy Guide](development/policies.md)

</div>

## Key Features

### Policy-Driven Authorization
- **Multi-policy architecture** - Dynamic policy selection per request
- **Manifest-driven configuration** - Declarative policy metadata with typed attributes
- **Automatic defaults** - Missing attributes filled with sensible policy-defined defaults
- **Attribute validation** - Required fields enforced with structured error messages
- **Policy routing** - Automatic selection based on resource type or explicit hints
- **Declarative Rego policies** in OPA with ABAC (Attribute-Based Access Control)
- **Consent and risk threshold evaluation** - User-defined constraints
- **Explainable authorization decisions** with structured reason codes
- **AuthZEN protocol** compliance for standardized authorization requests

### Relationship-Based Access Control
- Explicit delegation graph management
- Transitive delegation chain resolution
- Workflow-scoped and global delegations
- Time-bound and revocable delegations

### Defense-in-Depth Security
- JWKS-based JWT validation
- 4-layer input validation (Pydantic, path params, string sanitization, request size limits)
- Injection attack prevention
- Security headers on all responses
- Production-safe error handling
- Zero PII exposure to the back-end services (other than the authz-api and user-profile-api)

### Production-Ready Patterns
- Solid microservices architecture, adopting separation of concern
- Comprehensive testing suite
- OpenAPI specifications for all APIs
- Cloud Run deployment for GCP
- Docker Compose for local development

### Policy Governance

FlowPilot demonstrates a **GitOps-based policy governance model** where:

1. **Policies are code** - OPA Rego policies live in version control
2. **Changes are auditable** - Every policy change has a git commit hash
3. **Deployments are validated** - Automated tests prevent broken policies from reaching production
4. **Rollbacks are instant** - Zero-downtime rollback to previous policy versions
5. **History is preserved** - Complete audit trail of all policy deployments

## Technology Stack

- **Backend**: Python + FastAPI
- **Policy Engine**: Open Policy Agent (OPA) and ready for Topaz
- **Graph Database**: PostgreSQL (GCP) / SQLite (local) and ready for Topaz Directory
- **NoSQL Database**: Firestore (GCP) / SQLite (local)
- **Identity Provider**: Firebase (GCP) / Keycloak (local) and ready for any other OIDC IdP
- **Infrastructure**: Google Cloud Run / Docker Compose and ready for any containerized deployment
- **Client**: React (web app) / Swift (macOS desktop app) and ready for any other client tech

## Next Steps

**For Policy Governance, Auditors, Security/Privacy Officers:** Start with the [Policy Guide](development/policies.md) to understand how to develop and review policies with FlowPilot.

**For Architects, Auditors, Back-end Developers:** Start with the [Personas Guide](development/personas.md) to add FlowPilot to your application.

**For App Developers:** Start with the [Integration Guide](getting-started/integration.md) to add FlowPilot to your application.

**For Platform Operators:** See the [Self-Hosting Guide](deployment/gcp.md) if you want to run your own instance.

**To Understand the Model:** Read the [Architecture Overview](architecture/overview.md) and [Personas Guide](development/personas.md).
