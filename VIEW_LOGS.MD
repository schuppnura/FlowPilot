To view the structured API logging output from `shared-libraries/api_logging.py` when running on Google Cloud Run, you have two primary options:

## 1. Cloud Logging (Recommended)

View logs in real-time or search historical logs:

```bash
# Tail logs for a specific service
gcloud logging tail "resource.type=cloud_run_revision AND resource.labels.service_name=flowpilot-authz-api" --format=json

# View recent logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=flowpilot-authz-api" --limit=50 --format=json

# Filter for specific log severity
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=flowpilot-authz-api AND severity>=INFO" --limit=50
```
## 2. Cloud Console

Navigate to: **Cloud Console → Logging → Logs Explorer**

Useful queries:
```
resource.type="cloud_run_revision"
resource.labels.service_name="flowpilot-authz-api"
```
Filter by specific fields from your structured logs:
```
resource.type="cloud_run_revision"
jsonPayload.endpoint="/v1/evaluate"
```

## Key Considerations

Since your `api_logging.py` likely outputs structured JSON logs, Cloud Run automatically captures:
- `stdout`/`stderr` → Cloud Logging
- JSON logs → parsed as `jsonPayload` fields (searchable)
- Plain text logs → stored as `textPayload`

Make sure your logging uses `print()` or Python's `logging` module configured to write to stdout—Cloud Run captures this automatically.

**Pro tip:** For debugging inter-service calls, filter by correlation IDs or request IDs if your logging includes them.


## ✅ Compatibility Analysis

**1. JSON to stdout** (lines 172, 218)
- Uses `print(json.dumps(...), file=sys.stdout, flush=True)`
- Cloud Run captures stdout automatically and parses JSON as `jsonPayload`

**2. Structured logging format**
- Each log entry includes `type`, `timestamp`, `method`, `path`, etc.
- These become searchable fields in Cloud Logging's `jsonPayload` object

**3. Environment-gated** (line 40)
- Controlled by `ENABLE_API_LOGGING` environment variable
- You can enable/disable per service via `cloud-run-envs/*.yaml`

## How to Use in GCP

**1. Enable logging for a service:**

Add to `cloud-run-envs/authz-api.yaml`:
```yaml
ENABLE_API_LOGGING: "1"
```
Then redeploy:
```bash
gcloud run services update flowpilot-authz-api \
  --region=us-central1 \
  --update-env-vars ENABLE_API_LOGGING=1
```
**2. View logs to authz-api:**

```bash
# Search for API requests
gcloud logging read 'resource.type="cloud_run_revision" 
  AND resource.labels.service_name="flowpilot-authz-api" 
  AND jsonPayload.type="api_request"' \
  --limit=20 --format=json

# Search by specific endpoint
gcloud logging read 'resource.type="cloud_run_revision" 
  AND jsonPayload.path="/v1/evaluate"' \
  --limit=20 --format=json
```
**3. Cloud Console filtering:**
```
resource.type="cloud_run_revision"
jsonPayload.type="api_request"
jsonPayload.path="/v1/evaluate"
jsonPayload.status_code=200
```
**4. View logs from authz-api to opa:**

```bash
# Search for OPA calls (URL contains "opa")
gcloud logging read 'resource.type="cloud_run_revision" 
  AND resource.labels.service_name="flowpilot-authz-api" 
  AND jsonPayload.path:"opa"' \
  --limit=50 --format=json

# Or search for the specific OPA endpoint path
gcloud logging read 'resource.type="cloud_run_revision" 
  AND resource.labels.service_name="flowpilot-authz-api" 
  AND jsonPayload.path:"/v1/data/"' \
  --limit=50 --format=json
```