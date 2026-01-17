# Policy Governance

This section describes FlowPilot's policy governance framework - how authorization policies are developed, validated, deployed, and audited in a production environment.

FlowPilot demonstrates a **GitOps-based policy governance model** where:

1. **Policies are code** - OPA Rego policies live in version control
2. **Changes are auditable** - Every policy change has a git commit hash
3. **Deployments are validated** - Automated tests prevent broken policies from reaching production
4. **Rollbacks are instant** - Zero-downtime rollback to previous policy versions
5. **History is preserved** - Complete audit trail of all policy deployments

## Policy Deployment Lifecycle

```
┌─────────────────┐
│ 1. Development  │  Developer edits policy.rego
│                 │  Policy is validated locally
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. Version      │  Changes committed to git
│    Control      │  Commit hash becomes version tag
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. Governance   │  Pre-deployment checks:
│    Checks       │  • Syntax validation
│                 │  • Unit tests (if present)
│                 │  • Uncommitted changes check
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. Build        │  Docker image built with policy
│                 │  Tagged with git commit hash
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 5. Deploy       │  New revision deployed (no traffic)
│    (No Traffic) │  Previous revision still serves all traffic
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 6. Traffic      │  100% traffic shifted to new revision
│    Shift        │  Zero-downtime cutover
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 7. Regression   │  Full test suite runs against new policy
│    Tests        │  12 authorization scenarios validated
└────────┬────────┘
         │
         ├─ PASS ──────────────┐
         │                     │
         │                     ▼
         │            ┌─────────────────┐
         │            │ 8. Success      │  Deployment complete
         │            │                 │  Audit log updated
         │            └─────────────────┘
         │
         └─ FAIL ──────────────┐
                               │
                               ▼
                      ┌─────────────────┐
                      │ 8. Auto-Rollback│  Traffic shifted back
                      │                 │  Previous policy restored
                      │                 │  Incident logged
                      └─────────────────┘
```

## Deployment Script

### Usage

```bash
# Standard deployment (with all checks and tests)
./bin/deploy-opa-policy.sh

# Skip regression tests (faster, less safe)
./bin/deploy-opa-policy.sh --skip-tests

# Automated deployment (no prompts)
./bin/deploy-opa-policy.sh --auto-approve

# Combined flags
./bin/deploy-opa-policy.sh --skip-tests --auto-approve
```

### What the Script Does

**Governance Checks**

- Validates all Rego files have correct syntax
- Warns if uncommitted changes exist (policies MUST be version controlled)
- Runs OPA unit tests if present

**Version Tagging**

- Uses git commit hash as version identifier (e.g., `a3f9d2c`)
- Tags Docker image with version for traceability
- Creates Cloud Run revision tag for easy access

**Safe Deployment**

- Deploys new revision without routing traffic (no user impact)
- Shifts traffic only after successful deployment
- Monitors for errors during traffic shift

**Automated Testing**

- Runs 12 regression tests covering all authorization scenarios
- Tests delegation, personas, autobook constraints, anti-spoofing
- Validates new policy behavior matches expectations

**Automatic Rollback**

- If tests fail, immediately restores previous policy
- No manual intervention needed for failed deployments
- Complete rollback in <10 seconds

**Audit Trail**

- Logs every deployment attempt to `logs/opa-deployments.log`
- Records: timestamp, version, outcome, rollback events
- Shows recent deployment history at end of each deployment

## Governance Controls

### Pre-Deployment Controls

**Version Control Requirement**

- All policy changes must be committed to git before deployment
- Uncommitted changes trigger a warning and require confirmation
- Ensures every production policy has a commit hash for traceability

**Syntax Validation**

- OPA CLI validates all Rego files before deployment
- Prevents syntax errors from reaching production
- Fails fast if policies have parse errors

**Unit Testing** (optional but recommended)

- If `policy_test.rego` files exist, they are automatically run
- Tests validate policy logic before deployment
- Example: Test that suspended personas are always denied

