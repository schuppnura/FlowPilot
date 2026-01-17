# Persona Management

This guide explains FlowPilot's *persona* model, including the data model, API operations, authorization rules, and technical implementation details.

## Overview

A *persona* represents a business role that a user assumes in a specific context. Personas are the core abstraction in FlowPilot’s authorization model and directly drive policy decisions for both **autonomous AI execution** and **delegated access**.

Rather than binding static permissions to user accounts, FlowPilot evaluates authorization against the **activated persona** provided with each request. Persona activation is not a platform-wide setting; it is scoped to the client app. The client app determines which persona is active; either automatically, based on the app's intended audience, or explicitly via a user-driven persona selection.

### Key concepts

- A single user may have **multiple personas** (for example, `traveler` and `travel-agent`)
- Each authorization request is evaluated against **exactly one activated persona**
- Personas have explicit **lifecycle state**:
  - temporal validity (`valid_from`, `valid_till`)
  - operational status (configurable and policy-relevant, for example `active`, `inactive`, `suspended`, `pending`)
- Personas also encapsulate **user's preferences**, such as:
  - consent
  - cost limits
  - risk tolerance
- Personas are **user-owned** and **independently configurable**

### Why Personas Matter

Introducing personas allows authorization policies to depend on **business intent**, not on technical account and application structure.

A FlowPilot persona models the business role, and in fact **the mandate a person holds at a given moment**. Each persona carries only the attributes relevant to that mandate and can be self-declared and managed independently from the underlying user account.

This enables several important architectural properties.

#### 1. Persona-level lifecycle management

User lifecycle management moves from the **account level** to the **persona level**:

- When someone leaves a role or function, only the corresponding persona needs to be deactivated
- The underlying user account can remain intact
- Users can onboard early and activate personas only when appropriate

This avoids account churn and reduces operational friction.

#### 2. Delegated security administration

Persona ownership enables delegated security administration:

- Users manage their own personas and persona attributes
- Security decisions are made closest to the source of truth
- No central administrator is required to continuously assign roles, groups, or permissions

This improves:
- timeliness
- accuracy
- appropriateness
- freshness of authorization data

#### 3. Segregation of duties by design

Segregation of duties becomes straightforward:

- Different duties are represented as different personas
- Policies can enforce that certain actions require distinct personas
- Conflicts are prevented structurally rather than procedurally

#### 4. User Managed Access

Personas provide a clean foundation for users managing access in a policy-constrained way:

- Users explicitly control which personas are active
- Delegation operates on personas, not raw identities
- Users are still subject to policies that remain declarative and auditable

## Architectural Impact

FlowPilot personas combine the strengths of **RBAC**, **ABAC** and **ReBAC**:

- RBAC-like clarity through named business roles
- ABAC-like flexibility through persona-specific attributes
- ReBAC-like delegation through persona-driven relationships

At the same time, persona-based administration significantly simplifies access management at scale:

- No global role explosion
- No central permission assignment bottleneck
- No need to expose identity or PII to policies

Instead, authorization becomes:
- explicit
- decentralized
- policy-driven
- scalable by design

In FlowPilot, personas place users at the center of their own authorization model, controlling not just *who they are*, but *how* and *when* they may act.

## Persona Data Model

### Core Attributes

| Field | Type | Description |
|-------|------|-------------|
| `persona_id` | String | Composite unique identifier: `{user_sub}_{title}` - enforces uniqueness at database level |
| `user_sub` | String | Owner's user ID (Firebase UID or Keycloak sub) |
| `title` | String | Persona title (e.g., "traveler", "travel-agent") |
| `status` | String | Current status: defined in policy manifest (e.g., "pending", "active", "inactive", "suspended", "expired") |
| `scope` | Array[String] | Denotes a community, organisation, family |
| `consent` | Boolean | Whether user allows autonomous execution of workflows for this persona |
| `valid_from` | ISO 8601 | Timestamp when persona becomes active |
| `valid_till` | ISO 8601 | Timestamp when persona expires |
| `created_at` | ISO 8601 | Creation timestamp |
| `updated_at` | ISO 8601 | Last modification timestamp |

**Important:** Each user can have only **one persona per title**. The `persona_id` is a composite key formed from `user_sub` and `title` (e.g., `PKbHpCqDnLcNywEo8pev8yQmoU43_traveler`). This enforces uniqueness at the database level and makes persona creation fully idempotent.

