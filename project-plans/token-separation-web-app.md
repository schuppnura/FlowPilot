# Token Separation Implementation: Web App & GCP

## Current State Analysis

### Web App Token Usage

**Problem:** Web app uses Firebase ID token for API authorization

```typescript
// flowpilot-web/src/services/firebase/auth.ts
const idToken = await userCredential.user.getIdToken(true);
return { user: userCredential.user, idToken };  // ❌ ID token used for APIs

// flowpilot-web/src/services/api/base.ts
config.headers.Authorization = `Bearer ${token}`;  // ❌ Sends ID token to APIs
```

**ID Token Contains:**
- `sub` (UUID) ✅
- `email` ❌ (PII)
- `name` ❌ (PII)
- `persona` ✅
- `picture` ❌ (optional PII)
- `email_verified`, `iss`, `aud`, `exp`, etc.

### GCP Deployment

**Backend Services (Cloud Run):**
- authz-api
- domain-services-api
- delegation-api
- user-profile-api
- ai-agent-api

**Current Behavior:**
- ✅ Backend services only extract `sub` from tokens
- ✅ PII is not logged or processed
- ❌ PII is present in token (privacy risk)

## Implementation Plan

### Phase 1: Add Token Exchange Endpoint to AuthZ-API

**Create new endpoint for Firebase→Pseudonymous token exchange**

#### 1.1 Create Token Signing Key

```bash
# Generate RSA key pair for FlowPilot token signing
openssl genrsa -out flowpilot-signing-key.pem 2048
openssl rsa -in flowpilot-signing-key.pem -pubout -out flowpilot-signing-key-pub.pem

# Store in GCP Secret Manager
gcloud secrets create flowpilot-token-signing-key \
  --data-file=flowpilot-signing-key.pem \
  --replication-policy=automatic

gcloud secrets create flowpilot-token-signing-key-pub \
  --data-file=flowpilot-signing-key-pub.pem \
  --replication-policy=automatic
```

#### 1.2 Add Token Exchange Route

**File:** `flowpilot-services/authz-api/authz_main.py`

```python
from jose import jwt
import time
import os

# Load signing key from Secret Manager (cached)
_SIGNING_KEY = None
_SIGNING_KEY_ID = "flowpilot-v1"

def _get_signing_key() -> str:
    global _SIGNING_KEY
    if _SIGNING_KEY:
        return _SIGNING_KEY
    
    # In GCP: load from Secret Manager
    signing_key_path = os.environ.get("SIGNING_KEY_PATH", "/secrets/signing-key")
    with open(signing_key_path, "r") as f:
        _SIGNING_KEY = f.read()
    return _SIGNING_KEY


@app.post("/v1/token/exchange")
def exchange_token(
    token_claims: dict[str, Any] = Depends(get_token_claims)
) -> dict[str, Any]:
    """Exchange Firebase ID token for pseudonymous access token.
    
    Input: Firebase ID token (validated by middleware)
    Output: Pseudonymous JWT (sub + persona ONLY)
    
    This endpoint enables privacy-preserving authorization by converting
    Firebase ID tokens (which contain PII) into minimal access tokens
    that contain only the subject identifier and persona.
    """
    
    # Extract user ID from validated token
    user_sub = token_claims.get("sub")
    if not user_sub:
        raise HTTPException(status_code=400, detail="Missing sub claim")
    
    # Extract persona from ID token (Firebase custom claims)
    persona_claim = token_claims.get("persona", [])
    if isinstance(persona_claim, str):
        personas = [persona_claim] if persona_claim else []
    elif isinstance(persona_claim, list):
        personas = persona_claim
    else:
        personas = []
    
    # Create minimal access token (pseudonymous)
    now = int(time.time())
    access_token_payload = {
        "sub": user_sub,
        "persona": personas,
        "iss": "https://flowpilot-authz-api",  # FlowPilot as issuer
        "aud": "flowpilot",  # FlowPilot services
        "exp": now + 900,  # 15 minutes
        "iat": now,
        "token_type": "access",
        "kid": _SIGNING_KEY_ID,
    }
    
    # Sign with FlowPilot's private key
    signing_key = _get_signing_key()
    access_token = jwt.encode(
        access_token_payload,
        signing_key,
        algorithm="RS256",
        headers={"kid": _SIGNING_KEY_ID}
    )
    
    # Log token exchange (for audit)
    api_logging.log_api_request(
        "POST",
        "/v1/token/exchange",
        request_body={"sub": user_sub, "persona_count": len(personas)}
    )
    
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 900,  # 15 minutes
    }
```

