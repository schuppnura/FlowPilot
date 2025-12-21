# FlowPilot Startup Guide

## Quick Start

To start the entire FlowPilot stack with proper initialization:

```bash
./bin/stack-up.sh
```

This script will:
1. Build the OCI policy bundle (if policy CLI is installed)
2. Start the HTTPS bundle server with TLS
3. Start all Docker containers
4. Wait for ***REMOVED*** to be ready
5. Load the authorization manifest into ***REMOVED***
6. Wait for Keycloak to be ready
7. Provision users and the agent in ***REMOVED***

## Manual Startup (if needed)

If you need to start services manually:

```bash
# 1. Start containers
docker compose up -d

# 2. Wait for Keycloak (important!)
sleep 10

# 3. Provision users and agent
python3 provision_current_user.py
```

## Troubleshooting

### "Allowed=0, Denied=3, Errors=0" in macOS app

This means the agent doesn't have permission to execute workflows. The most common causes:

1. **Agent not provisioned**: Run `python3 provision_current_user.py`
2. **Users not provisioned**: The script above also provisions users
3. **Manifest not loaded**: Run `./bin/***REMOVED***-init.sh`

### Check if agent exists

```bash
python3 -c "
import requests
r = requests.post('http://localhost:9393/api/v3/directory/check', json={
    'subject_type': 'agent',
    'subject_id': 'agent_flowpilot_1',
    'object_type': 'workflow',
    'object_id': 'YOUR_WORKFLOW_ID',
    'relation': 'can_execute'
})
print(r.json())
"
```

If you see `"reason": "E20025 object not found: subject agent:agent_flowpilot_1"`, the agent wasn't provisioned.

### Keycloak not ready error

If `provision_current_user.py` fails with "Failed to get admin token: 401", Keycloak isn't fully ready yet. Wait longer and retry:

```bash
sleep 10
python3 provision_current_user.py
```

### Clean slate restart


## What Gets Provisioned

The provisioning script creates:

1. **User objects**: One for each user in the Keycloak `flowpilot` realm
2. **Agent object**: `agent_flowpilot_1` (the AI agent runner)
3. **Delegation relations**: Each user delegates execution permission to the agent

This enables the permission chain:
```
agent can execute workflow_item
  → via workflow_item.workflow relation
  → workflow.can_execute permission  
  → via workflow.owner relation
  → user delegates to agent
```

## Service Dependencies

Start order matters:

1. **HTTPS Bundle Server** - Must be running before ***REMOVED*** starts (serves OCI policy bundles)
2. **Keycloak** - Must be fully ready before provisioning
3. **Services API** - Creates workflow graphs when workflows are created
4. **AuthZ API** - Evaluates permissions

## Key Files

- `bin/stack-up.sh` - Main startup script
- `provision_current_user.py` - Provisions users and agent
