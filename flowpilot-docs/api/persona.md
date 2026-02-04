# Persona API

The Persona API provides persona lifecycle management for FlowPilot's authorization system.

## Overview

**Base URL (Local):** `http://localhost:8006`  
**Base URL (GCP):** `https://flowpilot-persona-api-737191827545.europe-west1.run.app`

### Responsibilities

- Persona lifecycle management (CRUD operations)
- Autobook preference management per persona
- Service-to-service persona lookup for authorization decisions

### Key Features

- **Multi-persona support** - Users can have multiple independent personas
- **Unique persona per title+circle** - Each user can only have one persona per (title, circle) combination
- **Circle-based grouping** - Personas belong to circles (e.g., "family", "acme-corp", "best-travels")
- **Persona-scoped autobook settings** - Each persona has its own consent and thresholds
- **Temporal validity** - Personas have status and valid time ranges
- **JWT authentication** - All endpoints require authentication (except `/health`)
- **Service account support** - AuthZ-API can fetch any user's personas
- **Storage backends** - SQLite (local) or Firestore (GCP)
- **Zero PII proliferation** - Only UUID and persona processed

## Authentication

All endpoints (except `/health`) require a Bearer token:

=== "Local (Keycloak)"

    ```bash
    Authorization: Bearer <keycloak-jwt-token>
    ```

=== "GCP (Firebase)"

    ```bash
    Authorization: Bearer <firebase-id-token>
    ```

## Endpoints

### Health Check

`GET /health` - No authentication required

---

## User Discovery Endpoints

These endpoints support user discovery for delegation candidate selection.

### List All Users

`GET /v1/users` - List all users from the identity provider

**Response (200 OK):**
```json
{
  "users": [
    {
      "id": "PKbHpCqDnLcNywEo8pev8yQmoU43",
      "username": "carlo",
      "email": "carlo@me.com"
    }
  ]
}
```

### List Users by Persona Title

`GET /v1/users/by-persona?title={title}` - List users with a specific persona title

**Query Parameters:**
- `title` (required): Persona title to filter by (e.g., "travel-agent", "traveler")

**Response (200 OK):**
```json
{
  "users": [
    {
      "sub": "bcadc299-f463-4f7d-bab5-2221761387f4",
      "email": null,
      "persona": "travel-agent"
    },
    {
      "sub": "ef456789-abcd-1234-5678-9abcdef01234",
      "email": null,
      "persona": "travel-agent"
    }
  ]
}
```

**Note:** Email field is always `null` as email addresses are not stored in the persona system.

**Use Case:** Finding delegation candidates (e.g., all travel agents)

---

## Persona Management Endpoints

These endpoints provide full lifecycle management of user personas with rich metadata and temporal validity.

### Create Persona

`POST /v1/personas` - Create a new persona for the authenticated user

**Request Body:**
```json
{
  "title": "traveler",
  "circle": "corsica",
  "valid_from": "2024-01-01T00:00:00Z",
  "valid_till": "2026-12-31T23:59:59Z",
  "status": "active",
  "consent": true,
  "autobook_price": 5000,
  "autobook_leadtime": 7,
  "autobook_risklevel": 3
}
```

**Required Fields:**
- `title` - Persona title (e.g., "traveler", "travel-agent")
- `circle` - Circle/community/business unit (e.g., "corsica", "best-travels")

**Note:** Each user can only have one persona per (title, circle) combination. Attempting to create a duplicate will result in a 400 error.

**Response (201 Created):**
```json
{
  "persona_id": "PKbHpCqDnLcNywEo8pev8yQmoU43_traveler_corsica",
  "user_sub": "PKbHpCqDnLcNywEo8pev8yQmoU43",
  "title": "traveler",
  "circle": "corsica",
  "valid_from": "2024-01-01T00:00:00Z",
  "valid_till": "2026-12-31T23:59:59Z",
  "status": "active",
  "created_at": "2026-01-13T17:00:00Z",
  "updated_at": "2026-01-13T17:00:00Z",
  "consent": true,
  "autobook_price": 5000,
  "autobook_leadtime": 7,
  "autobook_risklevel": 3
}
```

**Note:** The `persona_id` is a composite ID: `{user_sub}_{title}_{circle}`

### List Personas

`GET /v1/personas?status={status}` - List authenticated user's personas

**Query Parameters:**
- `status` (optional): Filter by status ("active", "inactive", "suspended", "expired")

**Response:**
```json
{
  "personas": [
    {
      "persona_id": "PKbHpCqDnLcNywEo8pev8yQmoU43_traveler_corsica",
      "user_sub": "PKbHpCqDnLcNywEo8pev8yQmoU43",
      "title": "traveler",
      "circle": "corsica",
      "valid_from": "2024-01-01T00:00:00Z",
      "valid_till": "2026-12-31T23:59:59Z",
      "status": "active",
      "created_at": "2026-01-13T17:00:00Z",
      "updated_at": "2026-01-13T17:00:00Z",
      "consent": true,
      "autobook_price": 5000,
      "autobook_leadtime": 7,
      "autobook_risklevel": 3
    }
  ]
}
```

### Get Persona

`GET /v1/personas/{persona_id}` - Get a specific persona

**Response:** Single persona object (same format as create response)

**Authorization:** Persona must belong to authenticated user

### Update Persona

`PUT /v1/personas/{persona_id}` - Update persona (partial update)

