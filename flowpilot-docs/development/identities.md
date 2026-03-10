# Persona vs Identity

This document explains FlowPilot’s approach to *user accounts* and, just as importantly, what FlowPilot deliberately **does not** model or manage.

FlowPilot is **identity-provider agnostic**. Authentication and account management are delegated entirely to an external Identity Provider (IdP). FlowPilot itself does **not** manage user accounts, credentials, or identity attributes. Instead, it focuses exclusively on **authorization**, using personas and persona-specific attributes under its own control.

## Design Principles

### Bring Your Own Identity Provider

User authentication is handled by an external IdP such as Firebase (production) or Keycloak (local development) and thus FlowPilot supports a Bring Your Own Identity Provider. The IdP is responsible for:

- User account creation and lifecycle
- Credential management
- Authentication flows (passwords, MFA, federation, etc.)
- Issuance of OIDC ID tokens

FlowPilot services do **not** depend on any IdP-managed user attributes:
- no username
- no email address
- no name
- no group or role claims

From FlowPilot’s perspective, the only relevant output of authentication is a **stable subject identifier (`sub`)**.


### No Identity & Authentication API in FlowPilot

FlowPilot intentionally does **not** provide an API to manage user profiles.

User profiles, in the traditional sense (identity attributes, contact information, organizational metadata), are considered **out of scope** and belong to the IdP domain.

As a result:

- Developers are free to model IdP accounts as they see fit
- FlowPilot does not read, store, or expose IdP attributes
- FlowPilot services never receive ID tokens after initial token exchange

This keeps FlowPilot cleanly separated from identity concerns and avoids tight coupling to any specific IdP.


### Authorization Is Persona-Driven

All authorization decisions in FlowPilot are based on **personas**, not on user profiles.

A persona represents:
- a business role
- a mandate
- or a responsibility assumed by a user in a given context

Personas and persona-specific attributes are:

- explicitly modeled in FlowPilot
- owned and managed by the user (or delegated administrators)
- evaluated by authorization policies (OPA / Rego)

This means that FlowPilot controls **all data that influences authorization**, independently from the IdP.


## Privacy by Design

Because FlowPilot does not consume IdP attributes:

- No Personally Identifiable Information (PII) enters FlowPilot systems
- Tokens used between backend services contain **only** a pseudonymous UUID (`sub`)
- Persona attributes are fetched on demand and only for authorization decisions
- Domain services, AI agents, and logs never see identity data

This architecture ensures:

- minimal data exposure
- reduced breach impact
- strong GDPR alignment
- clear separation between identity and authorization


## How User Identity Is Represented

From FlowPilot’s point of view, a “user” is represented by:

```json
{
  "sub": "89eb5366-bab3-46e4-b8e1-abc5f2ea4631"
}
```

This `sub` value:

- originates from the IdP
- is stable across sessions
- is opaque and non-meaningful
- is used solely as a key to:
  - fetch personas
  - resolve delegation relationships
  - evaluate authorization policies

No other identity attributes are required.


## Relationship to Personas

Personas are **linked to users by `sub`**, part of each persona record. The `sub` is a pseudononymous identifier and not PII.

Key distinctions:

- **User (IdP)**  
  - authenticated entity  
  - managed externally  
  - opaque to FlowPilot  

- **Persona (FlowPilot)**  
  - authorization construct  
  - business-role specific  
  - policy-relevant  
  - explicitly modeled and validated  

A single user (`sub`) may own multiple personas, each with its own lifecycle, attributes, and authorization semantics.


## Architectural Consequences

This design has several important consequences:

- FlowPilot remains portable across IdPs
- Authorization logic is fully under FlowPilot’s control
- PII cannot accidentally leak into policies, logs, or AI prompts
- Identity concerns do not contaminate domain or policy logic
- Personas can evolve independently of authentication mechanisms

In short: **FlowPilot treats identity as an external fact and authorization as an internal responsibility**.


## Related Documentation

- [Persona Guide](personas.md)
- [Authentication Architecture](../architecture/authentication.md)
- [Policy Development Guide](policies.md)
