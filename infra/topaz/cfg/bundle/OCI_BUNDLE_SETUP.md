# FlowPilot ***REMOVED*** OCI Policy Bundle Setup

This document describes how to create and configure an OCI-compliant policy bundle for ***REMOVED*** ABAC (Attribute-Based Access Control).

## Overview

***REMOVED*** uses OPA (Open Policy Agent) to load policy bundles from OCI registries. This setup ensures:
1. Valid OCI manifest with usable layers
2. Proper registry configuration (public or private)
3. TLS support for secure registries
4. Polling configuration for policy updates

## Prerequisites

- `policy` CLI installed (OPCR policy tool)
  ```bash
  brew tap opcr-io/tap && brew install opcr-io/tap/policy
  ```
- Docker for testing
- Access to an OCI-compliant registry (GHCR, Docker Hub, etc.)

## Building the OCI Policy Bundle

### Step 1: Prepare Policy Files

The bundle directory contains:
- `auto_book.rego` - OPA policy implementing auto-booking authorization
- `.manifest` - OPA bundle manifest (JSON with roots and rego_version)
- `data.json` - Optional data file

### Step 2: Build OCI Image

Build the policy bundle as an OCI image:

```bash
cd /Users/Me/Python/FlowPilot
policy build infra/***REMOVED***/cfg/bundle -t ghcr.io/flowpilot/policy:latest
```

This creates a valid OCI image with:
- Proper manifest structure
- Bundle layers that OPA can load
- OCI annotations for policy metadata

### Step 3: Verify the Image

Inspect the image to ensure it's valid:

```bash
policy inspect ghcr.io/flowpilot/policy:latest
```

Expected output:
```
media type: application/vnd.oci.image.manifest.v1+json
digest: sha256:...
size: ...

Annotations
  rego.version                      rego.V1
  org.opencontainers.image.created  2025-12-18T...
  org.opencontainers.image.title    ghcr.io/flowpilot/policy
  org.openpolicyregistry.type       policy
```

### Step 4: Push to Registry (Optional)

For public GHCR:
```bash
policy push ghcr.io/flowpilot/policy:latest
```

For private registry with authentication:
```bash
echo $GITHUB_TOKEN | policy login ghcr.io -u <username> --password-stdin
policy push ghcr.io/flowpilot/policy:latest
```

## Configuring ***REMOVED*** to Load the Bundle

### Configuration File

The ***REMOVED*** configuration (`infra/***REMOVED***/cfg/config.yaml`) includes:

```yaml
opa:
  instance_id: "-"
  graceful_shutdown_period_seconds: 2
  config:
    services:
      ghcr:
        url: https://ghcr.io
        type: oci
    bundles:
      flowpilot:
        service: ghcr
        resource: ghcr.io/flowpilot/policy:latest
        persist: false
        polling:
          min_delay_seconds: 60
          max_delay_seconds: 120
```

### For Private Registries

Add credentials to the service configuration:

```yaml
services:
  ghcr:
    url: https://ghcr.io
    type: oci
    credentials:
      bearer:
        token: "${GITHUB_TOKEN}"
```

Pass the token via environment variable in `docker-compose.yml`:

```yaml
***REMOVED***:
  environment:
    GITHUB_TOKEN: ${GITHUB_TOKEN}
```

### For Self-Signed Certificates

Add TLS configuration:

```yaml
services:
  ghcr:
    url: https://your-registry.com
    type: oci
    tls:
      ca_cert: /certs/ca.pem
      system_ca_required: false
```

Mount the CA certificate in `docker-compose.yml`:

```yaml
***REMOVED***:
  volumes:
    - ./infra/***REMOVED***/certs:/certs:ro
```

## TLS Certificate Setup

Self-signed TLS certificates have been generated for ***REMOVED***:

```bash
openssl req -x509 -newkey rsa:4096 \
  -keyout infra/***REMOVED***/certs/key.pem \
  -out infra/***REMOVED***/certs/cert.pem \
  -days 365 -nodes \
  -subj "/CN=***REMOVED***/O=FlowPilot/C=US"
```

Certificates are located at:
- `infra/***REMOVED***/certs/cert.pem` - Public certificate
- `infra/***REMOVED***/certs/key.pem` - Private key

These certificates are mounted in the ***REMOVED*** container via docker-compose.

## Testing the Setup

### 1. Start ***REMOVED***

```bash
docker compose up -d ***REMOVED***
```

### 2. Check Logs for Bundle Loading

```bash
docker compose logs ***REMOVED*** | grep -i bundle
```

Expected output:
```
{"level":"info","name":"flowpilot","plugin":"bundle","message":"Bundle loaded and activated successfully."}
```

### 3. Query the Policy

Test the policy via the Authorizer API:

```bash
curl -X POST http://localhost:9393/api/v2/authz/is \
  -H "Content-Type: application/json" \
  -d '{
    "policy_context": {
      "path": "auto_book",
      "decisions": ["allow", "reason"]
    },
    "resource_context": {
      "user": {
        "auto_book_consent": true,
        "auto_book_max_cost_eur": 1000,
        "auto_book_min_days_advance": 7,
        "auto_book_max_airline_risk": 5
      },
      "resource": {
        "planned_price": 800,
        "departure_date": "2025-12-30",
        "airline_risk_score": 3
      }
    }
  }'
```

Expected response:
```json
{
  "decisions": [
    {
      "decision": "allow",
      "is": true
    },
    {
      "decision": "reason",
      "is": "auto_book.unknown_error"
    }
  ]
}
```

## Troubleshooting

### Issue: "No layers in manifest"

**Cause**: The OCI image was not built properly with the policy CLI.

**Solution**: Always use `policy build` rather than `docker build`:
```bash
policy build infra/***REMOVED***/cfg/bundle -t ghcr.io/flowpilot/policy:latest
```

### Issue: Registry authentication failure

**Cause**: Missing or incorrect credentials.

**Solution**: 
1. Verify credentials are correct
2. Ensure environment variables are passed to Docker
3. For GHCR, create a Personal Access Token with `read:packages` scope

### Issue: TLS certificate errors

**Cause**: Self-signed certificates not trusted or misconfigured.

**Solution**:
1. Ensure certificates are mounted correctly
2. Add `system_ca_required: false` for self-signed certs
3. Verify CA cert path matches mounted volume path

### Issue: Policy not evaluating

**Cause**: Bundle loaded but policy path incorrect.

**Solution**: 
1. Check `.manifest` file has correct roots: `["auto_book"]`
2. Verify policy path in query matches package name in .rego file
3. Use `policy_context.path` = `"auto_book"` in API calls

## References

- [***REMOVED*** Documentation](https://www.***REMOVED***.sh/)
- [OPA Bundle Format](https://www.openpolicyagent.org/docs/latest/management-bundles/)
- [OPCR Policy CLI](https://github.com/opcr-io/policy)
- [OCI Image Spec](https://github.com/opencontainers/image-spec)
- [FlowPilot Auto-Book Policy](../../../docs/AUTO_BOOK_POLICY.md)

## Generated Files

- `ghcr.io/flowpilot/policy:latest` - OCI policy image (in local Docker)
- `config.yaml` - Updated ***REMOVED*** configuration with OCI bundle loading
- `infra/***REMOVED***/certs/cert.pem` - TLS certificate
- `infra/***REMOVED***/certs/key.pem` - TLS private key
