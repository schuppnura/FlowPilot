# Security Architecture

FlowPilot implements defense-in-depth security with multiple layers of protection at every boundary.

## Security Principles

The system is built on the following security principles:

1. **Fail-closed by default** - Deny unless explicitly allowed
2. **Zero trust** - Validate every request at every boundary
3. **Minimal PII exposure** - Only process pseudonymous identifiers
4. **Defense-in-depth** - Multiple security layers
5. **Explicit authorization** - Never assume permissions

## Defense-in-Depth Layers

### Layer 1: JWT Validation

All services validate bearer tokens using Firebase Admin SDK:

**Validation checks (performed by Firebase Admin SDK):**

- **Signature verification** - Using Firebase public keys
- **Issuer validation** - Must be Firebase (`securetoken.google.com`)
- **Audience validation** - Must match Firebase project ID
- **Expiry check** - Token must not be expired (`exp` claim)
- **Issued-at check** - Token must have valid issue time (`iat` claim)
- **Authentication time** - Validates `auth_time` claim

**Benefits:**

- **Zero network calls per request** - Public keys cached by SDK
- **High performance** - Local cryptographic verification
- **Resilient** - No dependency on Firebase servers for validation
- **Automatic key rotation** - SDK handles Firebase key updates

**Implementation pattern:**

```python
from fastapi import Depends
import security

def get_token_claims(
    token_claims: dict = Depends(security.verify_token)
) -> dict:
    return token_claims

@app.post("/endpoint")
def handler(token_claims: dict = Depends(get_token_claims)):
    user_sub = token_claims["sub"]
    # Use validated claims
```

### Layer 2: Input Validation

Four-layer input validation approach:

**1. Pydantic Model Validation**

- Type validation
- Field presence checks
- Range validation
- Format validation

**2. Path Parameter Validation**

- Parameter type enforcement
- Required parameter checks
- Pattern matching

**3. String Sanitization**

- Control character rejection
- Maximum length enforcement
- Pattern validation
- Unicode normalization

**4. Request Size Limits**

- Default: 1MB maximum request size
- Configurable via `MAX_REQUEST_SIZE_MB`
- Prevents denial-of-service attacks

**Implementation pattern:**

```python
import security

try:
    sanitized = security.sanitize_request_json_payload(request_body)
except security.InputValidationError as e:
    raise HTTPException(status_code=400, detail=str(e))
```

### Layer 3: Injection Prevention

**Attack Pattern Detection:**

- Optional signature scanning for common attack patterns
- Configurable via `ENABLE_PAYLOAD_SIGNATURE_SCAN`
- Detects SQL injection, command injection, XSS attempts

**Control Character Rejection:**

- All string inputs sanitized
- Control characters stripped or rejected
- Prevents payload smuggling attacks

### Layer 4: Security Headers

Six protective headers on all HTTP responses:

1. **`X-Content-Type-Options: nosniff`** - Prevents MIME sniffing
2. **`X-Frame-Options: DENY`** - Prevents clickjacking
3. **`X-XSS-Protection: 1; mode=block`** - Enables XSS protection
4. **`Strict-Transport-Security: max-age=31536000`** - Enforces HTTPS
5. **`Content-Security-Policy: default-src 'self'`** - Restricts resource loading
6. **`Referrer-Policy: no-referrer`** - Prevents referrer leakage

### Layer 5: Error Handling

Production-safe error messages:

- **Development mode** (`INCLUDE_ERROR_DETAILS=1`): Detailed error messages
- **Production mode** (`INCLUDE_ERROR_DETAILS=0`): Sanitized error messages
- No stack traces exposed to clients
- No internal paths or configuration leaked

**Implementation:**

```python
INCLUDE_ERROR_DETAILS = os.environ.get("INCLUDE_ERROR_DETAILS", "1") == "1"

try:
    # ... operation ...
except Exception as exc:
    error_detail = security.sanitize_error_message(
        str(exc), 
        INCLUDE_ERROR_DETAILS
    )
    raise HTTPException(status_code=500, detail=error_detail)
```

### Layer 6: PII Protection

**Zero PII exposure:**

- **Tokens contain only `sub` (UUID)** - No names, emails, or personal data
- **Logs use pseudonymous identifiers** - No PII in application logs
- **Authorization decisions use UUIDs** - No identity data in policy evaluation
- **AI agents never see PII** - Only workflow context and pseudonymous IDs

**Benefits:**

- Minimal data surface for breaches
- Simplified compliance (GDPR, CCPA)
- Lower forensic costs
- Reproducible authorization without identity data

## Shared Security Library

All security utilities are centralized in the shared library:

**Location:** `flowpilot-services/shared-libraries/security.py`

**Provides:**

- `verify_token()` - JWKS-based JWT validation
- `sanitize_request_json_payload()` - Input sanitization
- `sanitize_string()` - String sanitization
- `sanitize_error_message()` - Error message sanitization
- `SecurityHeadersMiddleware` - Security headers middleware
- `RequestSizeLimiterMiddleware` - Request size limiting
- `get_cors_config()` - CORS configuration

