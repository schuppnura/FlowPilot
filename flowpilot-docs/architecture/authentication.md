# Authentication Architecture

FlowPilot implements a **two-tier token architecture** designed to maximize privacy and minimize PII exposure across the platform. Client applications authenticate with Firebase (or Keycloak for local development), then immediately exchange the OIDC ID token for a pseudonymous FlowPilot access token that contains **only the user's subject identifier (`sub`)**.

## Core Principles

### Privacy by Design

**FlowPilot tokens contain ZERO PII:**
- ❌ No name, no username
- ❌ No email addresses 
- ❌ No persona attributes
- ✅ Only the pseudononymous UUID (`sub`)

**Benefits:**
- Tokens remain small and stable
- Privacy preserved by design
- Lower breach impact (token compromise reveals no PII)
- GDPR-friendly
- Minimal data exposure to services and logs

### Separation of Concerns

**Identity Provider (Firebase/Keycloak):**
- Manages user accounts and credentials
- Issues OIDC ID tokens for authentication
- Supports a wide variety of authentication mechanisms, including federation and two-factor
- **Client-facing only** - backend services never see these tokens

**FlowPilot AuthZ API:**
- Exchanges OIDC tokens for pseudonymous access tokens
- Issues minimal JWTs with `sub` only
- Signs tokens with FlowPilot's private key
- All backend services validate FlowPilot tokens

**Authorization Services:**
- Operate on pseudonymous tokens (`sub` only)
- Fetch persona attributes on-demand when needed for policy decisions
- Only authz-api, persona-api, and OPA see persona details

**Domain-specifc Services:**
- Operate on pseudonymous tokens (`sub` only)
- Never obtain user account data for the identity provider or through a JWT
- Never obtain any persona attributes

## Privacy Architecture

### Data Flow Separation

```
┌──────────────────────────────────────────────────────────────┐
│                      CLIENT TIER                             │
│  • Firebase ID Token (contains PII: email, name, etc.)       │
│  • Used ONLY for initial authentication                      │
│  • NEVER sent to backend services                            │
└──────────────────────────────────────────────────────────────┘
                            ↓
                    Token Exchange
                            ↓
┌──────────────────────────────────────────────────────────────┐
│                   BACKEND SERVICE TIER                       │
│  • FlowPilot Access Token (contains ONLY sub UUID)           │
│  • Used for ALL backend API calls                            │
│  • No PII in tokens or logs                                  │
└──────────────────────────────────────────────────────────────┘
                            ↓
                  Authorization Decision Needed
                            ↓
┌──────────────────────────────────────────────────────────────┐
│                  AUTHORIZATION TIER                          │
│  • AuthZ API fetches persona attributes on-demand            │
│  • Only authz-api, persona-api, and OPA see attributes  │
│  • Attributes never logged or exposed                        │
└──────────────────────────────────────────────────────────────┘
```

### Services and PII Exposure

| Service | Sees User UUID | Sees PII | Sees Persona Attributes |
|---------|---------------|----------|------------------------|
| Client Apps | ✅ | ✅ (Firebase token) | ❌ |
| AuthZ API (exchange endpoint) | ✅ | ✅ (during exchange only) | ❌ |
| AuthZ API (evaluate endpoint) | ✅ | ❌ | ✅ (owner only, for policies) |
| User Profile API | ✅ | ❌ | ✅ (owns persona data) |
| Domain Services API | ✅ | ❌ | ❌ |
| Delegation API | ✅ | ❌ | ❌ |
| AI Agent API | ✅ | ❌ | ❌ |
| OPA | ✅ | ❌ | ✅ (for policy evaluation) |

**Key Insight:** Most services operate with **zero knowledge** of user identity beyond UUID. Only 3 services (authz-api, persona-api, OPA) ever see persona attributes, and only when making authorization decisions.

## Security Considerations

### Token Storage

**Client Applications:**
- Store FlowPilot access tokens securely (iOS Keychain, secure storage)
- Never log tokens
- Clear tokens on logout
- Refresh proactively before expiry

**Backend Services:**
- Tokens are transient (not stored)
- Validate on every request
- Never log tokens

### Token Transmission

- **Always use HTTPS** in production
- **Use Authorization header** (never query parameters)
- **Never expose tokens** in logs, error messages, or URLs

