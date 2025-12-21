# JWT Validation in FlowPilot

## Overview

FlowPilot uses **local JWT validation** for bearer token authentication. This provides significant performance and scalability benefits compared to token introspection.

## How It Works

### Local JWT Validation

Instead of making a network call to Keycloak for every request, the system:

1. **Fetches Keycloak's public keys (JWKS)** once and caches them
2. **Validates JWT signatures locally** using the cached public keys
3. **Checks standard claims** (exp, nbf, iss, aud) according to OAuth 2.0 best practices
4. **Refreshes keys automatically** when cache expires (default: 1 hour)

### Benefits

- **Performance**: ~1-2ms vs ~50-200ms for network introspection
- **Scalability**: No load on Keycloak for token validation
- **Offline capability**: Works even if Keycloak is temporarily unavailable (uses cached keys)
- **Best practices**: Comprehensive claim validation following OAuth 2.0/OIDC standards

## Validation Checks

The JWT validator performs the following checks:

### Standard JWT Claims

1. **Signature Verification** (`sig`)
   - Validates JWT signature using Keycloak's public key (RS256 algorithm)
   - Ensures token hasn't been tampered with

2. **Expiration** (`exp`)
   - Required claim
   - Token must not be expired
   - Returns: `401 Unauthorized - Token has expired`

3. **Not Before** (`nbf`)
   - Token must be valid at current time
   - Returns: `401 Unauthorized - Token not yet valid`

4. **Issuer** (`iss`)
   - Must match expected Keycloak realm: `https://keycloak:8443/realms/flowpilot`
   - Returns: `401 Unauthorized - Invalid issuer`

5. **Audience** (`aud`)
   - Must include the expected client ID (default: `flowpilot-agent`)
   - Returns: `401 Unauthorized - Invalid audience`

6. **Issued At** (`iat`)
   - Required claim
   - Must not be in the future (allows 30s clock skew)

### Additional Best Practice Checks

1. **Token Type** (`typ`)
   - Should be `Bearer` for access tokens
   - Returns: `401 Unauthorized - Invalid token type`

2. **Token Age**
   - Token must not be older than 24 hours (from `iat`)
   - Security measure to limit exposure
   - Returns: `401 Unauthorized - Token too old`

3. **Clock Skew**
   - Allows up to 30 seconds for clock synchronization differences
   - Prevents false rejections due to minor time differences

## Configuration

### Environment Variables

```bash
# Authentication control
AUTH_ENABLED=true                    # Set to "false" to disable auth (dev only)

# Keycloak configuration
KEYCLOAK_URL=https://keycloak:8443  # Keycloak base URL
KEYCLOAK_REALM=flowpilot             # Realm name
KEYCLOAK_CLIENT_ID=flowpilot-agent   # Client ID (used for audience validation)

# Optional: Override audience validation
KEYCLOAK_AUDIENCE=my-custom-audience # Defaults to KEYCLOAK_CLIENT_ID

# JWKS caching
JWKS_CACHE_TTL=3600                  # Cache duration in seconds (default: 1 hour)
```

### Docker Compose Example

```yaml
services:
  flowpilot-authz-api:
    environment:
      - AUTH_ENABLED=true
      - KEYCLOAK_URL=https://keycloak:8443
      - KEYCLOAK_REALM=flowpilot
      - KEYCLOAK_CLIENT_ID=flowpilot-agent
      - JWKS_CACHE_TTL=3600
```

## Token Claims Available

After successful validation, the following claims are available from Keycloak tokens:

### Standard Claims

- `sub` - Subject identifier (user ID)
- `exp` - Expiration timestamp
- `iat` - Issued at timestamp  
- `nbf` - Not before timestamp (optional)
- `iss` - Issuer URL
- `aud` - Audience (array or string)
- `typ` - Token type (typically "Bearer")
- `azp` - Authorized party (client ID)
- `jti` - JWT ID (unique identifier)

### Keycloak-Specific Claims

- `preferred_username` - Username
- `email` - User email
- `email_verified` - Email verification status
- `realm_access.roles` - Realm-level roles
- `resource_access` - Client-level roles
- `scope` - OAuth scopes
- `session_state` - Session identifier
- `acr` - Authentication Context Class Reference

### FlowPilot Usage

Currently, FlowPilot uses only:
- `sub` - For user identification in `resolve_principal_sub()`
- `active` - Added by validator for compatibility (always true if validation passes)
- Full claims object passed to OPA policies (available but not currently used)

## Comparison: JWT Validation vs Introspection