### Deployment Controls

**Zero-Downtime Deployment**

- New policy revision deployed alongside old revision
- Traffic shifted only after new revision is healthy
- No service interruption during policy updates

**Canary Testing**

- Script supports gradual traffic shifting (easily extensible)
- Could deploy to 10% traffic, validate metrics, then 100%
- Reduces blast radius of policy errors

### Post-Deployment Controls

**Automated Regression Testing**

- 12 comprehensive test scenarios run automatically
- Covers positive and negative authorization cases
- Tests run against production environment (GCP Cloud Run)

**Automatic Rollback**

- Failed tests trigger immediate rollback
- Previous policy restored within seconds
- No human intervention required

**Audit Logging**

- Every deployment logged with:
    - Timestamp (UTC)
    - Version tag (git commit hash)
    - Outcome (success/failure/rollback)
    - Revision identifier
- Immutable audit trail for compliance

## Governance Best Practices

### For Policy Authors

**Always commit before deploying**
   ```bash
   git add infra/opa/policies/
   git commit -m "policy: add persona validity time checks"
   ./bin/deploy-opa-policy.sh
   ```

**Write unit tests for complex logic**
   ```rego
   # infra/opa/policies/travel/policy_test.rego
   test_suspended_persona_denied {
     not allow with input as {
       "resource": {"properties": {"owner": {"persona_status": "suspended"}}},
       # ... rest of input
     }
   }
   ```

**Test locally before deploying**
   ```bash
   opa check infra/opa/policies --strict
   opa test infra/opa/policies -v
   ```

**Use descriptive commit messages**
   - Good: `policy: require active persona status, remove backward compat`
   - Bad: `update policy`

### For Operations Teams

**Monitor the audit log**
   ```bash
   tail -f logs/opa-deployments.log
   ```

**Integrate with CI/CD**
   - Run `deploy-opa-policy.sh --auto-approve` in CI pipeline
   - Trigger on merge to `main` branch
   - Alert on failures

**Set up alerting**
   - Alert on rollback events
   - Alert on repeated deployment failures
   - Monitor Cloud Run revision health

**Review audit trail regularly**
   ```bash
   # Show all deployments in last 7 days
   grep "$(date -v-7d +%Y-%m-%d)" logs/opa-deployments.log
   
   # Show all rollbacks
   grep "ROLLBACK" logs/opa-deployments.log
   ```

### For Compliance/Security Teams

**Policy changes are traceable**

- Every production policy has a git commit hash
- `git log infra/opa/policies/` shows complete change history
- `git blame` shows who changed what and when

**Deployments are audited**

- Complete audit trail in `logs/opa-deployments.log`
- Includes: who deployed (via git author), when, what version
- Rollback events are logged with reason

**Failed deployments can't reach production**

- Syntax errors caught pre-deployment
- Behavioral regressions caught by automated tests
- Automatic rollback prevents broken policies from staying live

**Rollback capability is tested**

- Every deployment validates rollback works (via failed test scenario)
- Previous policy versions are retained in Cloud Run
- Instant rollback without code changes

## Example Deployment Session

