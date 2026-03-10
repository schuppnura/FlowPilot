# Policy Testing

The regression suite is not just testing “access allowed vs denied”. It systematically demonstrates how FlowPilot’s authorization model behaves under real-world conditions: consent, personas, constraints, delegation chains, revocation, scope changes, and temporal validity.

At a high level, FlowPilot evaluates every action along four axes:

- Who is acting (principal)
- In which persona they are acting
- Under which delegation or invitation
- Against which policy constraints, both at workflow and item level

What follows is a human-readable explanation of what the tests prove.

## 1. Fail-Fast Authorization at the right level

FlowPilot distinguishes between workflow-level authorization and item-level authorization. Only when workflow-level checks pass does FlowPilot evaluate item-level constraints.

This is visible throughout the tests:

- Users without consent are denied immediately.
- Users with read-only delegation are denied immediately on execute.
- Persona mismatches are rejected before any item logic runs.

This fail-fast behavior is intentional: it prevents partial execution and avoids leaking information about items the principal should not even see.

## 2. Consent is a first-class Policy Primitive

Consent is not implied by ownership, delegation, or persona.

- A user with no autobook consent is denied even if everything else appears correct.
- Consent is evaluated before cost limits, airline risk, or other business rules.

This ensures that automation is never triggered implicitly or accidentally, even by trusted delegates.

## 3. Persona is not cosmetic — it is Enforced

Personas in FlowPilot are authoritative execution contexts, not labels.

The tests demonstrate that:

- A workflow is bound to a specific persona type.
- Executing with a different persona — even by the owner — is denied.
- Delegates must explicitly select a delegation persona, not an invitation persona.
- Switching persona mid-flow immediately changes what actions are permitted.

In practice, this means:

- “Who you are” is less important than “who you are acting as.”
- Owners cannot bypass constraints by switching personas.
- Delegates cannot escalate privileges by selecting the wrong persona.

## 4. Delegation is Explicit, Scoped, and Revocable

Delegation in FlowPilot is:

- Explicit (must be created)
- Scoped (read vs execute)
- Persona-aware
- Revocable, with immediate effect

The tests show that:

- Changing delegation scope requires revoke + recreate, avoiding ambiguous state.
- Read-only delegates can view but never execute.
- Revoking an intermediate delegation breaks the entire transitive chain.
- Restoring delegation restores access predictably.

This makes delegation auditable, deterministic, and safe to reason about.

## 5. Transitive Delegation works — and stops where it should

FlowPilot supports multi-hop delegation:

- Owner → Delegate → Sub-delegate → …

As long as:

- Each hop has valid scope
- Personas are compatible
- No delegation in the chain is revoked

Once a single link is revoked or downgraded:

- Access is immediately denied downstream
- There is no partial or cached privilege

This enables realistic enterprise scenarios (assistants, agencies, back-office chains) without losing control.

## 6. Item-Level Constraints are applied only when appropriate

Once workflow-level authorization succeeds, FlowPilot applies fine-grained item policies, such as:

- Cost ceilings
- Risk thresholds
- Time-based constraints (e.g. minimum advance notice)

The tests demonstrate mixed outcomes:

- Some items allowed
- Some denied with precise reason codes
- No errors or undefined behavior

This shows that FlowPilot can safely combine coarse authorization with fine-grained business rules in a single execution.

## 7. Time and Status matter

Personas and delegations are not static:

- Personas can be inactive, suspended, or not yet valid.
- Delegations can expire or be revoked.

The tests confirm that:

- Personas not yet valid cannot be used to create or execute workflows.
- Inactive personas immediately invalidate access.
- Temporal validity is enforced consistently at creation and execution time.

This is critical for compliance, onboarding/offboarding, and regulated environments.

## 8. CRUDX is Persona-Bound, not Role-Assumed

Allowed actions are defined per persona, not per user.

The tests show that:

- Visitor personas can read but not update or execute.
- Office-manager personas cannot execute autobook workflows.
- Even with delegation, actions outside a persona’s allowed-actions are denied.

This avoids “role explosion” and keeps authorization declarative and predictable.

## 9. Known limitations are explicit and test-Covered

One test intentionally documents a known limitation:
- Persona type is not yet enforced for read access under invitation.

This is valuable because:

- The behavior is explicit, not accidental
- The test suite already captures the expected future behavior
- Policy evolution can be regression-tested safely

## What this dmonstrates overall

Taken together, these tests demonstrate that FlowPilot provides:

- Deterministic authorization
- Strong separation between consent, delegation, persona, and policy
- Safe transitive delegation
- Immediate revocation effects
- Fail-fast behavior where it matters
- Fine-grained item control without leaking privilege

In short: authorization is no longer implicit, role-based, or context-blind — it is explicit, composable, and explainable.