In addition to the persona lifecycle management attributes, each persona can also have a number of custom attributes specific to the business use case. These are configured in the manifest (see below).

### Persona Configuration

The persona titles, statuses and custom attributes are defined in the policy manifest as the **single source of truth** for both authorization policies and profil/persona management.

A system-defined persona `title` is `ai-agent`. This is used by the back-end and by agentic AI systems.

**Configuration Location:** `infra/opa/policies/travel/manifest.yaml`

**Key Benefits** of using the manifest:
- Customizable - Can easily be customized for a specific business use case
- Single source of truth - All persona configuration in one manifest file and used by both applications and the policy
- Centralized updates - Change persona configuration in one place
- Policy alignment - Persona titles and statuses automatically match OPA policy expectations, which is use case specific

**Important Note** on validation and defaulting responsibility
- persona-api: Validates that required attributes are PRESENT (not None) and sets a default value when not present. Does NOT validate ranges or policy-specific constraints
- authz-api: Assumes persona-api did its job and is not bypassed. So it passes attributes to OPA without validation or defaulting
- OPA policy: Performs ALL policy-specific validation (e.g., range checks) that is specific to the business use case

This separation ensures the system is extensible to other policies and business use cases without hardcoding policy logic in the API layer. This makes the platform truly a generic SaaS service

### Manifest Structure

The manifest's `persona_config` section defines `status`, `title` and a series of custom attributes. For the "travel" use case, FlowPilot defined the following `status`, `title` and autobook attributes. The latter enable and steer autonomous AI booking. Their values are validated and normalized by the persona-api and coerced to the type specified. Their values are also defaulted in case they are optional and a default value is provided. A default value of `null` means that the attribute will only be created when it explicitly has a value.

```yaml
persona_config:
  # Allowed persona status values (lifecycle states)
  persona_statuses:
    - pending      # Persona created but not yet activated
    - active       # Persona is active and can be used
    - inactive     # Persona temporarily disabled by user
    - suspended    # Persona suspended by admin
    - expired      # Persona validity period has ended
  
  # Persona titles with rich metadata
  persona_titles:
    - title: visitor
      description: "End user who may be interested in travel options or the itinerary"
      can-be-invited: true
      can-be-delegated-to: false
      allowed-actions: [read]

    - title: traveler
      description: "End users who book travel for themselves and for whom autobook preferences apply to their itineraries"
      can-be-invited: true
      can-be-delegated-to: false
      allowed-actions: [read, update]
    
    - title: business-traveler
      description: "End users who book travel for business purposes with specific autobook preferences"
      can-be-invited: true
      can-be-delegated-to: false
      allowed-actions: [read, update]
    
    - title: travel-agent
      description: "Travel agent who can execute workflows on behalf of travelers, if explicitly delegated"
      can-be-invited: false
      can-be-delegated-to: true
      allowed-actions: [read, update, execute, delete]
    
    - title: office-manager
      description: "Office manager with delegation and workflow execution capabilities"
      can-be-invited: false
      can-be-delegated-to: true
      allowed-actions: [read, update, execute]
    
    - title: booking-assistant
      description: "Booking assistant who can execute bookings on behalf of travelers"
      can-be-invited: false
      can-be-delegated-to: true
      allowed-actions: [read, execute]
    
    - title: user-admin
      description: "Supra-level administrator with full permissions to update personas of other users"
      can-be-invited: false
      can-be-delegated-to: true
      allowed-actions: [read, update, execute, delete]

  # Persona custom attributes
  attributes:
  - name: autobook_price
    type: integer
    source: persona
    default: 500
    required: false # when not given, the default value is set
    description: "Maximum trip cost for autonomous booking (EUR)"
  
  - name: autobook_leadtime
    type: integer
    source: persona
    default: 7
    required: false
    description: "Minimum days before departure for autonomous booking"
  
  - name: autobook_risklevel
    type: integer
    source: persona
    default: 3
    required: false
    description: "Maximum airline risk score for autonomous booking (1-5 scale)"
```

### Architecture Flow

```
manifest.yaml (SOURCE OF TRUTH)
     ↓
     ├─→ Python Services (via persona_config.py)
     │   ├─→ persona-api (validates titles & statuses)
     │   └─→ authz-api (loads attribute schema)
     │
     └─→ [generation script] → persona_config.json
                                      ↓
                                   OPA Policy Engine
```

