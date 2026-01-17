# Quick Start

Get FlowPilot running locally in 5 minutes.

## Prerequisites

- Docker and Docker Compose
- `make` (optional, for convenience commands)
- `curl` or similar HTTP client for testing

## Step 1: Clone the Repository

```bash
git clone https://github.com/yourusername/flowpilot.git
cd flowpilot
```

## Step 2: Configure Environment

Create a `.env` file in the root directory:

```bash
cat > .env << EOF
KEYCLOAK_ADMIN_USERNAME=admin
KEYCLOAK_ADMIN_PASSWORD=admin123
KEYCLOAK_CLIENT_SECRET=your-secret-here
AGENT_CLIENT_SECRET=your-agent-secret-here
EOF
```

!!! warning "Security Note"
    Never commit the `.env` file to version control. It contains sensitive credentials.

## Step 3: Start the Stack

The easiest way to start FlowPilot is using the provided script:

```bash
make up
# Or directly:
./bin/stack-up.sh
```

This script will:

1. Build and start all Docker containers
2. Wait for Keycloak to be ready (can take 60+ seconds)
3. Provision test users and agent relationships
4. Configure OIDC clients

## Step 4: Verify Services Are Running

Check the status of all services:

```bash
make status
# Or:
docker compose ps
```

You should see all services in "Up" status:

- `keycloak`
- `opa`
- `flowpilot-authz-api`
- `flowpilot-delegation-api`
- `flowpilot-domain-services-api`
- `flowpilot-ai-agent-api`

## Step 5: Run Integration Tests

Verify everything works by running the test suite:

```bash
python3 tests/user_based_testing.py
```

Expected output:
```
Test Results:
- Kathleen: Allowed=0, Denied=3, Errors=0 ✓
- Peter: Allowed=0, Denied=3, Errors=0 ✓
- Carlo: Allowed=3, Denied=0, Errors=0 ✓
```

## Step 6: Explore the APIs

### Health Check

```bash
curl http://localhost:8002/health  # authz-api
curl http://localhost:8003/health  # domain-services-api
curl http://localhost:8004/health  # ai-agent-api
curl http://localhost:8005/health  # delegation-api
```

### Get an Access Token

```bash
TOKEN=$(curl -s -X POST \
  "http://localhost:8080/realms/flowpilot/protocol/openid-connect/token" \
  -d "grant_type=client_credentials" \
  -d "client_id=flowpilot-agent" \
  -d "client_secret=$AGENT_CLIENT_SECRET" | jq -r '.access_token')

echo $TOKEN
```

### Create a Workflow

```bash
curl -X POST http://localhost:8003/v1/workflows \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "trip-to-milan",
    "principal_sub": "user-uuid-here",
    "start_date": "2026-02-01",
    "persona": "traveler"
  }'
```

## Common Commands

### View Logs

```bash
# All services
make logs

# Specific service
docker compose logs -f flowpilot-authz-api
docker compose logs -f opa
```

### Stop the Stack

```bash
make down
# Or:
./bin/stack-down.sh
```

### Reset Everything

```bash
make reset
# Or:
./bin/stack-reset.sh
```

This wipes all volumes and gives you a clean slate.

## Next Steps

- 📖 [Local Development Guide](local-development.md) - Detailed setup and development workflow
- 🏗️ [Architecture Overview](../architecture/overview.md) - Understand the design
- 🔐 [Authorization Model](../architecture/authorization.md) - Learn about personas and delegation
- 🚀 [Deploy to GCP](gcp-deployment.md) - Run in the cloud

## Troubleshooting

### Keycloak Not Ready

If provisioning fails, wait longer:

```bash
docker compose logs -f keycloak
# Wait for "Listening on: https://0.0.0.0:8443"
```

### Port Conflicts

Ensure ports 8080, 8181, 8443, and 8002-8005 are available:

```bash
lsof -i :8080
lsof -i :8002
```

### Services Won't Start

Try a full rebuild:

```bash
docker compose down -v
docker compose up -d --build
```

For more troubleshooting tips, see the [WARP.md](../WARP.md#troubleshooting) file or check service logs.
