# Viewing API Logs

The API logging system writes structured JSON logs to stdout in the Docker containers. Here's how to view them:

## Quick Commands

### View all API logs (requests and responses)
```bash
docker compose logs | grep '"type":"api_' | jq .
```

### View only requests
```bash
docker compose logs | grep '"type":"api_request"' | jq .
```

### View only responses
```bash
docker compose logs | grep '"type":"api_response"' | jq .
```

### View logs for specific service
```bash
# AuthZ API
docker compose logs flowpilot-authz-api | grep '"type":"api_' | jq .

# Domain Services API
docker compose logs flowpilot-domain-services-api | grep '"type":"api_' | jq .
```

### Follow logs in real-time
```bash
# Watch all API logs as they come in
docker compose logs -f | grep '"type":"api_' | jq .

# Watch specific service
docker compose logs -f flowpilot-authz-api | grep '"type":"api_' | jq .
```

### View recent logs (last 100 lines)
```bash
docker compose logs --tail 100 | grep '"type":"api_' | jq .
```

## Filtering Logs

### Filter by endpoint
```bash
# Only /v1/evaluate logs
docker compose logs | grep '/v1/evaluate' | jq .

# Only workflow execution logs
docker compose logs | grep '/execute' | jq .
```

### Filter by status code
```bash
# Only errors (4xx/5xx)
docker compose logs | grep '"status_code":[45]' | jq .

# Only success (2xx)
docker compose logs | grep '"status_code":2' | jq .
```

### Filter by user
```bash
# Logs for specific user (by sub claim)
docker compose logs | grep 'carlo' | jq .
```

## Log File Locations

The logs are written to stdout in the containers, so they appear in:
- `docker compose logs` output
- Container stdout (visible via `docker logs <container-name>`)

## Example Output

When you make an API call, you'll see logs like:

```json
{"type":"api_request","timestamp":"2025-12-21T13:00:00Z","method":"POST","path":"/v1/evaluate","request_body":{...},"token_claims":{"sub":"..."}}
{"type":"api_response","timestamp":"2025-12-21T13:00:01Z","method":"POST","path":"/v1/evaluate","status_code":200,"response_body":{"decision":"allow",...}}
```

## Troubleshooting

### No logs appearing?
1. Check if logging is enabled:
   ```bash
   docker compose exec flowpilot-authz-api printenv | grep ENABLE_API_LOGGING
   ```
   Should show: `ENABLE_API_LOGGING=1`

2. Make an API call from the app to generate logs

3. Check if services are running:
   ```bash
   docker compose ps
   ```

### Pretty-print JSON
If you don't have `jq` installed:
```bash
# Install jq
brew install jq

# Or use python to pretty-print
docker compose logs | grep '"type":"api_' | python3 -m json.tool
```