The `persona_config.json` file is **auto-generated** from `manifest.yaml`:
- For local development: Run `make generate-opa-config`
- For Docker/Cloud Run: Auto-generated during build process
- **Never edit `persona_config.json` directly** - it will be overwritten

### Example Persona Document

```json
{
  "persona_id": "PKbHpCqDnLcNywEo8pev8yQmoU43_business-traveler",
  "user_sub": "PKbHpCqDnLcNywEo8pev8yQmoU43",
  "title": "business-traveler",
  "status": "active",
  "scope": ["nike"],
  "valid_from": "2026-01-11T17:00:00Z",
  "valid_till": "2026-12-31T23:59:59Z",
  "created_at": "2026-01-11T17:00:00Z",
  "updated_at": "2026-01-13T17:00:00Z",
  "consent": true,
  "autobook_price": 10000,
  "autobook_leadtime": 7,
  "autobook_risklevel": 5
}
```

Note the `persona_id` format: `{user_sub}_{title}`. This composite ID ensures that each user can have only one persona per title.

## Service Architecture

### Persona-API

Purpose: Persona lifecycle management (CRUD operations)

Endpoints:

- `POST /v1/personas` - Create persona (idempotent)
- `GET /v1/personas` - List user's personas
- `GET /v1/personas/{persona_id}` - Get specific persona
- `PUT /v1/personas/{persona_id}` - Update persona
- `DELETE /v1/personas/{persona_id}` - Delete persona
- `GET /v1/users/{user_sub}/personas` - List personas for any user (service accounts only)

Authorization:

- User endpoints: JWT `sub` must match persona owner
- Service endpoint: Requires service account token (Keycloak: `client_id=flowpilot-agent`, GCP: `gserviceaccount.com` in email)

Code Location: `flowpilot-services/persona-api/`

Validation Rules:

- `title` must be one of the allowed persona titles defined in `persona_config.persona_titles` in the policy manifest
- `status` must be one of the allowed statuses defined in `persona_config.persona_statuses` in the policy manifest
- `scope` must be a non-empty array of action strings
- `valid_from` & `valid_till` must be valid ISO 8601 timestamps
- Custom attributes (e.g., `autobook_price`, `autobook_leadtime`, `autobook_risklevel`) are optional and validated according to the `attributes` section of the policy manifest
- **Uniqueness:** Each user can have only one persona per title (enforced at database level via composite ID)

**Important Notes:**
- The service fails fast at startup if the policy manifest cannot be loaded, ensuring persona configuration is always consistent with authorization policies
- **Idempotency:** Creating a persona that already exists (same `user_sub` + `title`) returns the existing persona with HTTP 201. This makes provisioning scripts safe to run multiple times.


## Authorization Scenarios

### Scenario 1: Owner with Traveler Persona

Context:

- Carlo (traveler) creates a workflow
- Carlo executes his own workflow

Authorization Flow:

1. Domain-services-api receives request with Carlo's token
2. Authz-api extracts `sub=carlo-uuid` from JWT
3. Authz-api fetches Carlo's "traveler" persona from persona-api
4. OPA evaluates:
    - `authorized_principal`: ✓ (owner == principal)
    - `persona_valid`: ✓ (traveler == traveler)
    - `owner_persona_active`: ✓ (status == "active")
    - `owner_persona_valid_time`: ✓ (current time within range)
    - `has_consent`: ✓ (autobook_consent == true)
    - Other gates...
5. Decision: **Allow** (if all gates pass)

### Scenario 2: Delegated Travel Agent

Context:

- Carlo (traveler) delegates to Yannick (travel-agent)
- Yannick executes Carlo's workflow

Authorization Flow:

