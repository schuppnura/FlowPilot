# Token Separation Proposal: Pseudonymous Access Tokens

## Problem Statement

Currently, FlowPilot uses OIDC ID tokens (with `openid`, `email`, `profile` scopes) as OAuth Bearer access tokens for authorization. This violates privacy principles:

**Current Issues:**
1. **PII Proliferation** - Email, name, and profile data propagated to all services
2. **Token Misuse** - ID tokens are for authentication (client UI), not authorization (API calls)
3. **Over-exposure** - Services receive claims they don't need (`email`, `preferred_username`, etc.)
4. **Privacy Risk** - Logs, traces, and error messages may leak PII

**Current Token Flow:**
```
User → Client App → domain-services-api → authz-api
         [ID Token]    [ID Token]            [ID Token]
         ↓             ↓                     ↓
    email, name,   email, name,          email, name,
    profile        profile               profile
```

## Proposed Solution

**Separate ID tokens (client-side) from access tokens (API authorization):**

### Token Types

**1. ID Token (Client-Side Only)**
- **Purpose**: Client UI personalization (display name, email, avatar)
- **Scopes**: `openid`, `email`, `profile`
- **Contains**: `sub`, `email`, `preferred_username`, `name`, `picture`, `persona`
- **Usage**: Client app only, NEVER sent to APIs
- **Lifetime**: Short (1 hour)

**2. Access Token (API Authorization)**
- **Purpose**: Service-to-service authorization
- **Scopes**: Custom scopes (e.g., `flowpilot:workflow`, `flowpilot:execute`)
- **Contains**: `sub`, `persona` ONLY (pseudonymous)
- **Usage**: Authorization header for all API calls
- **Lifetime**: Short (15 minutes), refreshable

### Updated Token Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ Client App (Swift, React, etc.)                                 │
├─────────────────────────────────────────────────────────────────┤
│ Token Exchange:                                                  │
│   1. OIDC Auth Flow → Receives:                                 │
│      - ID Token (email, name, profile) → Store for UI           │
│      - Access Token (sub, persona only) → Use for API calls     │
│      - Refresh Token → Get new access tokens                    │
│                                                                  │
│ UI Display: Use ID Token claims                                 │
│   - Welcome, {name}!                                            │
│   - {email}                                                     │
│                                                                  │
│ API Calls: Use Access Token ONLY                               │
│   - Authorization: Bearer {access_token}                        │
│   - Contains: sub=uuid, persona=traveler                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Authorization: Bearer {access_token}
                              │ (sub + persona ONLY)
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Backend Services (domain-services, authz, delegation, etc.)     │
├─────────────────────────────────────────────────────────────────┤
│ Receives: Access Token with minimal claims                      │
│   {                                                             │
│     "sub": "d91fb602-29f2-43d0-8878-4d646f442967",            │
│     "persona": "traveler",                                      │
│     "iss": "https://...",                                       │
│     "aud": "flowpilot",                                         │
│     "exp": 1234567890,                                          │
│     "iat": 1234567000                                           │
│   }                                                             │
│                                                                  │
│ NO email, NO name, NO profile data                             │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation Plan

### Phase 1: Keycloak Configuration

**1. Create Custom Client Scope: `flowpilot`**

```bash
# Create flowpilot scope
curl -X POST "https://keycloak/admin/realms/flowpilot/client-scopes" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "flowpilot",
    "description": "FlowPilot pseudonymous access token scope",
    "protocol": "openid-connect",
    "attributes": {
      "include.in.token.scope": "true",
      "display.on.consent.screen": "false"
    }
  }'

# Add 'persona' mapper to flowpilot scope
curl -X POST "https://keycloak/admin/realms/flowpilot/client-scopes/{scope-id}/protocol-mappers/models" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "persona-mapper",
    "protocol": "openid-connect",
    "protocolMapper": "oidc-usermodel-attribute-mapper",
    "config": {
      "user.attribute": "persona",
      "claim.name": "persona",
      "jsonType.label": "String",
      "id.token.claim": "false",
      "access.token.claim": "true",
      "userinfo.token.claim": "false",
      "multivalued": "true"
    }
  }'
```

