# FlowPilot ABAC Policy Bundle

This directory contains the OPA policy bundle for FlowPilot's ABAC (Attribute-Based Access Control) layer.

## Status

**ReBAC (Relationship-Based) authorization**: ✅ **WORKING**  
**ABAC (Attribute-Based) authorization**: ⏸️ **READY BUT DISABLED**

## Policy Files

- `auto_book.rego` - OPA/Rego policy implementing auto-booking authorization rules
- `.manifest` - OPA bundle manifest defining policy roots and revision
- `policy-bundle.tar.gz` - Pre-built OCI-compatible policy bundle

## Policy Logic

The `auto_book` policy evaluates four conditions for autonomous booking:

1. **Consent**: User must have `auto_book_consent = true`
2. **Cost limit**: Trip cost must be ≤ `auto_book_max_cost_eur`
3. **Advance notice**: Days until departure must be ≥ `auto_book_min_days_advance`
4. **Risk threshold**: Airline risk score must be < `auto_book_max_airline_risk`

Returns:
- `allow`: boolean indicating if all conditions pass
- `reason`: string code explaining denial reason if applicable

## Building the Bundle

The policy bundle can be rebuilt using the `policy` CLI (OPCR):

```bash
# Install policy CLI
brew tap opcr-io/tap && brew install opcr-io/tap/policy

# Build bundle
cd /path/to/FlowPilot/infra/***REMOVED***/cfg/bundle
policy build . -t localhost/flowpilot-policy:latest

# Save as tarball
policy save localhost/flowpilot-policy:latest -f policy-bundle.tar.gz
```

## Integration with ***REMOVED***

### Current Issue

***REMOVED*** v3 (latest) successfully loads the bundle but the Authorizer API returns empty `decisions` arrays when querying the policy. This appears to be a configuration or API compatibility issue.

**Evidence of bundle loading:**
```
{"level":"info","name":"flowpilot","plugin":"bundle","message":"Bundle loaded and activated successfully."}
```

**Issue when querying:**
```json
POST /api/v2/authz/is
{
  "policy_context": {"path": "auto_book", "decisions": ["allow", "reason"]},
  "resource_context": { /* policy input */ }
}

Response: {"decisions": []}  // Empty!
```

### Attempted Solutions

1. ✅ HTTP bundle serving - ***REMOVED*** fetches successfully
2. ✅ Clean bundle creation (no macOS metadata)
3. ✅ OCI image packaging with `policy` CLI
4. ✅ Tested with ***REMOVED*** 0.30, 0.32, and latest
5. ❌ Policy evaluation still returns empty decisions

### Enabling ABAC (When Fixed)

To enable ABAC policy evaluation once the ***REMOVED*** integration is resolved:

1. Start HTTP server for bundle:
   ```bash
   cd infra/***REMOVED***/cfg
   python3 -m http.server 8888 &
   ```

2. Uncomment OPA config in `config.yaml`:
   ```yaml
   opa:
     instance_id: "-"
     graceful_shutdown_period_seconds: 2
     config:
       services:
         bundle_server:
           url: http://host.docker.internal:8888
       bundles:
         flowpilot:
           service: bundle_server
           resource: bundle/policy-bundle.tar.gz
           persist: false
   ```

3. Restart ***REMOVED***:
   ```bash
   docker compose restart ***REMOVED***
   ```

4. Verify bundle loaded:
   ```bash
   docker compose logs ***REMOVED*** | grep "Bundle loaded"
   ```

## Next Steps

- [ ] Post on [***REMOVED*** Community Slack](https://aserto.com/slack) with specific config and issue
- [ ] Check if newer ***REMOVED*** versions or different config format resolves the issue
- [ ] Consider alternative: temporary Python-based policy evaluation for demo purposes

## References

- [***REMOVED*** Documentation](https://www.***REMOVED***.sh/)
- [OPA/Rego Language](https://www.openpolicyagent.org/docs/latest/policy-language/)
- [OPCR Policy CLI](https://github.com/opcr-io/policy)
- [FlowPilot Auto-Book Policy Design](../../../docs/AUTO_BOOK_POLICY.md)