#### 1.3 Update JWT Validation to Accept FlowPilot Tokens

**File:** `flowpilot-services/shared-libraries/security_firebase.py`

```python
# Add FlowPilot public key validation alongside Firebase

_FLOWPILOT_PUBLIC_KEY = None

def _get_flowpilot_public_key() -> str:
    global _FLOWPILOT_PUBLIC_KEY
    if _FLOWPILOT_PUBLIC_KEY:
        return _FLOWPILOT_PUBLIC_KEY
    
    pub_key_path = os.environ.get("FLOWPILOT_PUBLIC_KEY_PATH", "/secrets/signing-key-pub")
    with open(pub_key_path, "r") as f:
        _FLOWPILOT_PUBLIC_KEY = f.read()
    return _FLOWPILOT_PUBLIC_KEY


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
) -> dict[str, Any]:
    """Validate JWT - supports both Firebase ID tokens and FlowPilot access tokens."""
    token = credentials.credentials
    
    try:
        # Decode header to check issuer
        unverified_header = jwt.get_unverified_header(token)
        unverified_claims = jwt.get_unverified_claims(token)
        issuer = unverified_claims.get("iss", "")
        
        # Route to appropriate validator based on issuer
        if "flowpilot-authz-api" in issuer:
            # FlowPilot access token - validate with FlowPilot public key
            public_key = _get_flowpilot_public_key()
            claims = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience="flowpilot",
                issuer="https://flowpilot-authz-api"
            )
            return claims
        else:
            # Firebase ID token - validate with Firebase (existing logic)
            validator = _get_jwt_validator()
            claims = validator.validate(token)
            return claims
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {str(e)}",
        ) from e
```

#### 1.4 Update Docker & Cloud Run Configuration

**File:** `flowpilot-services/authz-api/Dockerfile`

```dockerfile
# Add secret mounting for signing keys
# Keys will be mounted at runtime from Secret Manager
```

**File:** `cloud-run-envs/authz-api.yaml`

```yaml
# Add environment variables for signing keys
SIGNING_KEY_PATH: /secrets/signing-key
FLOWPILOT_PUBLIC_KEY_PATH: /secrets/signing-key-pub
```

**Cloud Run Deployment:**

```bash
# Deploy authz-api with secret mounting
gcloud run deploy flowpilot-authz-api \
  --image us-central1-docker.pkg.dev/PROJECT/flowpilot/flowpilot-authz-api:latest \
  --region us-central1 \
  --set-secrets="/secrets/signing-key=flowpilot-token-signing-key:latest" \
  --set-secrets="/secrets/signing-key-pub=flowpilot-token-signing-key-pub:latest" \
  --env-vars-file cloud-run-envs/authz-api.yaml
```

### Phase 2: Update Web App to Use Token Exchange

#### 2.1 Create Token Exchange Service

**File:** `flowpilot-web/src/services/auth/tokenExchange.ts` (NEW)