**Request Body:** All fields optional
```json
{
  "circle": "corfu",
  "autobook_price": 8000,
  "autobook_leadtime": 14,
  "status": "active"
}
```

**Response:** Updated persona object

**Authorization:** Persona must belong to authenticated user

### Delete Persona

`DELETE /v1/personas/{persona_id}` - Delete a persona

**Response:** 204 No Content

**Authorization:** Persona must belong to authenticated user

### List User's Personas (Service Accounts Only)

`GET /v1/users/{user_sub}/personas?status={status}` - List personas for any user

**Authorization:** Requires service account token
- Keycloak: `client_id=flowpilot-agent`
- GCP: Email contains `gserviceaccount.com`

**Response:** Same format as `GET /v1/personas`

**Use Case:** AuthZ-API uses this endpoint to fetch persona data for authorization decisions

## OpenAPI Specification

<swagger-ui src="../flowpilot-openapi/persona.openapi.yaml"/>

## Example Usage

### List Users by Persona Title

```bash
curl -X GET "http://localhost:8006/v1/users/by-persona?title=travel-agent" \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**
```json
{
  "users": [
    {
      "sub": "bcadc299-f463-4f7d-bab5-2221761387f4",
      "email": null,
      "persona": "travel-agent"
    }
  ]
}
```

### Create a Persona

```bash
TOKEN="your-firebase-or-keycloak-token"

curl -X POST http://localhost:8006/v1/personas \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "traveler",
    "circle": "corsica",
    "valid_from": "2024-01-01T00:00:00Z",
    "valid_till": "2026-12-31T23:59:59Z",
    "status": "active",
    "consent": true,
    "autobook_price": 5000,
    "autobook_leadtime": 7,
    "autobook_risklevel": 3
  }'
```

### List Your Personas

```bash
curl -X GET http://localhost:8006/v1/personas \
  -H "Authorization: Bearer $TOKEN"
```

### List Active Personas Only

```bash
curl -X GET "http://localhost:8006/v1/personas?status=active" \
  -H "Authorization: Bearer $TOKEN"
```

### Get Specific Persona

```bash
PERSONA_ID="b9678f30-f4b0-4033-82db-846357311165"

curl -X GET http://localhost:8006/v1/personas/$PERSONA_ID \
  -H "Authorization: Bearer $TOKEN"
```

### Update Autobook Preferences

```bash
curl -X PUT http://localhost:8006/v1/personas/$PERSONA_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "autobook_price": 8000,
    "autobook_leadtime": 14
  }'
```

### Deactivate a Persona

```bash
curl -X PUT http://localhost:8006/v1/personas/$PERSONA_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "inactive"
  }'
```

### Delete a Persona

```bash
curl -X DELETE http://localhost:8006/v1/personas/$PERSONA_ID \
  -H "Authorization: Bearer $TOKEN"
```

### Error Handling

| Status Code | Description |
|-------------|-------------|
| 200 | Success (GET, PUT) |
| 201 | Created (POST) |
| 204 | No Content (DELETE) |
| 400 | Validation error (invalid title, out of range values) |
| 401 | Unauthorized (invalid or missing token) |
| 403 | Forbidden (not owner of persona, or service account required) |
| 404 | Persona not found |
| 500 | Internal server error |

### Common Error Examples

**400 Bad Request - Invalid Title:**
```json
{
  "detail": "Invalid persona title 'invalid-persona'. Allowed: admin, booking-assistant, office-manager, travel-agent, traveler"
}
```

**400 Bad Request - Duplicate Title+Circle:**
```json
{
  "detail": "Persona with title 'traveler' and circle 'corsica' already exists for this user. Use PATCH/PUT (update) instead of POST (create) to modify it."
}
```

**400 Bad Request - Max Personas:**
```json
{
  "detail": "Maximum 5 personas per user. Delete an existing persona first."
}
```

**403 Forbidden (User endpoint):**
```json
{
  "detail": "Persona does not belong to authenticated user"
}
```

**403 Forbidden (Service endpoint):**
```json
{
  "detail": "Forbidden: Service account required"
}
```

**404 Not Found:**
```json
{
  "detail": "Persona not found"
}
```

## Storage Backends

### Local Development (SQLite)

- In-memory or file-based SQLite database
- Zero configuration
- Perfect for local testing

### Production (Firestore)

- Google Cloud Firestore (NoSQL)
- Serverless, auto-scaling
- Requires composite indexes (defined in `infra/firebase/firestore.indexes.json`)

**Deploy indexes:**
```bash
# Using gcloud CLI:
gcloud firestore indexes composite create \
  --collection-group=personas \
  --query-scope=COLLECTION \
  --field-config field-path=user_sub,order=ascending \
  --field-config field-path=status,order=ascending \
  --field-config field-path=created_at,order=descending

gcloud firestore indexes composite create \
  --collection-group=personas \
  --query-scope=COLLECTION \
  --field-config field-path=user_sub,order=ascending \
  --field-config field-path=created_at,order=descending

# Or using Firebase CLI:
firebase deploy --only firestore:indexes
```

## Related Documentation

- [Persona Guide](../development/personas.md) - Complete persona management guide
- [Policy Development Guide](../development/policies.md) - How OPA uses persona data
- [Authorization Architecture](../architecture/authorization.md) - Overall authorization flow
- [Delegation API](delegation.md) - Manage delegation relationships