**IMPORTANT:** Changes to shared libraries require container rebuilds (files are copied at build time).

## TLS and Certificate Management

### Local Development

**Using mkcert for local TLS:**

```bash
# Install mkcert
brew install mkcert

# Install local CA
mkcert -install

# Copy root CA to project
cp "$(mkcert -CAROOT)/rootCA.pem" infra/certs/mkcert-rootCA.pem
```

**Services use `verify=False` in development:**

```python
# LOCAL DEV ONLY - NEVER IN PRODUCTION
response = requests.post(
    url,
    data=data,
    verify=False  # ⚠️ Only for local development
)
```

### Production Deployment

- **Never use `verify=False` in production**
- Use proper TLS certificates
- Configure certificate validation
- Enable HSTS headers

## Authentication Flows

### Desktop Client → Services

**Authorization Code + PKCE flow:**

1. User clicks login in desktop app
2. App opens browser to Keycloak
3. User authenticates
4. Keycloak returns authorization code
5. App exchanges code for access token (with PKCE)
6. App uses access token for API calls

**Token characteristics:**

- Short-lived (configurable)
- Contains `sub` and `persona` claims
- Validated locally by services

### Service → Service

**Client Credentials flow:**

```python
def get_service_token():
    response = requests.post(
        os.environ["KEYCLOAK_TOKEN_URL"],
        data={
            "grant_type": "client_credentials",
            "client_id": os.environ["AGENT_CLIENT_ID"],
            "client_secret": os.environ["AGENT_CLIENT_SECRET"],
        },
        verify=False  # Local dev only
    )
    return response.json()["access_token"]
```

**Service account:** `flowpilot-agent`

## Environment Configuration

### Security Environment Variables

**JWT Validation:**

Firebase Admin SDK uses Application Default Credentials (ADC) - no configuration needed on Cloud Run.

For local development:

```bash
GOOGLE_APPLICATION_CREDENTIALS=/path/to/serviceAccountKey.json  # Optional
```

**Input Validation:**

```bash
ENABLE_PAYLOAD_SIGNATURE_SCAN=0  # 1 to enable attack signature scanning
MAX_REQUEST_SIZE_MB=1
```

**Error Handling:**

```bash
INCLUDE_ERROR_DETAILS=1  # Set to 0 in production
```

**Secrets (.env file - never commit):**

```bash
KEYCLOAK_ADMIN_USERNAME=admin
KEYCLOAK_ADMIN_PASSWORD=<your-password>
KEYCLOAK_CLIENT_SECRET=<your-secret>
AGENT_CLIENT_SECRET=<your-secret>
```

## Security Best Practices

### Development

- ✅ Use environment variables for configuration
- ✅ Never commit `.env` file
- ✅ Use mkcert for local TLS
- ✅ Enable detailed errors for debugging
- ✅ Test with malformed inputs

### Production

- ✅ Set `INCLUDE_ERROR_DETAILS=0`
- ✅ Set `ENABLE_PAYLOAD_SIGNATURE_SCAN=1`
- ✅ Use proper TLS certificates
- ✅ Rotate secrets regularly
- ✅ Monitor for unauthorized access attempts
- ✅ Enable audit logging
- ❌ Never use `verify=False` for TLS
- ❌ Never expose internal error details
- ❌ Never log PII

### Code Reviews

When reviewing code, check for:

- JWT validation on all protected endpoints
- Input sanitization before processing
- Fail-closed authorization logic
- No PII in logs or error messages
- Proper use of security middleware
- No hard-coded secrets

## Threat Model

The system is designed to defend against:

### External Threats

- **Token theft** - Mitigated by short-lived tokens and signature validation
- **Replay attacks** - Mitigated by token expiry and nonce validation
- **Injection attacks** - Mitigated by input sanitization
- **XSS/CSRF** - Mitigated by security headers
- **Man-in-the-middle** - Mitigated by TLS and certificate validation

### Internal Threats

- **Privilege escalation** - Mitigated by explicit delegation and bounded chains
- **Unauthorized access** - Mitigated by fail-closed authorization
- **Data exfiltration** - Mitigated by minimal PII exposure
- **Service impersonation** - Mitigated by mutual TLS and token validation

## Audit and Compliance

### Audit Logging

All authorization decisions are logged:

- Subject, action, resource
- Decision (allow/deny)
- Reason codes
- Timestamp
- Request ID

### Compliance Considerations

**GDPR:**

- Minimal PII by design
- Pseudonymous identifiers (UUIDs)
- Clear data minimization
- Explicit consent mechanisms

**SOC 2:**

- Comprehensive audit logging
- Fail-closed security model
- Separation of duties (PEP/PDP)
- Input validation at boundaries

## Security Contact

For security issues, see `SECURITY.md` for reporting procedures.
