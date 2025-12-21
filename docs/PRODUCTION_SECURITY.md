# Production Security Guide

This document outlines the critical security fixes and how to deploy FlowPilot securely.

## Critical Security Issues Fixed

### 1. ✅ Removed Hardcoded Client Secret
**Previous:** Client secret had a hardcoded fallback in code
**Now:** Service fails to start if `KEYCLOAK_CLIENT_SECRET` is not set when `AUTH_ENABLED=true`

### 2. ✅ Production Keycloak Configuration
**Previous:** Keycloak ran in development mode (`start-dev`)
**Now:** Production compose file uses `start` with optimized settings

### 3. ✅ SSL Verification Configurable
**Previous:** SSL verification was hardcoded to `false`
**Now:** Controlled via `KEYCLOAK_VERIFY_SSL` environment variable

### 4. ✅ Service Port Exposure Options
**Previous:** All services exposed to host machine
**Now:** Production/secure configs limit exposure

## Deployment Modes

### Development Mode (Current Default)
```bash
docker compose up -d
```
- Keycloak in development mode
- SSL verification disabled (self-signed certs)
- All service ports exposed for debugging
- ⚠️ **NOT for production**

### Secure Development Mode
```bash
docker compose -f docker-compose.yml -f docker-compose.secure.yml up -d
```
- Internal services not exposed to host
- Only Keycloak accessible
- Better isolation while developing

### Production Mode
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```
- Keycloak in production mode with security headers
- SSL verification enabled (requires proper certificates)
- Minimal port exposure
- Optimized performance

## Pre-Production Checklist

### 1. Generate Production Secrets
```bash
# Generate strong client secret
openssl rand -hex 32

# Update .env file
KEYCLOAK_ADMIN_PASSWORD=<strong-password>
KEYCLOAK_CLIENT_SECRET=<generated-secret>
```

### 2. Obtain Valid SSL Certificates
Replace self-signed certificates in `infra/keycloak/certs/` with CA-signed certificates:
```bash
# Example with Let's Encrypt
certbot certonly --standalone -d your-domain.com

# Copy to Keycloak certs directory
cp /etc/letsencrypt/live/your-domain.com/fullchain.pem infra/keycloak/certs/cert.pem
cp /etc/letsencrypt/live/your-domain.com/privkey.pem infra/keycloak/certs/key.pem
```

### 3. Enable SSL Verification
Update `.env`:
```bash
KEYCLOAK_VERIFY_SSL=true
```

### 4. Update Keycloak Hostname
Update `docker-compose.yml` or use environment variable:
```yaml
KC_HOSTNAME: https://your-domain.com:8443
```

### 5. Configure Reverse Proxy
Use Nginx or Traefik to:
- Terminate TLS
- Rate limit requests
- Forward to internal services
- Add security headers

Example Nginx config:
```nginx
server {
    listen 443 ssl http2;
    server_name api.your-domain.com;
    
    # SSL configuration
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    
    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req zone=api_limit burst=20 nodelay;
    
    # Proxy to services
    location /v1/authz/ {
        proxy_pass http://flowpilot-authz-api:8002/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location /v1/services/ {
        proxy_pass http://flowpilot-domain-services-api:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 6. Network Segmentation
Use Docker networks to isolate services:
```yaml
networks:
  frontend:
    # External-facing services only
  backend:
    internal: true  # No external access
```

### 7. Enable Monitoring
- Set up log aggregation (ELK, Splunk, etc.)
- Monitor authentication failures
- Alert on unusual API usage patterns
- Track authorization denials

## Security Testing

Before going live:

1. **Verify no hardcoded secrets:**
   ```bash
   git grep -i "password\|secret" | grep -v ".env\|.example\|.md"
   ```

2. **Test SSL verification:**
   ```bash
   # Should fail with invalid cert
   curl https://localhost:8443/health
   
   # Should work with proper cert
   curl --cacert /path/to/ca.pem https://your-domain.com:8443/health
   ```

3. **Verify authentication required:**
   ```bash
   # Should return 401/403
   curl http://localhost:8002/v1/profiles/test
   ```

4. **Test rate limiting:**
   ```bash
   # Send rapid requests, should get 429
   for i in {1..100}; do curl http://localhost:8000/api/endpoint; done
   ```

5. **Scan for vulnerabilities:**
   ```bash
   # Use security scanners
   docker scan flowpilot-flowpilot-domain-services-api
   trivy image flowpilot-flowpilot-domain-services-api
   ```

## Environment Variables Reference

| Variable | Development | Production | Required |
|----------|------------|------------|----------|
| `KEYCLOAK_ADMIN_PASSWORD` | `admin` | Strong password | Yes |
| `KEYCLOAK_CLIENT_SECRET` | Generated | Strong random | Yes |
| `KEYCLOAK_VERIFY_SSL` | `false` | `true` | Yes |
| `AUTH_ENABLED` | `true` | `true` | Yes |
| `KC_HOSTNAME` | `localhost:8443` | Your domain | Yes |

## Incident Response

If credentials are compromised:

1. **Immediately rotate secrets:**
   ```bash
   # Generate new secret
   NEW_SECRET=$(openssl rand -hex 32)
   
   # Update .env
   echo "KEYCLOAK_CLIENT_SECRET=$NEW_SECRET" >> .env
   
   # Regenerate Keycloak realm config
   ./scripts/generate-realm-config.sh
   
   # Restart services
   docker compose down && docker compose up -d
   ```

2. **Invalidate all tokens in Keycloak admin console**

3. **Review access logs for unauthorized access**

4. **Update credentials in all dependent systems**

## Support

- Security issues: See [SECURITY.md](../SECURITY.md)
- Questions: Open a GitHub issue
- Urgent security matters: Follow responsible disclosure in SECURITY.md
