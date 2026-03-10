# AuthZ API

The AuthZ API serves as the authorization façade for FlowPilot, implementing the Policy Decision Point (PDP) pattern with AuthZEN-compliant request structure.

## Overview

**Base URL (Local):** `http://localhost:8002`  
**Base URL (GCP):** `https://flowpilot-authz-api-737191827545.us-central1.run.app`

### Responsibilities

- Policy evaluation using OPA Rego policies (PDP)
- Authorization graph validation via delegation-api
- JWT validation and claim extraction
- Structured authorization decisions with reason codes

### Key Features

- AuthZEN-compliant request/response structure
- Stateless operation (no in-memory storage)
- Bearer token authentication on all endpoints (except `/health`)
- Integration with OPA for ABAC decisions
- Integration with delegation-api for ReBAC checks

## Authentication

The AuthZ API accepts different token types depending on the endpoint:

### Token Types

- **Firebase ID tokens**: Only for `/v1/token/exchange` endpoint
- **FlowPilot access tokens**: For `/v1/evaluate` and other authorization endpoints
- **GCP service tokens**: For service-to-service calls (automatic)

=== "User Requests"

    ```bash
    # First exchange Firebase ID token for FlowPilot access token
    Authorization: Bearer <flowpilot-access-token>
    ```

=== "Token Exchange"

    ```bash
    # Only /v1/token/exchange accepts Firebase ID tokens
    Authorization: Bearer <firebase-id-token>
    ```

=== "Service-to-Service"

    ```bash
    # Services use GCP identity tokens (automatic)
    Authorization: Bearer <gcp-identity-token>
    ```

## Endpoints

### Health Check

`GET /health` - No authentication required

Returns service health status.

### Token Exchange

`POST /v1/token/exchange` - Requires Firebase ID token

Exchanges a Firebase ID token (containing PII) for a pseudonymous FlowPilot access token (containing only `sub`).

**Purpose:** Privacy separation - keeps PII in the client, sends only UUID to backend services.

**Request Headers:**
```bash
Authorization: Bearer <firebase-id-token>
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsImtpZCI6ImZsb3dwaWxvdC12MSJ9...",
  "token_type": "Bearer",
  "expires_in": 900
}
```

**Access Token Contents:**
```json
{
  "sub": "user-uuid",
  "iss": "https://flowpilot-authz-api",
  "aud": "flowpilot",
  "exp": 1768401064,
  "iat": 1768400164,
  "token_type": "access"
}
```

**Key Properties:**
- Access tokens contain **only** the user's UUID (`sub`), no PII
- Short-lived (15 minutes by default)
- Signed with FlowPilot's private RSA key
- Use this token for all subsequent API calls to FlowPilot services

### Evaluate Authorization

`POST /v1/evaluate` - Requires authentication

Evaluates whether a subject (agent or user) may perform an action on a resource.

**Request Structure:**
```json
{
  "subject": {
    "type": "agent",
    "id": "agent_flowpilot_1"
  },
  "action": {
    "name": "execute"
  },
  "resource": {
    "type": "workflow_item",
    "id": "i_f032d0a2",
    "properties": {
      "workflow_id": "t_4a6455a3"
    }
  },
  "context": {
    "principal": {
      "type": "user",
      "id": "1460e175-74f9-43af-aac3-7b4fc0547f05",
      "persona": "traveler",
      "circle": "corsica"
    },
    "policy_hint": "travel"
  },
  "options": {
    "dry_run": true,
    "explain": true
  }
}
```

**Response Structure:**
```json
{
  "decision": "allow",
  "reason_codes": [],
  "advice": []
}
```

**Principal Context:**

The `context.principal` object represents the end-user on whose behalf the action is being performed:

- `type`: Principal type (typically "user")
- `id`: User subject identifier (UUID)
- `persona`: User's selected persona title (e.g., "traveler", "travel-agent")
- `circle` (optional): Persona circle for disambiguation when a user has multiple personas with the same title

**Note on Persona Circle:**

The `circle` attribute is used to uniquely identify a persona when a user has multiple personas with the same title. For example, a user might have two "traveler" personas - one for "corsica" and one for "corfu". The circle attribute enables the system to distinguish between them and fetch the correct persona attributes for policy evaluation.

## Decision Flow