```bash
$ ./bin/deploy-opa-policy.sh

═══════════════════════════════════════════════════════════
  OPA Policy Deployment with Governance
═══════════════════════════════════════════════════════════

ℹ Running governance checks...
ℹ Validating Rego syntax...
✓ Syntax validation passed
✓ Governance checks passed
ℹ Current active revision: flowpilot-opa-00009-gc5
ℹ New version tag: b7f8a3c

Proceed with deployment? (y/N) y

ℹ Building OPA container (version: b7f8a3c)...
✓ Build completed successfully
✓ Image tagged: b7f8a3c
ℹ Deploying new revision (no traffic)...
✓ Revision deployed (no traffic)
ℹ New revision: flowpilot-opa-00010-xj2
ℹ Shifting 100% traffic to flowpilot-opa-00010-xj2...
✓ Traffic shifted to flowpilot-opa-00010-xj2

ℹ Waiting 5 seconds for service to stabilize...
ℹ Running regression tests against deployed service...
======================================================================
FlowPilot Regression Test Suite - Firebase/Cloud Run
======================================================================
[... 12 tests run ...]
✓ All regression tests passed

═══════════════════════════════════════════════════════════
✓ Deployment successful!
═══════════════════════════════════════════════════════════

Version:          b7f8a3c
Revision:         flowpilot-opa-00010-xj2
Previous:         flowpilot-opa-00009-gc5
Service URL:      https://flowpilot-opa-737191827545.us-central1.run.app

Tagged URL:       https://vb7f8a3c---flowpilot-opa-737191827545.us-central1.run.app

Recent deployment history (last 5):
  [2026-01-15T11:20:15Z] DEPLOY_START: Deploying version a3f9d2c
  [2026-01-15T11:20:45Z] DEPLOY_SUCCESS: Version a3f9d2c deployed as flowpilot-opa-00009-gc5
  [2026-01-15T11:35:12Z] DEPLOY_START: Deploying version b7f8a3c
  [2026-01-15T11:36:02Z] DEPLOY_SUCCESS: Version b7f8a3c deployed as flowpilot-opa-00010-xj2

To rollback if needed:
  gcloud run services update-traffic flowpilot-opa \
    --region=us-central1 \
    --to-revisions=flowpilot-opa-00009-gc5=100
```
## Extending the Governance Controls

### Adding Manual Approval Gate

For production environments, add a manual approval step:

```bash
# 1. Deploy to staging (no traffic)
./bin/deploy-opa-policy.sh --skip-tests

# 2. Manual testing/review

# 3. Shift traffic after approval
gcloud run services update-traffic flowpilot-opa \
  --region=us-central1 \
  --to-revisions=flowpilot-opa-00010-xj2=100
```

### Adding Slack Notifications

Integrate with Slack for deployment notifications:

```bash
# Add to audit_log function
curl -X POST $SLACK_WEBHOOK_URL \
  -H 'Content-Type: application/json' \
  -d "{\"text\":\"OPA Policy deployed: ${VERSION_TAG}\"}"
```

### Adding Policy Signing

Sign policies with GPG for tamper-proof deployments:

```bash
# Before deployment
git tag -s "policy-v${VERSION_TAG}" -m "Release ${VERSION_TAG}"
git verify-tag "policy-v${VERSION_TAG}"
```

### Adding Change Approval Workflow

Require PR approvals before merging policy changes:

```yaml
# .github/CODEOWNERS
infra/opa/policies/ @security-team @policy-reviewers
```

## Periodically Review Compliance Artifacts

The governance framework produces these compliance artifacts:

**Audit Log** (`logs/opa-deployments.log`)
- Immutable record of all deployments
- Includes timestamps, versions, outcomes

**Git History** (`git log infra/opa/policies/`)
- Complete change history
- Author, timestamp, rationale (commit message)

**Tagged Container Images**
- Every deployed policy has tagged image
- Can redeploy exact historical version

**Test Results**
- Regression test output proves policy behavior
- Captures before/after for each deployment

**Rollback Records**
- Automatic rollbacks are logged
- Shows governance controls prevented bad deployments

## Summary

FlowPilot's policy governance demonstrates:

✅ Version Control - All policies in git with commit hashes  
✅ Pre-Deployment Validation - Syntax checks and unit tests  
✅ Zero-Downtime Deployment - No service interruption  
✅ Automated Testing - 12 scenarios validate policy behavior  
✅ Automatic Rollback - Failed tests trigger instant rollback  
✅ Audit Trail - Complete deployment history logged  
✅ Rollback Capability - Previous versions always available  

This governance model ensures authorization policies can be changed safely and confidently in production environments