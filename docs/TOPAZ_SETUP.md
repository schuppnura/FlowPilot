# ***REMOVED*** Setup Guide

## Overview

***REMOVED*** is the Policy Decision Point (PDP) that handles authorization checks for FlowPilot. It needs to have the authorization model (manifest) loaded before it can process authorization requests.

## Current Issue

The FlowPilot manifest (`infra/***REMOVED***/cfg/flowpilot-manifest.yaml`) defines the authorization model with these object types:
- `user` - Users who can delegate to agents
- `agent` - Agents that can execute workflows
- `workflow` - Workflows with owners
- `workflow_item` - Individual items in workflows

However, this manifest needs to be loaded into ***REMOVED***'s directory before authorization checks will work.

**Update**: The current ***REMOVED*** Docker image (`ghcr.io/aserto-dev/***REMOVED***:latest`) does NOT support:
- `/api/v3/directory/model/set` endpoint (returns 404 Not Found)
- `/api/v3/directory/objects` endpoint (returns 501 Method Not Allowed)
- `/api/v3/directory/relations` endpoint (returns 501 Method Not Allowed)

These endpoints are required for dynamic manifest loading. The **only supported method** is using the ***REMOVED*** CLI.

## The Manifest

```yaml
types:
  user:
    relations:
      delegate: agent
  
  agent: {}
  
  workflow:
    relations:
      owner: user
    permissions:
      can_execute: owner->delegate
  
  workflow_item:
    relations:
      workflow: workflow
    permissions:
      can_execute: workflow->can_execute
```

## Loading the Manifest

### Option 1: Using the ***REMOVED*** CLI (Recommended)

If you have the `***REMOVED***` CLI installed locally:

```bash
# Install ***REMOVED*** CLI
brew tap aserto-dev/tap && brew install aserto-dev/tap/***REMOVED***

# Load the manifest
***REMOVED*** directory set manifest infra/***REMOVED***/cfg/flowpilot-manifest.yaml \
  --insecure \
  --host localhost:9292
```

### Option 2: Manual API Call (JSON format)

The ***REMOVED*** import API endpoint doesn't seem to be available in the current version. You may need to:

1. Use a newer version of ***REMOVED*** that supports manifest loading via API
2. Use the ***REMOVED*** CLI tool
3. Load data directly using the relations API

### Option 3: Load Sample Data

Instead of loading the manifest via API, you can bootstrap the directory by creating sample relations:

```bash
# Create a sample user
curl -X POST http://localhost:9393/api/v3/directory/objects \
  -H "Content-Type: application/json" \
  -d '{"object_type": "user", "object_id": "user_123"}'

# Create a sample agent
curl -X POST http://localhost:9393/api/v3/directory/objects \
  -H "Content-Type: application/json" \
  -d '{"object_type": "agent", "object_id": "agent_flowpilot_1"}'

# Create delegation relationship
curl -X POST http://localhost:9393/api/v3/directory/relations \
  -H "Content-Type: application/json" \
  -d '{
    "object_type": "user",
    "object_id": "user_123",
    "relation": "delegate",
    "subject_type": "agent",
    "subject_id": "agent_flowpilot_1"
  }'
```

## Verification

Test that ***REMOVED*** can perform authorization checks:

```bash
curl -X POST http://localhost:9393/api/v3/directory/check \
  -H "Content-Type: application/json" \
  -d '{
    "object_type": "workflow_item",
    "object_id": "item_123",
    "relation": "can_execute",
    "subject_type": "agent",
    "subject_id": "agent_flowpilot_1"
  }'
```

Expected response:
```json
{
  "check": true/false,
  "trace": []
}
```

If you get an error about "object type not found", the manifest is not loaded.

## Alternative: Use ***REMOVED*** with Bundle

Update `infra/***REMOVED***/cfg/config.yaml` to load a policy bundle that includes the manifest:

```yaml
opa:
  local_bundles:
    paths:
      - /app/cfg
```

Then create a bundle that includes the manifest. This is the recommended approach for production.

## Troubleshooting

### "object type not found" errors

This means the ***REMOVED*** directory doesn't have the object types registered. Load the manifest first.

### 403 Forbidden from authz-api

The authz-api is calling ***REMOVED***, but ***REMOVED*** is returning deny because:
1. The manifest isn't loaded, OR
2. No relations have been set up between users, agents, and workflows

### Check ***REMOVED*** logs

```bash
docker logs flowpilot-***REMOVED***-1
```

Look for errors about the directory or manifest loading.

## Next Steps

1. Install the ***REMOVED*** CLI tool
2. Load the FlowPilot manifest
3. Create sample relations for testing
4. Verify authorization checks work

## Resources

- [***REMOVED*** Documentation](https://www.***REMOVED***.sh/)
- [***REMOVED*** Directory API](https://www.***REMOVED***.sh/docs/directory/directory-api)
- [FlowPilot Manifest](../infra/***REMOVED***/cfg/flowpilot-manifest.yaml)
