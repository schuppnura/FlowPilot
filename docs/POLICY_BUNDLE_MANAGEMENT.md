# FlowPilot Policy Bundle Management

This document describes how to manage OCI-compliant policy bundles for ***REMOVED*** ABAC (Attribute-Based Access Control) in FlowPilot.

## Overview

FlowPilot uses OPA (Open Policy Agent) policy bundles distributed as OCI images served over HTTPS with TLS. This approach ensures:

- **OCI Compliance**: Policy bundles follow OCI image specification with valid manifests and layers
- **Secure Distribution**: Bundles are served over HTTPS with TLS encryption
- **Version Control**: Policy changes are tracked alongside code in Git
- **Automatic Loading**: ***REMOVED*** fetches and activates policy bundles automatically

## Architecture

```
┌─────────────────────┐
│  Policy Bundle      │
│  (auto_book.rego)   │
└──────────┬──────────┘
           │
           ↓
    policy build
           │
           ↓
┌─────────────────────┐
│  OCI Image          │
│  (localhost/...)    │
└──────────┬──────────┘
           │
    policy save
           │
           ↓
┌─────────────────────┐
│  Bundle Tarball     │
│  (*.tar.gz)         │
└──────────┬──────────┘
           │
           ↓
┌─────────────────────┐
│  HTTPS Server       │
│  (TLS enabled)      │
└──────────┬──────────┘
           │
      HTTPS GET
           │
           ↓
┌─────────────────────┐
│  ***REMOVED*** OPA Runtime  │
│  (evaluates policy) │
└─────────────────────┘
```

## Components

### 1. Policy Files (`infra/***REMOVED***/cfg/bundle/`)

- **`auto_book.rego`**: OPA policy implementing auto-booking authorization rules
- **`.manifest`**: OPA bundle manifest (JSON) defining policy roots and rego version
- **`data.json`**: Optional static data for policy evaluation
- **`README.md`**: Policy documentation

### 2. HTTPS Bundle Server (`infra/***REMOVED***/cfg/https_bundle_server.py`)

- Python-based HTTPS server with TLS
- Serves policy bundles to ***REMOVED***
- Uses self-signed certificates from `infra/***REMOVED***/certs/`
- Runs on port 8888

### 3. TLS Certificates (`infra/***REMOVED***/certs/`)

- **`cert.pem`**: Self-signed public certificate (tracked in Git)
- **`key.pem`**: Private key (tracked in Git for development)
- Valid for 365 days
- **Production**: Replace with proper CA-signed certificates

### 4. ***REMOVED*** Configuration (`infra/***REMOVED***/cfg/config.yaml`)

OPA section configured to fetch bundles via HTTPS:

```yaml
opa:
  config:
    services:
      bundle_server:
        url: https://host.docker.internal:8888
        tls:
          system_ca_required: false
    bundles:
      flowpilot:
        service: bundle_server
        resource: bundle/flowpilot-policy.tar.gz
        persist: false
```

## Workflow

### Building Policy Bundles

```bash
# Using the policy CLI (recommended)
policy build infra/***REMOVED***/cfg/bundle -t localhost/flowpilot-policy:latest
policy save localhost/flowpilot-policy:latest -f infra/***REMOVED***/cfg/bundle/flowpilot-policy.tar.gz

# Or use the management script
./bin/bundle-server.sh rebuild
```

### Managing the HTTPS Server

```bash
# Start the server
./bin/bundle-server.sh start

# Check status
./bin/bundle-server.sh status

# Stop the server
./bin/bundle-server.sh stop

# Restart the server
./bin/bundle-server.sh restart
```

### Updating Policies

1. **Edit the policy file**:
   ```bash
   vim infra/***REMOVED***/cfg/bundle/auto_book.rego
   ```

2. **Rebuild the bundle**:
   ```bash
   ./bin/bundle-server.sh rebuild
   ```

3. *****REMOVED*** auto-fetches** the updated bundle (or restart ***REMOVED***):
   ```bash
   docker compose restart ***REMOVED***
   ```

4. **Verify the update**:
   ```bash
   docker compose logs ***REMOVED*** | grep bundle
   ```

## Policy Development Workflow

### 1. Local Testing

Test policy logic directly with OPA:

```bash
# Install OPA CLI
brew install opa

# Test policy with sample input
opa eval -d infra/***REMOVED***/cfg/bundle/auto_book.rego \
  -i test_input.json \
  'data.auto_book.allow'
```

### 2. Policy Validation

```bash
# Check Rego syntax
opa check infra/***REMOVED***/cfg/bundle/auto_book.rego

# Run policy tests (if you have test files)
opa test infra/***REMOVED***/cfg/bundle/
```

### 3. Integration Testing

After rebuilding and restarting:

```bash
# Test via AuthZ API
curl -X POST http://localhost:8002/v1/is \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d @test_authz_request.json
```

## Troubleshooting

### Bundle Not Loading

**Symptom**: ***REMOVED*** logs show fetch errors

**Check**:
```bash
# 1. Verify HTTPS server is running
./bin/bundle-server.sh status

# 2. Test bundle accessibility
curl -k https://localhost:8888/bundle/flowpilot-policy.tar.gz

# 3. Check ***REMOVED*** logs
docker compose logs ***REMOVED*** | grep -i bundle
```