```typescript
import { auth } from '../firebase/config';

const AUTHZ_API_URL = import.meta.env.VITE_AUTHZ_API_URL || 
  'https://flowpilot-authz-api-737191827545.us-central1.run.app';

export interface AccessTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

/**
 * Exchange Firebase ID token for pseudonymous FlowPilot access token.
 * 
 * This separates authentication (Firebase ID token with PII for UI)
 * from authorization (pseudonymous access token for API calls).
 */
export async function exchangeToken(): Promise<AccessTokenResponse> {
  const user = auth.currentUser;
  if (!user) {
    throw new Error('No authenticated user');
  }
  
  // Get Firebase ID token
  const idToken = await user.getIdToken(true);
  
  // Exchange for pseudonymous access token
  const response = await fetch(`${AUTHZ_API_URL}/v1/token/exchange`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${idToken}`,  // Firebase ID token for authentication
    },
  });
  
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Token exchange failed: ${response.status} ${errorText}`);
  }
  
  return await response.json();
}

/**
 * Get current access token with automatic refresh.
 * Caches access token and automatically exchanges when expired.
 */
let cachedAccessToken: string | null = null;
let accessTokenExpiry: number = 0;

export async function getAccessToken(): Promise<string | null> {
  const user = auth.currentUser;
  if (!user) {
    cachedAccessToken = null;
    accessTokenExpiry = 0;
    return null;
  }
  
  // Return cached token if still valid (with 60s buffer)
  const now = Date.now() / 1000;
  if (cachedAccessToken && accessTokenExpiry > now + 60) {
    return cachedAccessToken;
  }
  
  // Exchange for new access token
  try {
    const response = await exchangeToken();
    cachedAccessToken = response.access_token;
    accessTokenExpiry = now + response.expires_in;
    return cachedAccessToken;
  } catch (error) {
    console.error('Failed to exchange token:', error);
    cachedAccessToken = null;
    accessTokenExpiry = 0;
    return null;
  }
}

/**
 * Clear cached access token (e.g., on logout)
 */
export function clearAccessToken(): void {
  cachedAccessToken = null;
  accessTokenExpiry = 0;
}
```

#### 2.2 Update AuthContext to Provide Access Token

**File:** `flowpilot-web/src/state/AuthContext.tsx`

```typescript
import { getAccessToken, clearAccessToken } from '../services/auth/tokenExchange';

interface AuthContextType {
  user: User | null;
  idToken: string | null;  // For UI display only
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, persona: string) => Promise<void>;
  signOut: () => Promise<void>;
  getToken: () => Promise<string | null>;  // Returns ACCESS token, not ID token
  getIdToken: () => Promise<string | null>;  // Explicitly get ID token for UI
}

// ... in AuthProvider:

const handleSignOut = async () => {
  await logout();
  clearAccessToken();  // Clear cached access token
  setUser(null);
  setIdToken(null);
};

const getToken = async () => {
  // Return pseudonymous access token for API calls
  return await getAccessToken();
};

const getIdToken = async () => {
  // Return ID token for UI personalization
  if (user) {
    return await user.getIdToken();
  }
  return null;
};
```

#### 2.3 Update API Client to Use Access Token

**File:** `flowpilot-web/src/services/api/base.ts`

```typescript
// No changes needed! Already uses getToken() which now returns access token
// The interceptor automatically adds the access token to requests

client.interceptors.request.use(async (config) => {
  const token = await getToken();  // Now returns access token (sub + persona only)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```

#### 2.4 Update AppStateContext to Use New Token Functions

**File:** `flowpilot-web/src/state/AppStateContext.tsx`

```typescript
export function AppStateProvider({ children }: { children: React.ReactNode }) {
  const { user, getToken, getIdToken } = useAuth();  // getToken now returns access token
  
  // Extract persona from ID token (for UI)
  useEffect(() => {
    const loadPersonas = async () => {
      if (user) {
        const idToken = await getIdToken();  // Explicitly get ID token
        if (idToken) {
          const personas = extractPersonas(idToken);
          setState((prev) => ({ ...prev, personas }));
        }
      }
    };
    loadPersonas();
  }, [user, getIdToken]);
  
  // API clients use getToken() which returns access token
  const domainClientRef = useRef(new DomainServicesClient(getToken));
  // ... etc.
}
```

### Phase 3: Testing & Deployment

#### 3.1 Local Testing

```bash
# 1. Build and deploy authz-api locally
docker compose build flowpilot-authz-api
docker compose up -d flowpilot-authz-api

# 2. Test token exchange endpoint
firebase auth:export --project flowpilot users.json
# Get test user token
TOKEN=$(curl -X POST "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=$FIREBASE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"email":"carlo@me.com","password":"password","returnSecureToken":true}' \
  | jq -r .idToken)

# 3. Exchange token
ACCESS_TOKEN=$(curl -X POST http://localhost:8002/v1/token/exchange \
  -H "Authorization: Bearer $TOKEN" \
  | jq -r .access_token)

# 4. Verify access token is pseudonymous
jwt decode $ACCESS_TOKEN
# Expected output:
# {
#   "sub": "uuid-here",
#   "persona": ["traveler"],
#   "iss": "https://flowpilot-authz-api",
#   "aud": "flowpilot",
#   "exp": ...,
#   "iat": ...
# }

# 5. Test access token works with APIs
curl -X GET http://localhost:8003/v1/workflows \
  -H "Authorization: Bearer $ACCESS_TOKEN"
# Expected: 200 OK
```