1. Domain-services-api receives request with Yannick's token
2. Authz-api extracts `sub=yannick-uuid` from JWT
3. Authz-api queries delegation-api: valid delegation exists
4. Authz-api fetches Carlo's "traveler" persona (resource owner)
5. OPA evaluates:
    - `authorized_principal`: ✓ (valid delegation with "execute" action)
    - `persona_valid`: ✓ (Yannick's persona "travel-agent" is an agent persona)
    - `owner_persona_active`: ✓ (Carlo's persona status == "active")
    - `owner_persona_valid_time`: ✓ (Carlo's persona is valid)
    - `has_consent`: ✓ (Carlo's autobook_consent == true)
    - Other gates...
6. Decision: **Allow** (if all gates pass)

### Scenario 3: Autonomous AI Agent

Context:

- AI agent attempts to book autonomously (no delegation)
- Carlo's workflow with autobook consent

Authorization Flow:

1. AI-agent-api calls domain-services-api with service token
2. AuthZEN request: `subject.persona = "ai-agent"`, `context.principal.id = carlo-uuid`
3. Authz-api fetches Carlo's "traveler" persona
4. OPA evaluates:
    - `authorized_principal`: ✓ (autobook_consent == true, no delegation required)
    - `persona_valid`: ✓ (context.principal.persona == owner.persona)
    - `owner_persona_active`: ✓ (status == "active")
    - `owner_persona_valid_time`: ✓ (within valid time range)
    - `has_consent`: ✓ (autobook_consent == true)
    - `within_cost_limit`: Check Carlo's autobook_price
    - `sufficient_advance`: Check Carlo's autobook_leadtime
    - `acceptable_risk`: Check Carlo's autobook_risklevel
5. Decision: **Allow** or **Deny** based on ABAC gates

### Scenario 4: Persona Mismatch

Context:

- Martine has two personas: "traveler" and "office-manager"
- Martine (office-manager) tries to execute her own workflow created with "traveler" persona

Authorization Flow:

1. Workflow was created with `owner.persona = "traveler"`
2. Martine's request has `subject.persona = "office-manager"`
3. OPA evaluates:
    - `authorized_principal`: ✓ (owner == principal)
    - `persona_valid`: ✗ (office-manager ≠ traveler, and office-manager is not allowed for owner execution)
4. Decision: **Deny** with reason_code `"auto_book.persona_mismatch"`

Resolution: Martine must switch to her "traveler" persona when executing her own workflows.

## Persona Lifecycle

### Creation

Personas are created via the persona-api POST /v1/personas endpoint.

**Request:**
```http
POST /v1/personas
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "title": "traveler",
  "scope": ["read", "execute"],
  "valid_from": "2024-01-01T00:00:00Z",
  "valid_till": "2026-12-31T23:59:59Z",
  "status": "active",
  "autobook_consent": true,
  "autobook_price": 5000,
  "autobook_leadtime": 7,
  "autobook_risklevel": 3
}
```

**Response (HTTP 201):**
```json
{
  "persona_id": "PKbHpCqDnLcNywEo8pev8yQmoU43_traveler",
  "user_sub": "PKbHpCqDnLcNywEo8pev8yQmoU43",
  "title": "traveler",
  "status": "active",
  "scope": ["read", "execute"],
  "valid_from": "2024-01-01T00:00:00Z",
  "valid_till": "2026-12-31T23:59:59Z",
  "created_at": "2026-01-13T17:00:00Z",
  "updated_at": "2026-01-13T17:00:00Z",
  "autobook_consent": true,
  "autobook_price": 5000,
  "autobook_leadtime": 7,
  "autobook_risklevel": 3
}
```

**Authorization:** The user must be authenticated. The persona is created for the authenticated user (extracted from JWT `sub` claim).

**Idempotency:** If a persona with the same `title` already exists for the authenticated user, the API returns the existing persona (HTTP 201). This allows provisioning scripts to be run multiple times safely. The `persona_id` is deterministic: `{user_sub}_{title}`.

### Fetch

Fetch a specific persona by ID:

```http
GET /v1/personas/{persona_id}
Authorization: Bearer <access-token>
```

**Authorization:** The user must be authenticated. 

### Update

Modify persona attributes:

```http
PUT /v1/personas/{persona_id}
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "autobook_price": 8000,
  "autobook_leadtime": 14,
  "status": "active"
}
```

**Authorization:** The persona must belong to the authenticated user.

### List

Users can list their own personas:

```http
GET /v1/personas?status=active
Authorization: Bearer <access-token>
```

**Service accounts** can list personas for any user:

```http
GET /v1/users/{user_sub}/personas?status=active
Authorization: Bearer <service-token>
```

This endpoint is used by authz-api to fetch persona data for authorization decisions.

All fields are optional (partial update). Only provided fields are updated.

**Authorization:** The persona must belong to the authenticated user.

### 5. Delete

Delete a persona:

```http
DELETE /v1/personas/{persona_id}
Authorization: Bearer <user-token>
```

**Authorization:** The persona must belong to the authenticated user.

## Technical Implementation

### Storage Backends

FlowPilot supports two storage backends for personas:

#### Firestore (GCP Production)

Used by Cloud Run deployment with Firebase Authentication:
- Serverless, scalable NoSQL database
- Collection: `personas`
- Document ID = `{user_sub}_{title}` (composite key for uniqueness)
- Requires composite indexes for efficient queries
- **Idempotency:** Creating a persona that already exists returns the existing document

Required Firestore Indexes:

```bash
# Index 1: user_sub + status + created_at (descending)
gcloud firestore indexes composite create \
  --collection-group=personas \
  --query-scope=COLLECTION \
  --field-config field-path=user_sub,order=ascending \
  --field-config field-path=status,order=ascending \
  --field-config field-path=created_at,order=descending

# Index 2: user_sub + created_at (descending)
gcloud firestore indexes composite create \
  --collection-group=personas \
  --query-scope=COLLECTION \
  --field-config field-path=user_sub,order=ascending \
  --field-config field-path=created_at,order=descending
```

#### SQLite (Local Development)

Used by local Docker Compose stack with Keycloak:
- Serverless
- In-memory or file-based SQLite database
- Schema defined in `personadb_sqlite.py`
- Simple, zero-configuration setup
- **Uniqueness Constraint:** `UNIQUE(user_sub, title)` ensures no duplicates
- **Idempotency:** Creating a persona that already exists returns the existing record

## Provisioning Personas

### GCP Production (Firebase)

Use the `seed_firebase_users.py` script:

```bash
FIREBASE_API_KEY=<your-api-key> \
python3 flowpilot-provisioning/seed_firebase_users.py \
  --profile-api-url=https://flowpilot-persona-api-737191827545.us-central1.run.app \
  --csv=flowpilot-provisioning/users_seed.csv
```

**Note:** The seed script is fully idempotent and can be run multiple times safely. It relies on the persona-api's idempotency guarantees rather than implementing its own duplicate checking. This makes the seed script a true regression test that validates API behavior.

### Local Development (Keycloak)

Use the `seed_keycloak_users.py` script:

```bash
python3 flowpilot-provisioning/seed_keycloak_users.py \
  --csv flowpilot-provisioning/users_seed.csv
```

### CSV Format

For test purposes, a provisioning script is provided that reads users and their personas from the `users_seed.csv` file:

```csv
username;password;email;firstname;lastname;persona;autobook_consent;autobook_price;autobook_leadtime;autobook_risklevel;persona_status;persona_valid_from;persona_valid_till
carlo;password;carlo@me.com;Carlo;Schupp;traveler,travel-agent;Yes;10000;7;5;active;2024-01-01T00:00:00Z;2026-12-31T23:59:59Z
```

**Note:** Users can have multiple personas by comma-separating them in the `persona` column. For simplicity reasons, the test provisioning creates each persona with the same autobook settings.

## Troubleshooting

### Persona Not Found

Symptom: Authorization denied with `auto_book.no_consent` despite user having consent

Causes:

1. Persona not created or provisioned
2. Persona fetch fails (403, 404, timeout)
3. Service account cannot access persona-api

Debug Steps:

1. Verify persona exists:
   ```bash
   curl -H "Authorization: Bearer <user-token>" \
     https://persona-api/v1/personas
   ```

2. Check authz-api logs for persona fetch errors:
   ```bash
   gcloud logging read "resource.labels.service_name=flowpilot-authz-api \
     AND (textPayload=~'persona' OR jsonPayload.error=~'persona')" \
     --limit=20
   ```

3. Verify service account can access persona-api:
   ```bash
   # Get service token (GCP)
   curl -H "Metadata-Flavor: Google" \
     "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=flowpilot-services"
   
   # Test access
   curl -H "Authorization: Bearer <service-token>" \
     https://persona-api/v1/users/<user-sub>/personas
   ```

### Persona Status Denied

Symptom: Authorization denied with `auto_book.persona_inactive` or `auto_book.persona_expired`

Causes:

1. Persona status is not "active"
2. Current time is outside valid_from/valid_till range

Resolution:

1. Update persona status:
   ```bash
   curl -X PUT https://persona-api/v1/personas/<persona-id> \
     -H "Authorization: Bearer <user-token>" \
     -H "Content-Type: application/json" \
     -d '{"status": "active"}'
   ```

2. Update temporal validity:
   ```bash
   curl -X PUT https://persona-api/v1/personas/<persona-id> \
     -H "Authorization: Bearer <user-token>" \
     -H "Content-Type: application/json" \
     -d '{
       "valid_from": "2024-01-01T00:00:00Z",
       "valid_till": "2027-12-31T23:59:59Z"
     }'
   ```

### Firestore Index Missing

Symptom: User-profile-api returns 500 error: "The query requires an index"

Resolution: Create the required composite indexes (see "Storage Backends" section above)

### Service Account Authorization Failure

Symptom: User-profile-api returns 403: "Forbidden: Service account required"

Causes:

1. Service token doesn't have `client_id=flowpilot-agent` (Keycloak)
2. Service token doesn't have `gserviceaccount.com` in email (GCP)

Resolution:

- Local: Use correct Keycloak service account credentials
- GCP: Ensure authz-api uses GCP identity tokens from metadata server

## Configuration Management

### Persona Configuration in Policy Manifest

Persona configuration is centrally managed in the policy manifest to ensure consistency between authorization policies and profile management.

**File:** `infra/opa/policies/travel/manifest.yaml`

### Adding New Persona Titles

To add a new persona title:

1. Update the policy manifest (`infra/opa/policies/travel/manifest.yaml`):
   ```yaml
   persona_config:
     persona_titles:
       - title: traveler
         description: "End user traveling"
         can-be-invited: true
         can-be-delegated-to: false
         allowed-actions: [read, update]
       
       - title: new-persona-title  # Add here
         description: "Description of new persona"
         can-be-invited: false
         can-be-delegated-to: true
         allowed-actions: [read, execute]
   ```

2. Update OPA policies if the persona requires special authorization logic

3. Regenerate OPA configuration (for local development):
   ```bash
   make generate-opa-config
   # This generates persona_config.json from manifest.yaml
   ```

4. Restart services to load new configuration:
   ```bash
   # Local
   docker compose restart flowpilot-persona-api opa
   
   # GCP (auto-generates during build)
   ./bin/deploy-all-services.sh
   ```

### Adding New Persona Statuses

To add a new persona status value:

1. Update the policy manifest:
   ```yaml
   persona_config:
     persona_statuses:
       - pending
       - active
       - inactive
       - suspended
       - expired
       - new-status  # Add here
   ```

2. Update OPA policies if the status requires special handling

3. Regenerate OPA configuration and restart services (same as above)

## Best Practices

1. **Use descriptive persona titles** - Match business roles, not technical identities
2. **Define all configuration in manifest** - Persona titles, statuses, and attributes are defined in `manifest.yaml` (single source of truth)
3. **Regenerate OPA config after manifest changes** - Run `make generate-opa-config` locally after editing manifest
4. **Never edit `persona_config.json` directly** - It's auto-generated from manifest.yaml
5. **Set reasonable autobook limits** - Start conservative, adjust based on user comfort
6. **Validate temporal ranges** - Ensure valid_till is far enough in the future
7. **Use descriptive status values** - The lifecycle should be clear: pending → active → suspended/inactive/expired
8. **Monitor persona status** - Implement workflows to expire/suspend personas when needed
9. **Limit personas per user** - Most users should have 1-2 personas (configurable via `MAX_PERSONAS_PER_USER`)
10. **Test delegation with personas** - Verify agent personas work correctly with delegations
11. **Use active personas for authorization** - Inactive/suspended personas should not be used in authorization
12. **Provision test data properly** - Use seed scripts to maintain consistency across environments
13. **Keep manifest in version control** - Track all changes to persona configuration
14. **Rely on API idempotency** - Don't implement duplicate checking in client code; the API enforces uniqueness at the database level
15. **Run seed scripts multiple times safely** - Seed scripts are idempotent and serve as regression tests for API behavior

## Related Documentation

- [Policy Development Guide](policies.md) - How OPA policies use persona data
- [Authorization Architecture](../architecture/authorization.md) - Overall authorization flow
- [API Reference: Persona API](../api/persona.md) - Full API specification