**2. Configure Desktop Client**

```bash
# Add flowpilot scope as default scope
curl -X PUT "https://keycloak/admin/realms/flowpilot/clients/{client-id}/default-client-scopes/{flowpilot-scope-id}" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Configure client to issue separate access token
curl -X PUT "https://keycloak/admin/realms/flowpilot/clients/{client-id}" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "clientId": "flowpilot-desktop",
    "protocol": "openid-connect",
    "publicClient": true,
    "standardFlowEnabled": true,
    "implicitFlowEnabled": false,
    "directAccessGrantsEnabled": false,
    "defaultClientScopes": ["openid", "flowpilot"],
    "optionalClientScopes": ["email", "profile"]
  }'
```

**Key Configuration:**
- **Default scopes**: `openid`, `flowpilot` (always included)
- **Optional scopes**: `email`, `profile` (client must request explicitly)
- **Access token claims**: `sub`, `persona` ONLY
- **ID token claims**: `sub`, `email`, `name`, `persona` (for UI)

### Phase 2: Client Updates

**Swift Client (macOS App)**

```swift
// Current (WRONG - uses ID token for API calls)
accessToken = tokens.idToken  // Contains email, name, etc.

// Proposed (CORRECT - separate tokens)
struct OidcTokenResponse: Codable {
    let access_token: String     // For API calls (sub + persona ONLY)
    let id_token: String          // For UI display (email, name, profile)
    let expires_in: Int
    let refresh_token: String?
}

// Store both tokens
self.idToken = tokens.id_token           // Use for UI personalization
self.accessToken = tokens.access_token    // Use for API Authorization headers

// UI: Extract display info from ID token
func extractUserInfoFromIdToken() {
    let claims = try JwtUtils.decodeClaims(idToken: idToken)
    self.username = claims["name"] as? String
    self.email = claims["email"] as? String
}

// API calls: Use access token (pseudonymous)
func makeAPICall() {
    let headers = ["Authorization": "Bearer \(accessToken)"]
    // accessToken contains ONLY: sub, persona
}
```

**Web Client (React)**

```typescript
// After OIDC callback
const tokens = await oidcClient.getTokens();

// Store separately
localStorage.setItem('id_token', tokens.id_token);      // For UI
localStorage.setItem('access_token', tokens.access_token); // For API

// UI: Use ID token
const idTokenClaims = parseJwt(tokens.id_token);
setUserName(idTokenClaims.name);
setUserEmail(idTokenClaims.email);

// API calls: Use access token
const apiHeaders = {
  'Authorization': `Bearer ${localStorage.getItem('access_token')}`
};
```

### Phase 3: Backend Services (No Changes Needed!)

Backend services already only use `sub` from tokens:

```python
# authz_core.py - Already pseudonymous
def evaluate_authorization_request(authzen_request):
    # Extract ONLY sub from token
    principal_id = context.get("principal", {}).get("id")
    # Fetch full persona from persona-api using sub
    owner_persona = fetch_persona_from_api(owner_persona_id)
```

**Current behavior is CORRECT** - services only use `sub`, never email/name.

**Problem is CLIENT** - currently sends ID token instead of access token.

### Phase 4: Firebase Migration

Firebase doesn't distinguish between ID tokens and access tokens (Firebase ID tokens ARE the access tokens).

**Solution: Custom Token Exchange**

