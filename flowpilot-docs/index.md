# FlowPilot

Nura has long advocated an authorization model that has proven to be both administration-friendly and effective.
Interestingly, it now also turns out to be a very natural fit for agentic AI.

When you treat AI agents as assistants or operators, authorization should follow the same principles we use for people.

The model is actually quite simple:

- Persona — actors operate in a defined role or capacity
- Delegation — authority can be granted to another actor
- Policy — actions are constrained by rules
- Consent — the authority to act must be granted explicitly

These principles apply equally to humans and AI agents.
At the authorization layer, both are simply actors participating in a trust chain.

> A human can delegate to another human or to an AI agent.
An AI agent can act within that delegated scope, or even delegate further where policy allows.

The only real difference is time scale.

A human delegation might last days or months.
An AI agent might receive authorization for less than a second — just long enough to execute a specific action.

Same principles.
Same governance model.
Just operating at machine speed.

To enable others to experiment with this authorization model, we offer FlowPilot as open source authorization platform for the age of agentic AI.

> With FlowPilot, AI agents don't assume authority; they obtain it explicitly and under tight control. At scale.

## What is FlowPilot?

FlowPilot is an Open Source library (see https://github.com/schuppnura/FlowPilot) for **Authorization-as-a-Service for AI agents** that need:

1.  Policy-based Authorization - Control what agents can do on behalf of users with declarative policies
2.  Persona-based Policies - Same user, different roles (traveler, agent, admin)
3.  Persona-based Delegation - Users delegate authority to agents or other users
4.  Privacy-First Design - No PII proliferation, minimal token claims
5.  Sovereign Deployment - Self-hosting and sovereignty as a key principle

It works as follows:

1.	You define baseline policy, personas, and delegation rules in FlowPilot
2.	Users refine these rules by delegating trust and setting scope, duration, and delegation constraints
3.	Your AI agents, services and apps submit authorization requests to FlowPilot over REST
4.	FlowPilot evaluates policies, personas, delegation chains, and contextual constraints at runtime
5.	Your AI agents, services and apps enforce the returned decision consistently and deterministically

## Goals

Agentic AI automates decisions, trigger actions, and operates with a level of autonomy that was previously reserved for humans. Yet most authorization models still assume that access is static, implicit, and largely context-free.

That assumption no longer holds.

When software can act, the relevant question is no longer “who has access?”, but who is acting, in which capacity, on whose behalf, and under which conditions. Without making those elements explicit, automation becomes difficult to trust, hard to audit, and risky to operate.

> Making authorization explainable, maintainable, testable and auditable

FlowPilot addresses this by treating authorization as a first-class concern. Actions are evaluated in context, combining identity, active persona, delegation scope, and policy constraints. If these elements do not align, the action does not proceed. There is no implicit privilege and no assumption that authority transfers automatically.

**Using AI for rule authoring**

FlowPilot follows a policy-as-code approach. Authorization logic is expressed declaratively and treated like any other critical system artifact: it is versionable, testable, reviewable, and deployable alongside application code or infrastructure configuration. This allows governance to evolve transparently, supports automated regression testing, and makes behavior reproducible across environments.

Because policies are explicit and machine-readable, FlowPilot is designed to work naturally with GenAI. GenAI can be used to draft initial policy rules, refine constraints, and translate high-level intent into concrete authorization logic. It can also assist in generating test cases and regression scenarios that validate expected behavior across personas, delegations, and edge conditions.

> While AI helps author the rules, FlowPilot enforces them continuously at runtime

While FlowPilot embraces GenAI for authoring and validation, all authorization decisions remain deterministic, policy-driven, and fully explainable. Decisions are enforced early and consistently, and every outcome can be expressed in human terms, supporting auditability, operational clarity, and trust.

**Personas as a natural model**

A central concept in security administration with FlowPilot is the persona. People and systems do not merely authenticate; they act in a defined capacity. A persona represents an explicit operating context and determines which actions are permitted at a given moment. The same individual may act in multiple personas, but privileges never blend across them. Switching persona immediately changes what the system will allow.

This model feels natural because it mirrors how people already think about responsibility. Acting as a traveler, an assistant, or a manager is intuitive. Assigning a persona, revoking one when someone changes role or leaves, or temporarily acting in a different capacity requires little explanation. Governance becomes a matter of managing clearly defined capacities rather than maintaining abstract permission sets.

FlowPilot treats AI agents in exactly the same way. An AI agent is simply another persona, subject to the same rules, scopes, constraints, and revocation mechanisms as any human assistant. Thinking of an AI agent as a digital secretary, travel agent, or operations assistant becomes straightforward: it can act only within the persona it is assigned, and only for the actions explicitly permitted.

> AI agents are governed like people, not special cases

By using personas as the core access-control primitive, FlowPilot avoids implicit privilege accumulation. Authority is always contextual, visible, and reversible. This makes access control easier to reason about, safer to operate, and better aligned with how real organizations function — whether actions are taken by people or by autonomous systems.

**Delegation to humans and AI**

In FlowPilot, delegation is an explicit expression of trust. Trust is never assumed or implicit; it is granted deliberately, scoped by action, and bound to clearly defined personas. Delegation always occurs persona to persona, reflecting the reality that people — and systems — act in specific capacities. AI agents are treated no differently: they are simply another participant in the trust chain, comparable to a human assistant or agent acting on someone’s behalf.

> Trust can be delegated to AI agents, while FlowPilot keeps the user in control

Trust in FlowPilot is contextual and conditional. A delegated persona may act only within the scope it has been granted, and only as long as the trust relationship remains valid. Delegation can extend transitively where appropriate, allowing trust to be shared across multiple actors, but access is retained only while every link in the chain is intact. The moment trust is withdrawn at any point, downstream authority stops immediately and predictably.

Crucially, the ability to extend trust further can itself be governed. Users can decide whether a delegate may sub-delegate, to which personas, and under which constraints. This allows trust to be composed without becoming uncontrolled. FlowPilot enforces these trust relationships continuously at runtime, ensuring that authority remains explicit, auditable, and aligned with the intent of the person who granted it.

## Non-Goals

FlowPilot is not intended to replace identity providers, authentication mechanisms, or directory services. It does not attempt to be a general workflow engine or a UI framework.

FlowPilot is also not an ontology-definition framework. Unlike initiatives such as ODRL and IDSA, it does not attempt to define or standardize domain-specific vocabularies, sector ontologies, or semantic models of consent, assets, or relationships. The creation and governance of such ontologies is intentionally left to sectors, standards bodies, and domain communities where it belongs.

> FlowPilot focuses on a complementary problem: turning declarative policy models into operational, real-time authorization decisions

FlowPilot is designed to consume externally defined policy representations and compile them into executable authorization rules that can be evaluated deterministically at runtime. Its scope is the enforcement layer: evaluating personas, delegation chains, scopes, constraints, and context efficiently and explainably when an action is requested.

In other words, FlowPilot does not seek to define what policies should mean across industries. Instead, FlowPilot focuses narrowly on one problem: making authorization decisions explicit, explainable, and enforceable in systems where actions matter and with a model that is easy to grasp and maintain. And doing this safely, consistently, efficiently and at scale in real systems.

## Policy Governance

FlowPilot demonstrates a **GitOps-based policy governance model** where:

1. **Policies are code** - OPA Rego policies live in version control
2. **Changes are auditable** - Every policy change has a git commit hash
3. **Deployments are validated** - Automated tests prevent broken policies from reaching production
4. **Rollbacks are instant** - Zero-downtime rollback to previous policy versions
5. **History is preserved** - Complete audit trail of all policy deployments

## The Travel Booking Metaphor

The concrete domain used in this git repo is **travel booking**, but this is deliberately a metaphor for a generic "workflow execution" problem involving users, agents, and delegated authority.

- Trips / Itineraries are workflows
- Booking steps are workflow items
- Travelers can delegate actions to travel agents and AI agents
- Auto-execution preferences drive policy-driven constraints

This maps cleanly to other domains:

- Medical record handling - Role-based access with patient consent and caring relationships
- Case management - Workflow delegation between case workers
- Financial approvals - Multi-level approval workflows, power of attorney, custody and mandates
- Enterprise automation - AI agents executing tasks within policy constraints
- Agent-based task execution** - Autonomous agents with user-defined limits

## Multiple Policies, One Platform

FlowPilot supports multiple authorization policies side-by-side:

- Travel Policy - Autonomous booking with cost, risk, and lead time constraints
- Nursing Policy - Healthcare workflows with certification and patient load limits
- Custom Policies - Define your own with typed attributes and validation rules

Policies are automatically selected based on resource type or explicit hints, with manifest-driven configuration for attributes, defaults, and validation.

## Why Not Just Use OAuth/OIDC?

OAuth/OIDC handles **authentication** (who are you?), but FlowPilot handles **authorization** (what can you do?):

- OAuth: "This is Alice"
- FlowPilot: "Alice (as a traveler) can delegate to Agent-X, who can auto-book if risk < 50 and consent = true"

FlowPilot integrates **with** your Identity Provider (Auth0, PingFederate, Firebase, Keycloak, etc.), not instead of it.

FlowPilot implements a three-tier token architecture that separates authentication from authorization:

1. **ID tokens** (from your IdP) - Contain user PII, used client-side for UI display only
2. **FlowPilot access tokens** - Pseudonymous tokens (UUID only), used for all backend API calls  
3. **Service tokens** - For efficient internal service-to-service communication

When your app authenticates a user with the Identity Provider of your choice you exchange the id-token for a pseudonymous FlowPilot access-token via the `/v1/token/exchange` endpoint. This access-token contains only the user's UUID (`sub`) with zero PII, preventing personal information from proliferating across your backend services.

Personas (business roles) are passed as request parameters selected by the user, not embedded in tokens. This allows users to switch personas without re-authentication and prevents token bloat. The combination of a persona `title` and the user's `sub` uniquely identifies the persona record of the user.

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
- Declarative policies in OPA/Rego
- Multi-policy architecture - Dynamic policy selection per request
- Manifest-driven configuration - Declarative policy metadata with typed attributes, no coding
- Policy routing - Automatic selection based on resource type or explicit hints
- Explainable authorization decisions with structured reason codes
- AuthZEN protocol compliance for standardized authorization requests

### Persona-Based Policies
- Persona is a natural concept for users, no access control lists, no pplication roles
- The assignment of personas is in the hands of users themselves with delegated governance processes, no need for super-admin
- Natural support for ABAC (Attribute-Based Access Control)
- Attribute validation based on declarations on type
- Attribute defaults based on declarations of sensible defaults
- User-defined constraints at persona level
- Time-bound and revocable persona assignments

### Persona-Based Delegation
- Declarative specification of delegation patterns, no coding
- Explicit delegation graph management
- Transitive delegation chain resolution
- Workflow-scoped and global delegations
- Time-bound and revocable delegations

### Defence-in-Depth Security
- JWKS-based JWT validation
- 4-layer input validation (Pydantic, path params, string sanitization, request size limits)
- Injection attack prevention
- Security headers on all responses
- Production-safe error handling
- Zero PII exposure to the back-end services (other than the authz-api and user-profile-api)

## Next Steps

**For Policy Governance, Auditors, Security/Privacy Officers:** Start with the [Policy Guide](development/policies.md) for authoring and reviewing policies.

**For Architects and Developers:** Start with the [Personas Guide](development/personas.md) to add FlowPilot to your application.

**To Understand the Model:** Read the [Architecture Overview](architecture/overview.md) and [Personas Guide](development/personas.md).

**For App Developers:** Start with the [Integration Guide](getting-started/integration.md) to add FlowPilot to your application.

**For Platform Operators:** See the [Self-Hosting Guide](deployment/gcp.md) if you want to run your own instance.