### Defense in Depth

**Layer 1: Signature Validation**
- All tokens cryptographically verified

**Layer 2: Issuer/Audience Validation**
- Prevents token substitution attacks

**Layer 3: Expiry Checks**
- Short-lived tokens (15 minutes)

**Layer 4: Token Type Validation**
- Ensures correct token for endpoint

**Layer 5: Minimal Claims**
- Only `sub` exposed (no PII)

## Authentication Flows

### 1. Client Authentication & Token Exchange

**Flow:** OIDC Authentication → Token Exchange → Platform Access

Client applications (web app, iOS app, test scripts) follow this pattern:

```
┌─────────┐                    ┌──────────┐                 ┌────────────┐
│ Client  │                    │ Firebase │                 │  AuthZ API │
│   App   │                    │   Auth   │                 │            │
└────┬────┘                    └─────┬────┘                 └──────┬─────┘
     │                               │                             │
     │ 1. Sign in (email/password)   │                             │
     │──────────────────────────────>│                             │
     │                               │                             │
     │ 2. Firebase id-token (PII)    │                             │
     │<──────────────────────────────│                             │
     │                               │                             │
     │ 3. POST /v1/token/exchange    │                             │
     │    Bearer: <Firebase id-token>│                             │
     │────────────────────────────────────────────────────────────>│
     │                               │                             │
     │                               │    4. Validate Firebase token
     │                               │    5. Extract sub (UUID)    │
     │                               │    6. Create minimal JWT    │
     │                               │                             │
     │ 7. FlowPilot access-token (sub only)                        │
     │<────────────────────────────────────────────────────────────│
     │                               │                             │
     │ 8. Use access-token for ALL backend API calls               │
     │    (domain-services, workflows, delegations, etc.)          │
     │                               │                             │
```

**Steps:**

1. User authenticates with Firebase/Keycloak (email/password, OAuth, passwordless, federated, etc.)
2. Identity provider issues id-token containing PII (email, name, etc.)
3. Client immediately exchanges id-token for FlowPilot access token:
   ```http
   POST https://flowpilot-authz-api/v1/token/exchange
   Authorization: Bearer <Firebase id-Token>
   ```
4. AuthZ API validates Firebase id-token and extracts `sub` (user UUID)
5. AuthZ API issues pseudonymous FlowPilot access-token:
   ```json
   {
     "access_token": "eyJ...",
     "token_type": "Bearer",
     "expires_in": 900
   }
   ```
6. Client uses FlowPilot access-token for all subsequent backend API calls
7. Backend services validate FlowPilot tokens using public key

**FlowPilot Access Token Contents (Pseudonymous):**

```json
{
  "sub": "89eb5366-bab3-46e4-b8e1-abc5f2ea4631",
  "iss": "https://flowpilot-authz-api",
  "aud": "flowpilot",
  "token_type": "access",
  "exp": 1704901200,
  "iat": 1704897600
}
```

**Key Properties:**
- Contains **only** the user's UUID (`sub`)
- Signed by FlowPilot private key (RS256)
- Short-lived (15 minutes default)
- All backend services use this token
- No PII whatsoever

### 2. Service-to-Service Authentication

**Flow:** GCP Identity Tokens (Cloud Run) or Client Credentials (Local)

Backend services authenticate to each other using service accounts.

**Production (GCP Cloud Run):**

```python
import google.auth
import google.auth.transport.requests

def get_service_token():
    """Get service-to-service access token from GCP metadata server."""
    credentials, project = google.auth.default()
    auth_req = google.auth.transport.requests.Request()
    credentials.refresh(auth_req)
    return credentials.token

# Use token in requests
headers = {"Authorization": f"Bearer {get_service_token()}"}
response = requests.post(url, json=data, headers=headers)
```

**Local Development (Keycloak):**

```python
import requests

def get_service_token_local():
    """Get service token using client credentials flow."""
    response = requests.post(
        keycloak_token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": "flowpilot-agent",
            "client_secret": os.environ["AGENT_CLIENT_SECRET"],
        }
    )
    return response.json()["access_token"]
```

**Service Account Personas:**
- `ai-agent` - AI agents executing workflows
- `service` - Generic service accounts