| Aspect | JWT Validation (Current) | Token Introspection (Old) |
|--------|-------------------------|---------------------------|
| **Speed** | ~1-2ms | ~50-200ms |
| **Network Calls** | Only on key refresh (~1/hour) | Every request |
| **Scalability** | Excellent | Limited by Keycloak capacity |
| **Keycloak Load** | Minimal | High |
| **Offline** | Works with cached keys | Requires Keycloak |
| **Revocation Detection** | On key refresh only | Immediate |
| **Complexity** | Medium | Low |

## Security Considerations

### Key Rotation

When Keycloak rotates signing keys:
1. Old keys remain valid during transition period (passive state)
2. New tokens use new key
3. JWKS cache refreshes automatically
4. Both old and new tokens validate successfully during transition

### Token Revocation

⚠️ **Important**: Local JWT validation **does not detect immediate revocation**.

- Revoked tokens remain valid until they expire (`exp` claim)
- If immediate revocation is critical, consider:
  - Shorter token lifetimes (e.g., 5-15 minutes)
  - Hybrid approach: JWT validation + periodic introspection
  - Token revocation list (blocklist) implementation

For FlowPilot's use case (service-to-service auth with client credentials), this trade-off is acceptable because:
- Client credentials tokens are system-to-system
- No user logout scenario
- Compromised clients can be disabled in Keycloak (stops new token issuance)

### Clock Skew

The validator allows 30 seconds of clock skew for `iat` validation. This handles:
- Minor time synchronization differences
- Network latency
- Processing delays

If your environment has larger clock differences, consider:
- Setting up NTP synchronization
- Adjusting validation logic (not recommended)

## Troubleshooting

### Common Errors

**401 - Token has expired**
- Token `exp` claim is in the past
- Solution: Request new token from Keycloak

**401 - Invalid audience**
- Token `aud` doesn't match expected client ID
- Check: `KEYCLOAK_CLIENT_ID` environment variable
- Verify: Token was issued for the correct client

**401 - Invalid issuer**
- Token `iss` doesn't match expected Keycloak realm
- Check: `KEYCLOAK_URL` and `KEYCLOAK_REALM` environment variables
- Verify: Keycloak URL matches exactly (including protocol and port)

**401 - Invalid token signature**
- JWT signature verification failed
- Possible causes:
  - Token was modified/tampered
  - Token is from wrong Keycloak instance
  - JWKS cache issue (rare)
- Solution: Request new token

**503 - Failed to fetch signing keys**
- Cannot reach Keycloak's JWKS endpoint
- Check: Network connectivity to Keycloak
- Check: Keycloak is running and accessible
- Check: JWKS endpoint URL is correct

### Development Mode

For local development without Keycloak:

```bash
AUTH_ENABLED=false
```

This returns mock claims:
```python
{
    "active": True,
    "sub": "demo_user",
    "client_id": "demo"
}
```

⚠️ **Never use `AUTH_ENABLED=false` in production!**

## Performance Optimization

### JWKS Cache Tuning

Default cache TTL is 1 hour (3600 seconds). Adjust based on your needs:

**Longer cache (e.g., 6 hours):**
- Pros: Even better performance, less Keycloak load
- Cons: Slower key rotation detection
- Use when: Key rotation is infrequent

**Shorter cache (e.g., 5 minutes):**
- Pros: Faster key rotation detection
- Cons: More frequent JWKS fetches
- Use when: Key rotation is frequent or security is critical

```bash
JWKS_CACHE_TTL=21600  # 6 hours
```

### Monitoring

The `JWTValidator` tracks last successful validation:

```python
validator._last_validation  # Unix timestamp
```

Use this for:
- Health checks
- Alerting if validation stops
- Debugging authentication issues

## Migration Guide

If migrating from token introspection to JWT validation:

1. **No client changes required** - Same bearer token format
2. **Update environment variables** - Remove `KEYCLOAK_CLIENT_SECRET` (not needed)
3. **Rebuild services** - Pull new security.py with JWT validation
4. **Test authentication** - Verify tokens validate correctly
5. **Monitor performance** - Should see significant improvement

## References

- [RFC 7519 - JSON Web Token (JWT)](https://tools.ietf.org/html/rfc7519)
- [RFC 7517 - JSON Web Key (JWK)](https://tools.ietf.org/html/rfc7517)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OAuth 2.0 Bearer Token Usage](https://tools.ietf.org/html/rfc6750)
- [Keycloak Documentation](https://www.keycloak.org/documentation)
