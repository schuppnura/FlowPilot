# API Logging for FlowPilot

## Overview

FlowPilot includes structured JSON logging for API requests and responses to aid debugging. All logs are written to stdout in plain JSON format, making them easy to inspect via CLI tools like `docker compose logs` or `jq`.

## Features

- **Structured JSON output** - Every log entry is a single-line JSON object
- **Request logging** - Logs method, path, request body, decoded token claims, path/query parameters
- **Response logging** - Logs status code, response body, and errors
- **Token decoding** - Automatically decodes JWT tokens to show claims (without exposing raw tokens)
- **Environment-controlled** - Enable/disable via `ENABLE_API_LOGGING` environment variable
- **Zero overhead when disabled** - When disabled, logging functions are no-ops

## Usage

### Enable Logging

Set the `ENABLE_API_LOGGING` environment variable to `"1"` in your `docker-compose.yml`:

```yaml
environment:
  - ENABLE_API_LOGGING=1
```

### View Logs

```bash
# View all logs
docker compose logs -f

# View logs for specific service
docker compose logs -f flowpilot-authz-api

# Filter and pretty-print JSON logs
docker compose logs flowpilot-authz-api | grep '"type":"api_' | jq .

# Filter only requests
docker compose logs flowpilot-authz-api | grep '"type":"api_request"' | jq .

# Filter only responses
docker compose logs flowpilot-authz-api | grep '"type":"api_response"' | jq .
```

## Log Format

### Request Log

```json
{
  "type": "api_request",
  "timestamp": "2025-12-21T13:00:00.123456+00:00",
  "method": "POST",
  "path": "/v1/evaluate",
  "request_body": {
    "subject": {"type": "agent", "id": "agent-runner"},
    "action": {"name": "book"},
    "resource": {"type": "workflow", "id": "w_12345678"}
  },
  "token_claims": {
    "sub": "1460e175-74f9-43af-aac3-7b4fc0547f05",
    "iss": "https://localhost:8443/realms/flowpilot",
    "aud": "account",
    "exp": 1734789600
  },
  "path_params": {
    "workflow_id": "w_12345678"
  }
}
```

### Response Log

```json
{
  "type": "api_response",
  "timestamp": "2025-12-21T13:00:00.234567+00:00",
  "method": "POST",
  "path": "/v1/evaluate",
  "status_code": 200,
  "response_body": {
    "decision": "allow",
    "reason_codes": [],
    "advice": []
  }
}
```

### Error Response Log

```json
{
  "type": "api_response",
  "timestamp": "2025-12-21T13:00:00.234567+00:00",
  "method": "POST",
  "path": "/v1/evaluate",
  "status_code": 400,
  "error": "Invalid request: missing required field"
}
```

## Integration in Code

The logging module is already integrated into key endpoints. To add logging to a new endpoint:

```python
import logging as api_logging

@app.post("/v1/your-endpoint")
def your_endpoint(
    request: Request,
    request_body: dict[str, Any] = Body(...),
    token_claims: dict[str, Any] = Depends(get_token_claims),
) -> dict[str, Any]:
    # Extract raw token
    raw_token = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        raw_token = auth_header[7:]
    
    # Log request
    api_logging.log_api_request(
        method="POST",
        path="/v1/your-endpoint",
        request_body=request_body,
        token_claims=token_claims,
        raw_token=raw_token,
    )
    
    try:
        # Your processing logic here
        result = process_request(request_body)
        
        # Log successful response
        api_logging.log_api_response(
            method="POST",
            path="/v1/your-endpoint",
            status_code=200,
            response_body=result,
        )
        
        return result
    except Exception as exc:
        # Log error response
        api_logging.log_api_response(
            method="POST",
            path="/v1/your-endpoint",
            status_code=400,
            error=str(exc),
        )
        raise
```

## Benefits

1. **Easy debugging** - See exactly what goes into and out of each API call
2. **Token inspection** - View decoded JWT claims without exposing raw tokens
3. **CLI-friendly** - JSON format works perfectly with `jq`, `grep`, and other CLI tools
4. **No code clutter** - Simple function calls, no debug flags or if/then clauses
5. **Production-safe** - Disabled by default, can be enabled only when needed

## Example Workflow

```bash
# 1. Enable logging in docker-compose.yml
# 2. Restart services
docker compose up -d

# 3. Make an API call (from your app or curl)

# 4. View the logs
docker compose logs flowpilot-authz-api | grep '"type":"api_' | jq .

# 5. Filter for specific endpoint
docker compose logs flowpilot-authz-api | grep '/v1/evaluate' | jq .

# 6. Find all errors
docker compose logs flowpilot-authz-api | grep '"status_code":[45]' | jq .
```