## Token Validation

### FlowPilot Token Validation (Primary Method)

All backend services validate FlowPilot access tokens using the **shared security library**.

**Validation Process:**

1. Extract token from Authorization header
2. Load FlowPilot public key (cached, from file or env var)
3. Verify signature using RS256 algorithm
4. Validate issuer (`https://flowpilot-authz-api`)
5. Validate audience (`flowpilot`)
6. Check expiry (`exp` > now)
7. Verify token type (`token_type == "access"`)
8. Extract sub (user UUID)

**Implementation Pattern:**

```python
from fastapi import Depends, HTTPException
import security

def get_token_claims(
    token_claims: dict = Depends(security.verify_token)
) -> dict:
    """Dependency that validates FlowPilot JWT and returns claims."""
    return token_claims

@app.post("/protected-endpoint")
def protected_handler(
    token_claims: dict = Depends(get_token_claims)
):
    user_sub = token_claims["sub"]  # Only sub available - no PII
    
    # Use validated UUID
    return {"message": f"Hello {user_sub}"}
```

**Configuration (Environment Variables):**

```bash
# FlowPilot token validation (all services)
FLOWPILOT_PUBLIC_KEY_PATH=/secrets/signing-key-pub  # Public key for verification
FLOWPILOT_TOKEN_ISSUER=https://flowpilot-authz-api
FLOWPILOT_TOKEN_AUDIENCE=flowpilot

# Or use environment variable directly (Cloud Run secrets)
SIGNING_KEY_PUB_CONTENT="-----BEGIN PUBLIC KEY-----\n..."
```

### Firebase Token Validation (Exchange Endpoint Only)

**Only the `/v1/token/exchange` endpoint validates Firebase tokens** using Firebase Admin SDK.

```python
from fastapi import Depends
import security

@app.post("/v1/token/exchange")
def post_token_exchange(
    token_claims: dict = Depends(security.verify_firebase_token),
):
    """Exchange Firebase ID token for FlowPilot access token."""
    user_sub = token_claims["sub"]
    
    # Create minimal FlowPilot token with sub only
    access_token = create_flowpilot_token(user_sub)
    
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 900
    }
```

**Firebase Admin SDK automatically:**
- Verifies signature using Firebase public keys
- Validates issuer (Firebase project)
- Validates audience
- Checks token expiry
- Caches public keys (no per-request network calls)

## Token Lifecycle

### 1. Initial Authentication

```
User → Firebase → Client receives ID token (with PII)
```

### 2. Token Exchange

```
Client → AuthZ API /v1/token/exchange → Client receives access token (sub only)
```

### 3. Backend API Calls

```
Client → Backend Service → Validates FlowPilot token → Extracts sub
```

### 4. Persona Data Fetching (On-Demand)

When authorization decisions require persona attributes:

```
Backend Service → AuthZ API /v1/evaluate
                    ↓
               AuthZ API fetches persona from persona-api
                    ↓
               OPA evaluates policy with persona attributes
                    ↓
               Decision returned (allow/deny + reasons)
```

**Key Point:** Persona attributes are **never in tokens**. They are fetched on-demand only when needed for authorization decisions, and only authz-api, persona-api, and OPA see them.

### Token Expiry and Refresh

**FlowPilot Access Token:**
- Short-lived (15 minutes default, configurable)
- Client must re-exchange Firebase token when expired

**Firebase ID Token:**
- Firebase SDK handles automatic refresh
- Typically 1 hour lifetime

**Refresh Flow:**

```python
# Client-side refresh logic
def get_valid_access_token():
    if flowpilot_token_expired():
        # Get fresh Firebase token (SDK auto-refreshes)
        firebase_token = firebase.auth().currentUser.getIdToken()
        
        # Exchange for new FlowPilot token
        response = requests.post(
            f"{authz_api_url}/v1/token/exchange",
            headers={"Authorization": f"Bearer {firebase_token}"}
        )
        return response.json()["access_token"]
    
    return cached_flowpilot_token
```

## Key Management

### FlowPilot Signing Keys

**Private Key (AuthZ API only):**
- Signs FlowPilot access tokens
- Stored in `/secrets/flowpilot-signing-key.pem`
- RSA 2048-bit or higher
- **Never exposed** outside authz-api