```python
# New endpoint: POST /v1/token/exchange
# Exchange Firebase ID token for pseudonymous access token

from jose import jwt

@app.post("/v1/token/exchange")
def exchange_token(
    firebase_token: str = Body(..., embed=True),
    token_claims: dict = Depends(security.verify_token)
):
    """Exchange Firebase ID token for pseudonymous access token.
    
    Input: Firebase ID token (contains email, name, etc.)
    Output: Pseudonymous JWT (contains only sub + persona)
    """
    # Validate Firebase token (already done by dependency)
    firebase_sub = token_claims["sub"]
    
    # Fetch persona from persona-api
    personas = fetch_user_personas(firebase_sub)
    persona_titles = [p["title"] for p in personas]
    
    # Create minimal access token
    access_token = jwt.encode(
        {
            "sub": firebase_sub,
            "persona": persona_titles,
            "iss": "https://flowpilot-authz-api",
            "aud": "flowpilot",
            "exp": time.time() + 900,  # 15 minutes
            "iat": time.time(),
        },
        private_key,  # FlowPilot's own signing key
        algorithm="RS256"
    )
    
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 900
    }
```

**Client Flow:**
```swift
// 1. Sign in with Firebase (get ID token)
let firebaseTokens = try await firebaseAuthClient.signIn(email: email, password: password)
self.idToken = firebaseTokens.idToken  // For UI

// 2. Exchange for pseudonymous access token
let response = try await exchangeToken(firebaseToken: firebaseTokens.idToken)
self.accessToken = response.access_token  // For API calls
```

## Migration Strategy

### Step 1: Add Token Exchange Endpoint (Non-Breaking)
- Add `/v1/token/exchange` to authz-api
- No client changes yet
- Test with manual token exchange

### Step 2: Update Keycloak Configuration (Non-Breaking)
- Create `flowpilot` client scope
- Configure desktop client for separate tokens
- Old clients still work (use ID token)

### Step 3: Update Clients (Breaking for Keycloak, Additive for Firebase)
- **Keycloak clients**: Use `access_token` instead of `id_token`
- **Firebase clients**: Call token exchange, use returned token

### Step 4: Enforce Access Token Usage (Breaking)
- Update backend to reject tokens with PII claims
- Validate `aud=flowpilot` (not `aud=account`)

## Benefits

✅ **Privacy by Design** - No PII in API authorization  
✅ **OIDC Compliance** - Proper separation of ID vs access tokens  
✅ **Minimal Logging** - Logs contain UUIDs, not emails  
✅ **Audit-Friendly** - Authorization traces are pseudonymous  
✅ **GDPR-Ready** - PII minimization principle  
✅ **Security** - Reduced attack surface (less data exposed)

## Testing Plan

### Unit Tests
- Test token exchange endpoint with Firebase tokens
- Validate access tokens contain only `sub` + `persona`
- Verify ID tokens still contain full claims

### Integration Tests
```bash
# Test 1: Verify access token is pseudonymous
TOKEN=$(curl -X POST .../v1/token/exchange -d '{"firebase_token": "..."}' | jq -r .access_token)
jwt decode $TOKEN | jq .
# Expected: {"sub": "uuid", "persona": ["traveler"], "iss": "...", "aud": "flowpilot"}

# Test 2: Verify backend accepts access token
curl -X POST .../v1/workflows \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"start_date": "2026-02-01", "persona": "traveler"}'
# Expected: 201 Created

# Test 3: Verify backend rejects ID token
curl -X POST .../v1/workflows \
  -H "Authorization: Bearer $ID_TOKEN" \
  -d '{"start_date": "2026-02-01", "persona": "traveler"}'
# Expected: 401 Unauthorized (audience mismatch)
```

## Documentation Updates

- [ ] Update authentication.md with token separation
- [ ] Add token exchange endpoint to API docs
- [ ] Update client integration guides
- [ ] Add security best practices section
- [ ] Update privacy policy / data handling docs

## References

- [OAuth 2.0 RFC 6749](https://tools.ietf.org/html/rfc6749) - Access tokens vs ID tokens
- [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html) - ID token spec
- [OAuth 2.0 Token Exchange RFC 8693](https://tools.ietf.org/html/rfc8693) - Token exchange patterns
- [GDPR Article 5](https://gdpr-info.eu/art-5-gdpr/) - Data minimization principle
