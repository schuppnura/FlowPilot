# ***REMOVED*** Audit Trail Guide

This guide explains how to view and analyze ***REMOVED*** authorization decisions for audit purposes.

## Overview

FlowPilot enables *****REMOVED*** trace by default** for all authorization checks, providing a complete audit trail of:
- Anti-spoofing checks (ownership verification)
- ReBAC delegation checks (agent authorization)
- ABAC policy evaluations (auto-book constraints)

## Viewing Real-Time Logs

### Follow ***REMOVED*** logs in real-time
```bash
docker logs -f flowpilot-***REMOVED***-1
```

### View recent logs (last 100 lines)
```bash
docker logs --tail 100 flowpilot-***REMOVED***-1
```

### View logs from the last hour
```bash
docker logs --since 1h flowpilot-***REMOVED***-1
```

## Filtering Authorization Decisions

### Filter for permission checks
```bash
docker logs flowpilot-***REMOVED***-1 | grep -i "check"
```

### Filter for specific permissions
```bash
# View ownership checks (anti-spoofing)
docker logs flowpilot-***REMOVED***-1 | grep -i "is_owner"

# View delegation checks
docker logs flowpilot-***REMOVED***-1 | grep -i "can_execute"
```

### Filter for denials
```bash
docker logs flowpilot-***REMOVED***-1 | grep -i "denied\|deny\|false"
```

## Understanding Decision IDs

Every authorization decision includes a `decision_id` that can be used to correlate:
1. The AuthZ API request (includes `decision_id` in response)
2. The ***REMOVED*** permission check (logs include trace information)
3. The client request (includes `decision_id` in error/success response)

Example correlation:
```bash
# Find all logs related to a specific decision
docker logs flowpilot-***REMOVED***-1 | grep "3f8b4d2e-5a1c-4f9b-8e3d-7c2a9b1d4e6f"
```

## Querying the Authorization Graph

### List all workflows in ***REMOVED***
```bash
docker exec flowpilot-***REMOVED***-1 ***REMOVED*** directory list objects workflow --plaintext
```

### List all relations for a specific workflow
```bash
docker exec flowpilot-***REMOVED***-1 ***REMOVED*** directory list relations --plaintext \
  --object-type workflow --object-id t_abc12345
```

### Check a specific permission
```bash
# Check if a user owns a workflow
docker exec flowpilot-***REMOVED***-1 ***REMOVED*** directory check --plaintext \
  --subject-type user --subject-id "2129b076-cd98-4f7b-a101-7d0fa228b1c3" \
  --object-type workflow --object-id "t_abc12345" \
  --relation is_owner

# Check if an agent can execute a workflow item
docker exec flowpilot-***REMOVED***-1 ***REMOVED*** directory check --plaintext \
  --subject-type agent --subject-id "agent-runner" \
  --object-type workflow_item --object-id "i_xyz67890" \
  --relation can_execute
```

## Trace Information in API Responses

When `trace: true` is set in the request (or when trace is enabled by default), the AuthZ API response includes detailed trace information showing:

1. **Ownership check** - Shows if principal owns the workflow
2. **Delegation check** - Shows the complete graph traversal
3. **Policy evaluation** - Shows why ABAC decisions were made

Example response with trace:
```json
{
  "decision": "deny",
  "decision_id": "3f8b4d2e-5a1c-4f9b-8e3d-7c2a9b1d4e6f",
  "reason_codes": ["security.principal_spoof"],
  "advice": [
    {
      "kind": "security",
      "code": "principal_spoof",
      "message": "Principal does not own the workflow. Rejecting request to prevent principal spoofing."
    },
    {
      "kind": "debug",
      "code": "***REMOVED***.ownership_check",
      "message": "***REMOVED*** ownership check returned deny.",
      "details": {
        "subject_type": "user",
        "subject_id": "attacker-456",
        "object_type": "workflow",
        "object_id": "t_abc12345",
        "relation": "is_owner"
      }
    }
  ]
}
```

## Export Logs for Analysis

### Save logs to a file
```bash
docker logs flowpilot-***REMOVED***-1 > ***REMOVED***_audit_$(date +%Y%m%d_%H%M%S).log
```

### Save logs from a specific time range
```bash
docker logs flowpilot-***REMOVED***-1 --since "2024-12-18T09:00:00" --until "2024-12-18T10:00:00" > audit.log
```

## Disabling Trace (Optional)

If you need to disable trace for performance reasons in production:

### Option 1: Environment Variable
Set in `.env` or `docker-compose.yml`:
```bash
***REMOVED***_TRACE_DEFAULT=false
```

### Option 2: Per-Request
Set in the API request options:
```json
{
  "options": {
    "trace": false
  }
}
```

## Production Audit Setup

For production environments, consider:

1. **Centralized Logging**: Send ***REMOVED*** logs to a logging platform (ELK, Splunk, CloudWatch)
2. **Log Retention**: Configure retention policies for compliance requirements
3. **Alerting**: Set up alerts for authorization denials, especially anti-spoofing detections
4. **Correlation**: Use `decision_id` to correlate requests across services
5. **Regular Audits**: Review authorization decisions periodically for anomalies

## Key Audit Scenarios

### Scenario 1: Verify Anti-Spoofing Works
```bash
# Run the user-based test
python3 tests/user_based_testing.py

# Check logs for ownership verification
docker logs flowpilot-***REMOVED***-1 | grep -A 5 "is_owner"
```

### Scenario 2: Track User Activity
```bash
# Find all authorization decisions for a specific user
docker logs flowpilot-***REMOVED***-1 | grep "2129b076-cd98-4f7b-a101-7d0fa228b1c3"
```

### Scenario 3: Investigate Denial
```bash
# Get the decision_id from the API response, then:
docker logs flowpilot-***REMOVED***-1 | grep "<decision_id>"
```

## Related Documentation

- [Authorization Graph](AUTHORIZATION_GRAPH.md)
- [Auto-Book Policy](AUTO_BOOK_POLICY.md)
- [Security Setup](SECURITY_SETUP.md)