**Public Key (All Services):**
- Validates FlowPilot access tokens
- Stored in `/secrets/flowpilot-signing-key-pub.pem`
- Distributed to all backend services
- Can be public (no security risk)

**Generation:**

```bash
# Generate RSA key pair
openssl genrsa -out flowpilot-signing-key.pem 2048
openssl rsa -in flowpilot-signing-key.pem -pubout -out flowpilot-signing-key-pub.pem

# Store in secrets directory
cp flowpilot-signing-key*.pem secrets/
```

**Cloud Run Secret Mounting:**

```bash
# Create secrets in Google Secret Manager
gcloud secrets create flowpilot-signing-key --data-file=secrets/flowpilot-signing-key.pem
gcloud secrets create flowpilot-signing-key-pub --data-file=secrets/flowpilot-signing-key-pub.pem

# Mount as environment variables in Cloud Run
gcloud run services update flowpilot-authz-api \
  --update-secrets SIGNING_KEY_CONTENT=flowpilot-signing-key:latest

gcloud run services update flowpilot-domain-services-api \
  --update-secrets SIGNING_KEY_PUB_CONTENT=flowpilot-signing-key-pub:latest
```

## Troubleshooting

### Invalid Token Signature

**Symptom:** 401 Unauthorized - "Invalid FlowPilot access token"

**Causes:**
- Public key mismatch (services using wrong key)
- Token signed with wrong private key
- Clock skew between services

**Solutions:**

```bash
# Verify public key is correct
cat /secrets/flowpilot-signing-key-pub.pem

# Check environment configuration
echo $FLOWPILOT_PUBLIC_KEY_PATH
echo $FLOWPILOT_TOKEN_ISSUER

# Restart service to reload key
docker compose restart flowpilot-domain-services-api
```

### Token Expired

**Symptom:** 401 Unauthorized - "Token expired"

**Solution:** Client must exchange a fresh Firebase token:

```python
# Client refresh logic
firebase_token = await firebase.auth().currentUser.getIdToken(true)  # Force refresh
response = await exchange_token(firebase_token)
flowpilot_token = response["access_token"]
```

### Firebase Token in Backend Call

**Symptom:** 401 Unauthorized - "Invalid FlowPilot access token"

**Cause:** Client sending Firebase ID token instead of FlowPilot access token

**Solution:** Ensure client exchanges Firebase token first:

```python
# ❌ WRONG - sending Firebase token to backend
response = requests.post(
    f"{domain_services_api}/v1/workflows",
    headers={"Authorization": f"Bearer {firebase_token}"}  # Wrong!
)

# ✅ CORRECT - exchange first, then use FlowPilot token
flowpilot_token = exchange_for_flowpilot_token(firebase_token)
response = requests.post(
    f"{domain_services_api}/v1/workflows",
    headers={"Authorization": f"Bearer {flowpilot_token}"}  # Correct!
)
```

## Best Practices

### Development

- ✅ Use token exchange in all client applications
- ✅ Test token expiry and refresh scenarios
- ✅ Never commit signing keys or secrets
- ✅ Use short-lived tokens (15 minutes or less)
- ✅ Validate tokens on every backend request

### Production

- ✅ Use managed secrets (Google Secret Manager, AWS Secrets Manager)
- ✅ Rotate signing keys periodically
- ✅ Monitor authentication failures
- ✅ Set appropriate token lifespans (balance security vs UX)
- ✅ Use HTTPS everywhere
- ❌ Never use `verify=False` for TLS
- ❌ Never log tokens or PII
- ❌ Never store tokens in plaintext
- ❌ Never send Firebase tokens to backend services

### Privacy

- ✅ Always exchange Firebase tokens immediately
- ✅ Use pseudonymous tokens (sub only) for all backend calls
- ✅ Fetch persona attributes on-demand only when needed
- ✅ Never log persona attributes
- ✅ Limit persona data exposure to authz-api, persona-api, and OPA only

## Related Documentation

- [Authorization Architecture](authorization.md) - How authorization decisions are made
- [Persona Guide](../development/personas.md) - Persona data model and lifecycle
- [Security Overview](../contributing/security.md) - Overall security architecture
