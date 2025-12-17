# Authorization Graph Implementation

## Overview

FlowPilot implements **Relationship-Based Access Control (ReBAC)** using ***REMOVED*** as the Policy Decision Point (PDP). Authorization decisions are made by evaluating permission chains through an authorization graph maintained in ***REMOVED*** Directory.

## Graph Structure

```
workflow_item --workflow--> workflow --owner--> user --delegate--> agent
```

### Graph Components

**Objects (Nodes)**:
- `user` - End users who own workflows (created during provisioning)
- `agent` - Service agents that execute workflows (created during provisioning)
- `workflow` - Workflow instances (created at runtime)
- `workflow_item` - Individual items within workflows (created at runtime)

**Relations (Edges)**:
- `user --delegate--> agent` - User delegates execution authority to agent
- `workflow --owner--> user` - Workflow is owned by user
- `workflow_item --workflow--> workflow` - Item belongs to workflow

## Permission Evaluation

When an agent attempts to execute a workflow item:

1. **Request**: "Can `agent-runner` perform `can_execute` on `workflow_item_123`?"

2. *****REMOVED*** Resolution**:
   ```
   workflow_item_123.can_execute
   → workflow_item_123 --workflow--> workflow_456
   → workflow_456.can_execute  
   → workflow_456 --owner--> user_789
   → user_789 --delegate--> agent-runner
   → ALLOW
   ```

3. **Result**: Permission is **allowed** if the complete chain exists

## Graph Lifecycle

### Provisioning Time (One-time Setup)

**Script**: `flowpilot_provisioning_bootstrap/provision_bootstrap.py`

**Creates**:
- User objects in Keycloak (with credentials)
- User objects in ***REMOVED***
- Agent objects in ***REMOVED***
- Delegate relations: `user --delegate--> agent-runner`

**Command**:
```bash
cd flowpilot_provisioning_bootstrap
python3 provision_bootstrap.py \
  --csv-path users_seed.csv \
  --config provision_config.json
```

### Runtime (Per-Workflow)

**Triggered by**: Workflow creation via desktop app

**Service Flow**:
1. Desktop app → `POST /v1/trips/{template_id}/load` → services-api
2. Services-api creates workflow in memory
3. Services-api → `POST /v1/graph/workflows` → authz-api
4. AuthZ-api creates workflow object + owner relation in ***REMOVED***
5. For each workflow item:
   - Services-api → `POST /v1/graph/workflow-items` → authz-api
   - AuthZ-api creates workflow_item object + workflow relation in ***REMOVED***

## Architecture Components

### AuthZ Integration Service (`flowpilot-authz-api`)

**Responsibilities**:
- **PDP Façade**: Evaluates authorization requests via ***REMOVED***
- **PIP (Policy Information Point)**: Enriches requests with profile attributes
- **Graph Writer**: Maintains workflow-user relations in ***REMOVED***

**Key Endpoints**:
- `POST /v1/evaluate` - Evaluate authorization decision
- `POST /v1/graph/workflows` - Create workflow + owner relation
- `POST /v1/graph/workflow-items` - Create workflow_item + workflow relation
- Profile management endpoints for progressive profiling

**Implementation**:
- `create_***REMOVED***_object()` - Creates objects in ***REMOVED*** Directory
- `create_***REMOVED***_relation()` - Creates relations in ***REMOVED*** Directory
- `create_workflow_graph()` - Orchestrates workflow object + owner relation creation
- `create_workflow_item_graph()` - Orchestrates item object + workflow relation creation

### Domain Service (`flowpilot-services-api`)

**Responsibilities**:
- System of record for workflow state
- Policy Enforcement Point (PEP)
- Calls AuthZ API for graph writes during workflow creation

**Implementation**:
- `get_service_token()` - Obtains service-to-service token from Keycloak
- `_create_workflow_graph()` - Calls AuthZ API to create workflow graph
- `_create_workflow_item_graph()` - Calls AuthZ API to create item graph
- Error handling: Graph write failures are logged but don't fail workflow creation

## Authentication

All graph write operations require service-to-service authentication:

1. Services-api requests token from Keycloak (client credentials grant)
2. Token is cached with 30s expiry buffer
3. Token is included in Authorization header when calling authz-api
4. AuthZ-api validates token before processing graph writes

**Configuration** (`docker-compose.yml`):
```yaml
KEYCLOAK_CLIENT_ID: "flowpilot-agent"
KEYCLOAK_CLIENT_SECRET: ${KEYCLOAK_CLIENT_SECRET}
```

## Error Handling

### Graph Write Failures

If graph write operations fail:
- Error is logged with details
- Workflow creation proceeds (in-memory state is preserved)
- Authorization checks will fail until graph is repaired

**Rationale**: Workflow data is preserved even if authorization graph is temporarily unavailable.

### Recovery

If graph becomes inconsistent:
1. Identify missing workflows/items via ***REMOVED*** console
2. Manually create objects/relations using ***REMOVED*** CLI
3. Or delete and recreate workflows from desktop app

## ***REMOVED*** Manifest

The authorization graph structure is defined in `infra/***REMOVED***/cfg/flowpilot-manifest.yaml`:

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

**Permission resolution**:
- `workflow.can_execute` resolves to users who have delegated to agents
- `workflow_item.can_execute` inherits from parent workflow's `can_execute`

## Benefits of This Architecture

### Decoupled Authorization
- Domain services don't embed auth logic
- Authorization rules centralized in ***REMOVED*** manifest
- Same authz service can be reused across domains

### Verifiable Delegation
- No trusting client assertions
- Relations are explicit and auditable
- Complete permission chain is traceable

### Scalability
- Authorization graph scales independently
- ***REMOVED*** handles complex permission resolution
- Domain services only make simple API calls

### Security
- Service-to-service authentication required
- Token-based authorization
- Graph writes are atomic operations

## Troubleshooting

### "Denied" Decisions

If authorization checks are denied:

1. **Verify user delegation**:
   ```bash
   docker exec flowpilot-***REMOVED***-1 ./***REMOVED*** directory get relation -P --no-check \
     '{"object_type":"user","object_id":"<user_uuid>","relation":"delegate","subject_type":"agent"}'
   ```

2. **Verify workflow ownership**:
   ```bash
   docker exec flowpilot-***REMOVED***-1 ./***REMOVED*** directory get relation -P --no-check \
     '{"object_type":"workflow","object_id":"<workflow_id>","relation":"owner","subject_type":"user"}'
   ```

3. **Verify workflow_item linkage**:
   ```bash
   docker exec flowpilot-***REMOVED***-1 ./***REMOVED*** directory get relation -P --no-check \
     '{"object_type":"workflow_item","object_id":"<item_id>","relation":"workflow","subject_type":"workflow"}'
   ```

### Agent ID Mismatch

Ensure the agent ID matches across:
- Provisioning config: `flowpilot_provisioning_bootstrap/provision_config.json`
- Services config: `docker-compose.yml` → `AGENT_SUB`
- Should be: `agent-runner`

## References

- [***REMOVED*** Documentation](https://www.***REMOVED***.sh/)
- [AuthZEN Specification](https://openid.github.io/authzen/)
- [ReBAC Overview](https://www.osohq.com/academy/relationship-based-access-control-rebac)