#### 3.2 GCP Staging Deployment

```bash
# 1. Create signing keys (one-time)
./scripts/create-token-signing-keys.sh

# 2. Build and push authz-api
gcloud builds submit --config=cloudbuild-authz-api.yaml

# 3. Deploy authz-api with secrets
gcloud run deploy flowpilot-authz-api \
  --image us-central1-docker.pkg.dev/PROJECT/flowpilot/flowpilot-authz-api:latest \
  --region us-central1 \
  --set-secrets="/secrets/signing-key=flowpilot-token-signing-key:latest,/secrets/signing-key-pub=flowpilot-token-signing-key-pub:latest" \
  --env-vars-file cloud-run-envs/authz-api.yaml

# 4. Build and deploy web app
cd flowpilot-web
npm run build
firebase deploy --only hosting

# 5. Test end-to-end
# Open https://flowpilot-web.web.app
# Sign in
# Check Network tab: Authorization headers should contain pseudonymous tokens
# Verify no email/name in API requests
```

#### 3.3 Verification Checklist

- [ ] Token exchange endpoint returns 200 with valid JWT
- [ ] Access tokens contain only `sub` and `persona`
- [ ] Access tokens are accepted by all backend services
- [ ] ID tokens are rejected by backend services (audience mismatch)
- [ ] Web app can sign in and load workflows
- [ ] Web app can create workflows and delegations
- [ ] AI agent can execute workflows
- [ ] No PII (email, name) in backend logs
- [ ] Network tab shows `Authorization: Bearer eyJ...` with pseudonymous token

### Phase 4: Documentation & Monitoring

#### 4.1 Update Documentation

- [ ] Update authentication.md with token exchange flow
- [ ] Add token separation to security.md
- [ ] Update web app integration guide
- [ ] Add troubleshooting section

#### 4.2 Add Monitoring

```typescript
// flowpilot-web/src/services/auth/tokenExchange.ts

// Add error tracking
export async function exchangeToken(): Promise<AccessTokenResponse> {
  try {
    // ... existing code ...
  } catch (error) {
    console.error('[TokenExchange] Failed to exchange token:', error);
    // Send to error tracking service if available
    throw error;
  }
}
```

```python
# flowpilot-services/authz-api/authz_main.py

# Add metrics
@app.post("/v1/token/exchange")
def exchange_token(...):
    # Log for monitoring
    api_logging.log_api_request(
        "POST", "/v1/token/exchange",
        request_body={"sub": user_sub, "persona_count": len(personas)}
    )
    # ... existing code ...
```

## Migration Timeline

### Week 1: Backend Implementation
- [ ] Day 1-2: Create signing keys, add token exchange endpoint
- [ ] Day 3-4: Update JWT validation to accept FlowPilot tokens
- [ ] Day 5: Local testing and debugging

### Week 2: Web App Implementation
- [ ] Day 1-2: Create token exchange service
- [ ] Day 3: Update AuthContext and AppState
- [ ] Day 4-5: Testing and debugging

### Week 3: GCP Deployment
- [ ] Day 1-2: Deploy backend to staging
- [ ] Day 3-4: Deploy web app to staging
- [ ] Day 5: End-to-end testing

### Week 4: Production
- [ ] Day 1-2: Deploy to production
- [ ] Day 3-5: Monitor, fix issues, optimize

## Rollback Plan

If issues occur:

1. **Immediate**: Revert web app to use ID tokens directly (previous behavior)
2. **Backend**: Token exchange endpoint is additive—no breaking changes
3. **JWT Validation**: Dual-token support means old tokens still work

## Benefits

✅ **Privacy**: No PII in backend authorization  
✅ **Compliance**: GDPR data minimization  
✅ **Security**: Reduced attack surface  
✅ **Auditability**: Pseudonymous authorization traces  
✅ **Flexibility**: Same backend works for Keycloak and Firebase  
✅ **Backward Compatible**: ID tokens still work during migration
