# CORS Configuration

FlowPilot services support Cross-Origin Resource Sharing (CORS) to enable web applications running in browsers to access the APIs.

## Overview

CORS is required when your web application's frontend (e.g., running on `https://app.example.com`) needs to make requests to FlowPilot APIs (running on different domains like `https://flowpilot-domain-services-api-*.run.app`).

All five FlowPilot services include CORS middleware:
- **authz-api** (port 8002 local, GCP Cloud Run)
- **domain-services-api** (port 8003 local, GCP Cloud Run)
- **delegation-api** (port 8005 local, GCP Cloud Run)
- **persona-api** (port 8006 local, GCP Cloud Run)
- **ai-agent-api** (port 8004 local, GCP Cloud Run)

## Configuration

CORS behavior is controlled via environment variables in the shared `security.py` library:

### Environment Variables

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `CORS_ALLOWED_ORIGINS` | Comma-separated list of allowed origins, or `*` for all | `*` | `https://app.example.com,https://admin.example.com` |
| `CORS_ALLOW_CREDENTIALS` | Allow credentials (cookies, auth headers) | `true` | `true` or `false` |
| `CORS_ALLOW_METHODS` | Allowed HTTP methods, or `*` for all | `*` | `GET,POST,PUT,DELETE` |
| `CORS_ALLOW_HEADERS` | Allowed headers, or `*` for all | `*` | `Authorization,Content-Type` |

## Local Development (Docker Compose)

All services are configured with permissive CORS settings in `docker-compose.yml`:

```yaml
environment:
  - CORS_ALLOWED_ORIGINS=*
  - CORS_ALLOW_CREDENTIALS=true
  - CORS_ALLOW_METHODS=*
  - CORS_ALLOW_HEADERS=*
```

This allows any web application running on localhost (e.g., `http://localhost:3000`, `http://localhost:5173`) to access the APIs during development.

## Production (GCP Cloud Run)

CORS settings for production are defined in `cloud-run-envs/*.yaml` files:

- `cloud-run-envs/authz-api.yaml`
- `cloud-run-envs/domain-services-api.yaml`
- `cloud-run-envs/delegation-api.yaml`
- `cloud-run-envs/persona-api.yaml`
- `cloud-run-envs/ai-agent-api.yaml`

### Default Production Settings

Currently configured with permissive settings for development/testing:

```yaml
CORS_ALLOWED_ORIGINS: "*"
CORS_ALLOW_CREDENTIALS: "true"
CORS_ALLOW_METHODS: "*"
CORS_ALLOW_HEADERS: "*"
```

### Recommended Production Settings

For production deployments, **restrict origins to your actual web application domains**:

```yaml
# Example: Production CORS configuration
CORS_ALLOWED_ORIGINS: "https://app.example.com,https://admin.example.com"
CORS_ALLOW_CREDENTIALS: "true"
CORS_ALLOW_METHODS: "GET,POST,PUT,DELETE"
CORS_ALLOW_HEADERS: "Authorization,Content-Type,X-Request-ID"
```

## Security Considerations

### Development vs. Production

**Development:**
- Using `CORS_ALLOWED_ORIGINS=*` is acceptable for local development
- Simplifies testing with various frontend frameworks and ports

**Production:**
- **Never use `*` in production** - this allows any website to access your APIs
- Specify exact origins (protocol + domain + port if non-standard)
- Use HTTPS origins only (except localhost for development)

### Credentials and Wildcard Origins

**Important:** When `CORS_ALLOW_CREDENTIALS=true`, you **cannot** use `CORS_ALLOWED_ORIGINS=*` according to the CORS specification. Browsers will reject such requests.

If you need credentials (JWT tokens in `Authorization` header), you **must** specify exact origins:

```yaml
# ✅ Correct: specific origins with credentials
CORS_ALLOWED_ORIGINS: "https://app.example.com"
CORS_ALLOW_CREDENTIALS: "true"

# ❌ Incorrect: wildcard with credentials (browsers reject)
CORS_ALLOWED_ORIGINS: "*"
CORS_ALLOW_CREDENTIALS: "true"
```

### Best Practices

