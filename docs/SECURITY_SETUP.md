# Security Setup Guide

This guide explains how to enable authentication and TLS for FlowPilot services.

## Overview

By default, FlowPilot runs in **secure mode** with:
- ✅ Bearer token authentication ENABLED on all APIs (except /health)
- ✅ TLS for Keycloak (self-signed certificates for demo)
- ⚠️ HTTP between internal Docker services (add TLS for production)
- ⚠️ Default credentials (must change for production)

For production deployment, follow this guide for additional hardening.

### Disabling Authentication (Development Only)

To disable authentication for local development/testing:

```yaml
environment:
  AUTH_ENABLED: "false"
```

**Warning**: Only disable authentication in secure, isolated development environments.

## Bearer Token Authentication

### Current State

Authentication is **ENABLED by default** with these settings:

```yaml
environment:
  # Authentication enabled by default
  AUTH_ENABLED: "true"
  
  # Keycloak configuration
  KEYCLOAK_URL: "https://keycloak:8443"
  KEYCLOAK_REALM: "flowpilot"
  KEYCLOAK_CLIENT_ID: "flowpilot-agent"
  KEYCLOAK_CLIENT_SECRET: "YOUR_CLIENT_SECRET_HERE"
  KEYCLOAK_VERIFY_SSL: "false"  # Set to "true" with proper certs
```

### Step 2: Generate New Client Secret

1. Access Keycloak admin console: https://localhost:8443
2. Login with admin credentials
3. Navigate to: Realm Settings → Clients → flowpilot-agent
4. Go to Credentials tab
5. Click "Regenerate Secret"
6. Copy the new secret to your environment variables

### Step 3: Restart Services

```bash
docker compose down
docker compose up -d --build
```

### Step 4: Test Authentication

Without token (should fail):
```bash
curl http://localhost:8002/v1/profiles/test-user
# Expected: 401 Unauthorized
```

With token:
```bash
# First, get a token from Keycloak
TOKEN=$(curl -k -X POST https://localhost:8443/realms/flowpilot/protocol/openid-connect/token \
  -d "client_id=flowpilot-agent" \
  -d "client_secret=YOUR_SECRET" \
  -d "grant_type=client_credentials" \
  | jq -r '.access_token')

# Then use it
curl -H "Authorization: Bearer $TOKEN" http://localhost:8002/v1/profiles/test-user
# Expected: 200 OK
```

## Enabling TLS for Services

### Current State

Keycloak already uses TLS with self-signed certificates. The Python services currently use HTTP.

### Step 1: Generate Certificates

```bash
# Create certs directory
mkdir -p infra/certs

# Generate self-signed certificate (for testing)
openssl req -x509 -newkey rsa:4096 -nodes \
  -out infra/certs/server.crt \
  -keyout infra/certs/server.key \
  -days 365 \
  -subj "/CN=localhost"

# For production, use proper CA-signed certificates
```

### Step 2: Update docker-compose.yml

Add TLS configuration to each service:

```yaml
services:
  flowpilot-authz-api:
    # ... existing config ...
    volumes:
      - ./infra/certs:/certs:ro
    environment:
      SSL_CERT_FILE: /certs/server.crt
      SSL_KEY_FILE: /certs/server.key
    command: >
      uvicorn main:app 
      --host 0.0.0.0 
      --port 8002 
      --ssl-keyfile /certs/server.key 
      --ssl-certfile /certs/server.crt
```

### Step 3: Update Service URLs

Update all service references from `http://` to `https://`:

```yaml
environment:
  WORKFLOW_BASE_URL: "https://flowpilot-api:8003"
  AUTHZ_BASE_URL: "https://flowpilot-authz-api:8002"
  KEYCLOAK_VERIFY_SSL: "true"  # Once using proper certs
```

## Service-to-Service Authentication

For service-to-service calls, services should use the `flowpilot-agent` client credentials.

### Example: AuthZ API calling Services API

The services already have the agent client configured. When AUTH_ENABLED=true, they will:

1. Request a token from Keycloak using client credentials
2. Include the token in outbound requests
3. Cache the token until near expiry
4. Automatically refresh when needed

This is handled by the shared authentication utilities.

## Desktop App Configuration

The desktop app uses OIDC with PKCE and doesn't need the client secret. It already uses TLS for Keycloak.

No changes needed for the desktop app when enabling API authentication - it only talks to Keycloak directly.

## Network Security (Production)

For production deployment:

### 1. Use a Reverse Proxy

```
Internet → Nginx/Traefik → Services (internal network)
```

### 2. Configure Firewall Rules

```bash
# Only expose necessary ports
# - 443 (HTTPS API gateway)
# - Block direct access to: 8002, 8003, 8004, 9393
```

### 3. Use Docker Networks

```yaml
networks:
  frontend:
    # External-facing services
  backend:
    # Internal services only
    internal: true
```

### 4. Enable Rate Limiting

Add to your reverse proxy or API gateway:
- Per-IP rate limits
- Per-token rate limits
- DDoS protection

## Monitoring & Auditing

### Enable Access Logging

```yaml
environment:
  LOG_LEVEL: "info"  # or "debug" for more detail
  ACCESS_LOG: "true"
```

### Track Authorization Decisions

All authorization decisions are logged by the AuthZ service. Enable structured logging for security monitoring:

```python
# In production, integrate with your SIEM/log aggregation
```

## Security Checklist

Before going to production:

- [ ] Generate new Keycloak admin password
- [ ] Regenerate all client secrets
- [ ] Use CA-signed TLS certificates (not self-signed)
- [ ] Enable AUTH_ENABLED=true
- [ ] Configure proper network segmentation
- [ ] Set up rate limiting
- [ ] Enable access logging
- [ ] Configure log aggregation/SIEM
- [ ] Set up automated certificate renewal
- [ ] Document incident response procedures
- [ ] Perform security testing/penetration testing
- [ ] Review and update SECURITY.md

## Troubleshooting

### "Token validation service unavailable"

- Check Keycloak is running: `docker ps | grep keycloak`
- Verify KEYCLOAK_URL is correct
- Check network connectivity between services

### "Invalid or expired token"

- Tokens expire after ~5 minutes by default
- Request a new token
- For service accounts, implement automatic token refresh

### TLS Certificate Errors

- With self-signed certs, set `KEYCLOAK_VERIFY_SSL=false`
- For production, use proper CA-signed certificates
- Ensure certificate CN/SAN matches the hostname

## Further Reading

- [SECURITY.md](../SECURITY.md) - Full security policy
- [Keycloak Documentation](https://www.keycloak.org/documentation)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [OWASP API Security](https://owasp.org/www-project-api-security/)