**Solution**:
```bash
# Restart HTTPS server
./bin/bundle-server.sh restart

# Restart ***REMOVED***
docker compose restart ***REMOVED***
```

### Policy Not Evaluating

**Symptom**: Empty decisions array or errors in ***REMOVED*** logs

**Check**:
```bash
# 1. Verify bundle manifest
cat infra/***REMOVED***/cfg/bundle/.manifest
# Should show: {"roots":["auto_book"],...}

# 2. Verify policy package matches manifest roots
head -1 infra/***REMOVED***/cfg/bundle/auto_book.rego
# Should show: package auto_book

# 3. Check ***REMOVED*** OPA status
docker compose logs ***REMOVED*** | tail -50
```

**Solution**:
- Ensure package name in `.rego` file matches roots in `.manifest`
- Rebuild bundle if manifest was changed
- Verify policy path in API calls matches package name

### TLS Certificate Errors

**Symptom**: curl fails with SSL errors

**Check**:
```bash
# Verify certificates exist
ls -la infra/***REMOVED***/certs/

# Test with insecure flag
curl -k https://localhost:8888/bundle/flowpilot-policy.tar.gz
```

**Solution**:
```bash
# Regenerate certificates
openssl req -x509 -newkey rsa:4096 \
  -keyout infra/***REMOVED***/certs/key.pem \
  -out infra/***REMOVED***/certs/cert.pem \
  -days 365 -nodes \
  -subj "/CN=***REMOVED***/O=FlowPilot/C=US"

# Restart HTTPS server
./bin/bundle-server.sh restart
```

### Bundle Build Failures

**Symptom**: `policy build` command fails

**Check**:
```bash
# Verify policy CLI is installed
policy version

# Check for syntax errors in Rego
opa check infra/***REMOVED***/cfg/bundle/*.rego
```

**Solution**:
```bash
# Install policy CLI if missing
brew tap opcr-io/tap
brew install opcr-io/tap/policy

# Fix Rego syntax errors
# Then rebuild
./bin/bundle-server.sh rebuild
```

## Production Considerations

### TLS Certificates

For production, replace self-signed certificates with proper CA-signed certificates:

1. **Obtain certificates** from Let's Encrypt, DigiCert, etc.
2. **Place certificates** in `infra/***REMOVED***/certs/`
3. **Update ***REMOVED*** config** to enable system CA validation:
   ```yaml
   tls:
     system_ca_required: true
   ```

### Bundle Distribution

For production environments, consider:

- **OCI Registry**: Push bundles to a proper OCI registry (GHCR, Docker Hub, Harbor)
- **CDN**: Use a CDN for global distribution
- **Versioning**: Tag bundles with semantic versions
- **Signing**: Sign bundles for verification

Example with GHCR:
```bash
# Login to GHCR
echo $GITHUB_TOKEN | policy login ghcr.io -u username --password-stdin

# Build and push
policy build infra/***REMOVED***/cfg/bundle -t ghcr.io/org/flowpilot-policy:v1.0.0
policy push ghcr.io/org/flowpilot-policy:v1.0.0

# Update ***REMOVED*** config
# services:
#   ghcr:
#     url: https://ghcr.io
#     type: oci
#     credentials:
#       bearer:
#         token: "${GITHUB_TOKEN}"
# bundles:
#   flowpilot:
#     service: ghcr
#     resource: ghcr.io/org/flowpilot-policy:v1.0.0
```

### Monitoring

Monitor policy bundle health:

```bash
# Bundle fetch metrics
docker compose logs ***REMOVED*** | grep -i bundle

# Policy evaluation metrics
docker compose logs ***REMOVED*** | grep -i "auto_book"

# HTTPS server access logs
tail -f /tmp/https-bundle-server.log
```

## References

- [OCI Bundle Setup Guide](../infra/***REMOVED***/cfg/bundle/OCI_BUNDLE_SETUP.md)
- [Auto-Book Policy Documentation](AUTO_BOOK_POLICY.md)
- [***REMOVED*** Documentation](https://www.***REMOVED***.sh/)
- [OPA Bundle Format](https://www.openpolicyagent.org/docs/latest/management-bundles/)
- [OPCR Policy CLI](https://github.com/opcr-io/policy)

## Quick Reference

### Common Commands

```bash
# Build bundle
./bin/bundle-server.sh rebuild

# Restart HTTPS server
./bin/bundle-server.sh restart

# Check server status
./bin/bundle-server.sh status

# Restart ***REMOVED***
docker compose restart ***REMOVED***

# View ***REMOVED*** logs
docker compose logs -f ***REMOVED***

# Test bundle fetch
curl -k https://localhost:8888/bundle/flowpilot-policy.tar.gz

# Validate Rego syntax
opa check infra/***REMOVED***/cfg/bundle/*.rego
```

### File Locations

- **Policy files**: `infra/***REMOVED***/cfg/bundle/`
- **HTTPS server**: `infra/***REMOVED***/cfg/https_bundle_server.py`
- **Certificates**: `infra/***REMOVED***/certs/`
- *****REMOVED*** config**: `infra/***REMOVED***/cfg/config.yaml`
- **Server logs**: `/tmp/https-bundle-server.log`
- **Management script**: `bin/bundle-server.sh`
