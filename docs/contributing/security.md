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

When deploying FlowPilot in production:

**API endpoints**

- Review sanitzation rules regularly
- Ensure application-level validation of JWT access tokens at all endpoints

**Authentication & Authorization**

- All API endpoints MUST require valid bearer tokens
- Use production-grade secrets (not demo credentials)
- Rotate credentials regularly
- Implement proper token validation and expiry

**Transport Security**

- MUST use TLS 1.2 or higher for all services
- Use valid, public certificates
- Configure proper cipher suites
- Enable HSTS (HTTP Strict Transport Security)

**Network Security**

- Deploy services behind a firewall
- Use network segmentation
- Limit service exposure (only expose necessary endpoints)
- Configure rate limiting

**Secrets Management**

- Never commit secrets to version control
- Use environment variables or secret management systems
- Rotate IdP admin credentials immediately
- Generate new client secrets for all OIDC clients

**Database Security**

- Encrypt data at rest
- Regular backups with encryption
- Limit database access to only necessary services

**Container Security**

- Use minimal base images
- Scan images for vulnerabilities
- Run containers as non-root users
- Keep dependencies updated
- Use container registry scanning

**Privacy & Compliance**

- The authorization model is designed with privacy-by-design principles
- Do not requests scopes such as 'profile' for the access token
- Do not expose PII to the back-end ai-agent and domain-services APIs 
- Do not store PII with domain-services data

## Security Features

FlowPilot implements several security best practices:

**Authorization Architecture**

- Centralized policy decision point (PDP)
- Policy enforcement points (PEP) at domain service boundaries
- Relationship-based access control (ReBAC) for delegation
- Explicit authorization checks for every operation

**Authentication**

- OIDC with PKCE for desktop client
- Bearer token authentication for service-to-service communication
- Keycloak as identity provider with realm isolation

**Privacy by Design**

- No PII exposed to AI/LLM components
- Principal identity uses opaque identifiers (sub)
- Profile information separated from domain data
- Progressive profiling without storing sensitive data

**Auditability**

- All authorization decisions are logged
- Per-item execution results with reasons
- Delegation chains are explicit and verifiable

## Dependencies

We recommend:
- Regularly updating dependencies
- Monitoring security advisories for:
  - Python packages (imported libraries are documented in requirements.txt)
  - Docker base images

## Security Contacts

For security-related questions or concerns:
- Email: ciso@nura.pro
- Response time: Within 48 hours

---

Last updated: 2026-01-15