1. **Restrict Origins:** Only allow your actual frontend application domains
2. **Use HTTPS:** Production origins should use HTTPS (except localhost for dev)
3. **Limit Methods:** Only allow HTTP methods your API actually uses
4. **Limit Headers:** Only allow headers your API requires
5. **Monitor:** Log CORS errors to detect misconfiguration or unauthorized access attempts

## Updating CORS Settings

### Local Development

1. Edit `docker-compose.yml` for the relevant service(s)
2. Rebuild and restart:
   ```bash
   docker compose up -d --build flowpilot-domain-services-api
   ```

### GCP Cloud Run

1. Edit the relevant `cloud-run-envs/*.yaml` file
2. Rebuild the service (triggers image rebuild with new shared library):
   ```bash
   gcloud builds submit --config=cloudbuild-domain-services-api.yaml
   ```
3. Redeploy with updated environment variables:
   ```bash
   gcloud run deploy flowpilot-domain-services-api \
     --image=us-central1-docker.pkg.dev/vision-course-476214/flowpilot/flowpilot-domain-services-api:latest \
     --region=us-central1 \
     --platform=managed \
     --env-vars-file=cloud-run-envs/domain-services-api.yaml
   ```

## Testing CORS

### Browser DevTools

1. Open your web application in a browser
2. Open DevTools → Network tab
3. Make a request to a FlowPilot API
4. Check the response headers for:
   ```
   access-control-allow-origin: https://your-app.example.com
   access-control-allow-credentials: true
   access-control-allow-methods: GET, POST, PUT, DELETE
   access-control-allow-headers: authorization, content-type
   ```

### CORS Preflight Requests

For requests with custom headers (like `Authorization`), browsers send a preflight `OPTIONS` request:

```bash
# Example preflight request
curl -X OPTIONS http://localhost:8003/v1/workflows \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type" \
  -v
```

You should see CORS headers in the response.

### Common CORS Errors

**Error:** "Access to fetch at '...' from origin '...' has been blocked by CORS policy"

**Causes:**
1. Origin not in `CORS_ALLOWED_ORIGINS`
2. Using `*` with `CORS_ALLOW_CREDENTIALS=true`
3. Missing required header in `CORS_ALLOW_HEADERS`
4. Service not configured with CORS middleware (should not happen in FlowPilot)

**Solution:**
- Check environment variables in running service
- Verify origin matches exactly (including protocol and port)
- Check browser DevTools → Console for specific CORS error details

## Implementation Details

CORS is implemented in `flowpilot-services/shared-libraries/security.py`:

```python
def get_cors_config() -> dict[str, Any]:
    """
    Get CORS configuration from environment variables.
    Returns dict suitable for passing to CORSMiddleware constructor.
    """
    origins_str = os.environ.get("CORS_ALLOWED_ORIGINS", "*")
    origins = [o.strip() for o in origins_str.split(",")] if origins_str != "*" else ["*"]
    
    allow_credentials = os.environ.get("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"
    
    methods_str = os.environ.get("CORS_ALLOW_METHODS", "*")
    methods = [m.strip() for m in methods_str.split(",")] if methods_str != "*" else ["*"]
    
    headers_str = os.environ.get("CORS_ALLOW_HEADERS", "*")
    headers = [h.strip() for h in headers_str.split(",")] if headers_str != "*" else ["*"]
    
    return {
        "allow_origins": origins,
        "allow_credentials": allow_credentials,
        "allow_methods": methods,
        "allow_headers": headers,
    }
```

Each service applies CORS middleware in its FastAPI app initialization:

```python
from fastapi.middleware.cors import CORSMiddleware
import security

# Add CORS middleware
cors_config = security.get_cors_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_config["allow_origins"],
    allow_credentials=cors_config["allow_credentials"],
    allow_methods=cors_config["allow_methods"],
    allow_headers=cors_config["allow_headers"],
)
```

## Related Documentation

- [Integration Guide](../getting-started/integration.md) - Web application integration examples
- [Security Architecture](security.md) - Overall security model
- [Deployment Guide](../deployment/gcp.md) - GCP Cloud Run deployment with CORS
