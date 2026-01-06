# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |

## Reporting a Vulnerability

We take the security of FlowPilot seriously. If you discover a security vulnerability, please follow these steps:

### How to Report

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to: ciso@nura.pro

Include the following information:
- Type of vulnerability
- Full paths of source file(s) related to the vulnerability
- Location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if available)
- Impact assessment (what an attacker could do)

### Response Timeline

- **Initial Response**: Within 48 hours of report
- **Status Update**: Within 7 days with assessment and timeline
- **Resolution**: Security fixes will be prioritized based on severity

### Disclosure Policy

- We follow responsible disclosure practices
- We will work with you to understand and resolve the issue
- We will credit you in the security advisory (unless you prefer to remain anonymous)
- We request that you do not publicly disclose the vulnerability until we have released a fix

## Security Best Practices

### Production Deployment

When deploying FlowPilot in production:

1. **Authentication & Authorization**
   - All API endpoints MUST require valid bearer tokens
   - Use production-grade secrets (not demo credentials)
   - Rotate credentials regularly
   - Implement proper token validation and expiry

2. **Transport Security**
   - MUST use TLS 1.2 or higher for all services
   - Use valid, non-self-signed certificates
   - Configure proper cipher suites
   - Enable HSTS (HTTP Strict Transport Security)

3. **Network Security**
   - Deploy services behind a firewall
   - Use network segmentation
   - Limit service exposure (only expose necessary endpoints)
   - Configure rate limiting

4. **Secrets Management**
   - Never commit secrets to version control
   - Use environment variables or secret management systems
   - Rotate Keycloak admin credentials immediately
   - Generate new client secrets for all OIDC clients
   - Update ***REMOVED*** configuration with production-grade settings

5. **Database Security**
   - Use strong authentication for ***REMOVED*** directory DB
   - Encrypt data at rest
   - Regular backups with encryption
   - Limit database access to only necessary services

6. **Container Security**
   - Use minimal base images
   - Scan images for vulnerabilities
   - Run containers as non-root users
   - Keep dependencies updated
   - Use container registry scanning

7. **Privacy & Compliance**
   - FlowPilot is designed with privacy-by-design principles
   - No PII is exposed to LLMs
   - Profile information is stored separately from domain data
   - Ensure GDPR/privacy compliance for your jurisdiction

### Demo/Development Environment Warnings

**The default configuration requires additional hardening for production:**

- Self-signed certificates are used (replace with CA-signed certs)
- Default credentials (admin/admin for Keycloak - must be changed)
- Default client secret in docker-compose (must be regenerated)
- No rate limiting configured
- Services exposed on localhost

**Authentication is ENABLED by default.

## Known Limitations

- Demo setup uses self-signed TLS certificates for Keycloak
- Default Keycloak realm includes test users with simple passwords
- No rate limiting configured by default  
- Services communicate over HTTP internally in Docker network (TLS termination at ingress recommended)
- Client secret visible in docker-compose.yml (use secrets management in production)

## Security Features

FlowPilot implements several security best practices:

1. **Authorization Architecture**
   - Centralized policy decision point (PDP) with ***REMOVED***
   - Policy enforcement points (PEP) at domain service boundaries
   - Relationship-based access control (ReBAC) for delegation
   - Explicit authorization checks for every operation

2. **Authentication**
   - OIDC with PKCE for desktop client
   - Bearer token authentication for service-to-service communication
   - Keycloak as identity provider with realm isolation

3. **Privacy by Design**
   - No PII exposed to AI/LLM components
   - Principal identity uses opaque identifiers (sub)
   - Profile information separated from domain data
   - Progressive profiling without storing sensitive data

4. **Auditability**
   - All authorization decisions are logged
   - Per-item execution results with reasons
   - Delegation chains are explicit and verifiable

## Dependencies

We recommend:
- Regularly updating dependencies
- Monitoring security advisories for:
  - Python packages (requirements.txt)
  - Docker base images
  - Keycloak
  - ***REMOVED***
  - Swift dependencies

## Security Contacts

For security-related questions or concerns:
- Email: ciso@nura.pro
- Response time: Within 48 hours

---

Last updated: 2025-12-20