1. **JWT Validation**: Validate bearer token and extract claims
2. **Delegation Check**: If subject ≠ principal, query delegation-api (ReBAC)
3. **Policy Evaluation**: Build OPA input and query OPA (ABAC)
4. **Return Decision**: Structured response with decision, reason codes, and advice

## OpenAPI Specification

<swagger-ui src="../flowpilot-openapi/authz.openapi.yaml"/>

## Error Handling

| Status Code | Description |
|-------------|-------------|
| 200 | Authorization decision returned |
| 400 | Bad request or downstream failure |
| 401 | Unauthorized (invalid token) |
| 403 | Forbidden |
| 422 | Validation error |
| 500 | Internal server error |

## Example Usage

### cURL Example

=== "With Token Exchange (Recommended)"

    ```bash
    # Step 1: Authenticate with Firebase and get ID token
    FIREBASE_TOKEN=$(curl -s -X POST \
      "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=$FIREBASE_API_KEY" \
      -H "Content-Type: application/json" \
      -d '{"email":"user@example.com","password":"password","returnSecureToken":true}' \
      | jq -r '.idToken')
    
    # Step 2: Exchange for FlowPilot access token (pseudonymous)
    ACCESS_TOKEN=$(curl -s -X POST http://localhost:8002/v1/token/exchange \
      -H "Authorization: Bearer $FIREBASE_TOKEN" \
      | jq -r '.access_token')
    
    # Step 3: Make authorization request with access token
    curl -X POST http://localhost:8002/v1/evaluate \
      -H "Authorization: Bearer $ACCESS_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{
        "subject": {"type": "agent", "id": "agent-runner"},
        "action": {"name": "execute"},
        "resource": {
          "type": "workflow_item",
          "id": "i_abc123",
          "properties": {"workflow_id": "w_xyz789"}
        },
        "context": {
          "principal": {
            "type": "user",
            "id": "user-uuid",
            "persona": "traveler",
            "circle": "corsica"
          },
          "policy_hint": "travel"
        }
      }'
    ```

=== "Service-to-Service (Keycloak)"

    ```bash
    # Get service token
    TOKEN=$(curl -s -X POST \
      "http://localhost:8080/realms/flowpilot/protocol/openid-connect/token" \
      -d "grant_type=client_credentials" \
      -d "client_id=flowpilot-agent" \
      -d "client_secret=$AGENT_CLIENT_SECRET" | jq -r '.access_token')
    
    # Make authorization request
    curl -X POST http://localhost:8002/v1/evaluate \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{
        "subject": {"type": "agent", "id": "agent-runner"},
        "action": {"name": "execute"},
        "resource": {
          "type": "workflow_item",
          "id": "i_abc123",
          "properties": {"workflow_id": "w_xyz789"}
        },
        "context": {
          "principal": {
            "type": "user",
            "id": "user-uuid",
            "persona": "traveler"
          }
        }
      }'
    ```

### Python Example

```python
import requests

# Step 1: Authenticate with Firebase
firebase_response = requests.post(
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword",
    params={"key": FIREBASE_API_KEY},
    json={
        "email": "user@example.com",
        "password": "password",
        "returnSecureToken": True
    }
)
firebase_token = firebase_response.json()["idToken"]

# Step 2: Exchange for FlowPilot access token
exchange_response = requests.post(
    "http://localhost:8002/v1/token/exchange",
    headers={"Authorization": f"Bearer {firebase_token}"}
)
access_token = exchange_response.json()["access_token"]

# Step 3: Make authorization request with access token
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
}

authz_request = {
    "subject": {"type": "agent", "id": "agent-runner"},
    "action": {"name": "execute"},
    "resource": {
        "type": "workflow_item",
        "id": "i_abc123",
        "properties": {"workflow_id": "w_xyz789"}
    },
    "context": {
        "principal": {
            "type": "user",
            "id": "user-uuid",
            "persona": "traveler"
        }
    }
}

response = requests.post(
    "http://localhost:8002/v1/evaluate",
    json=authz_request,
    headers=headers
)

decision = response.json()
print(f"Decision: {decision['decision']}")
```

## Related Documentation

- [Authorization Architecture](../architecture/authorization.md)
- [OPA Policy Development](../development/policies.md)
- [Delegation API](delegation.md)
