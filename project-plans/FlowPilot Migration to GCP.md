# FlowPilot GCP Migration Plan
## Overview
Migrate FlowPilot's microservices architecture from local Docker Compose to Google Cloud Platform using Cloud Run for services, Cloud SQL for databases, and Secret Manager for secrets.
## Current State
FlowPilot runs locally with:
* 4 Python FastAPI services (authz-api, delegation-api, domain-services-api, ai-agent-api) on ports 8002-8005
* OPA policy engine (port 8181)
* Keycloak OIDC provider (ports 8080/8443)
* SQLite database for delegation-api
* Docker Compose orchestration with service discovery via container names
* Local TLS certificates using mkcert
* Environment variables from .env file and docker-compose.yml
* Shared libraries copied at build time into each container
## Target Architecture
### Compute
* **Cloud Run** for all microservices (authz-api, delegation-api, domain-services-api, ai-agent-api, OPA)
* Auto-scaling based on traffic
* Internal service-to-service communication via Cloud Run URLs
* Public ingress only for domain-services-api (API gateway pattern)
### Identity & Access
* **Cloud Identity Platform** or **Firebase Auth** to replace Keycloak (or run Keycloak on Cloud Run/GKE)
* **Secret Manager** for sensitive credentials (client secrets, JWT keys)
* **Workload Identity** for service-to-service authentication
### Data
* **Cloud SQL (PostgreSQL)** to replace SQLite for delegation-api
* Persistent volume for Keycloak data if self-hosting
### Networking
* **Cloud Load Balancer** with TLS termination
* **VPC** for internal service communication
* **Cloud Endpoints** or **API Gateway** for external API management
### Observability
* **Cloud Logging** for centralized logs (already JSON structured)
* **Cloud Monitoring** for metrics and alerting
* **Cloud Trace** for distributed tracing
### Configuration
* **Secret Manager** for secrets
* **Environment variables** in Cloud Run for non-sensitive config
* **Artifact Registry** for container images
## Migration Strategy
### Phase 1: Infrastructure Preparation
**1.1 GCP Project Setup**
* Create or configure GCP project: `vision-course-476214` (already exists)
* Enable required APIs:
    * Cloud Run API
    * Cloud SQL Admin API
    * Secret Manager API
    * Artifact Registry API
    * Cloud Build API
    * Cloud Logging API
    * VPC Access API
    * Certificate Manager API
* Set up billing alerts and quotas
**1.2 Artifact Registry**
* Create Docker repository in Artifact Registry:
    * `us-central1-docker.pkg.dev/vision-course-476214/flowpilot`
* Configure Docker authentication: `gcloud auth configure-docker us-central1-docker.pkg.dev`
**1.3 Networking**
* Create VPC network for internal communication (or use default VPC)
* Create VPC Connector for Cloud Run to access Cloud SQL
* Configure firewall rules for service-to-service communication
**1.4 Secrets Management**
* Migrate secrets from .env to Secret Manager:
    * `KEYCLOAK_ADMIN_USERNAME`
    * `KEYCLOAK_ADMIN_PASSWORD`
    * `KEYCLOAK_CLIENT_SECRET`
    * `AGENT_CLIENT_SECRET`
* Create service account with Secret Manager access
* Grant Cloud Run services access to secrets
### Phase 2: Database Migration
**2.1 Cloud SQL Setup**
* Create PostgreSQL instance:
    * Version: PostgreSQL 15
    * Region: us-central1 (or preferred region)
    * Machine type: db-f1-micro (development) or db-custom-2-7680 (production)
    * Storage: 10GB SSD with automatic increases
    * High availability: Enable for production
* Create database: `flowpilot_delegations`
* Create database user with strong password (store in Secret Manager)
* Enable Cloud SQL Auth proxy or Private IP
**2.2 Schema Migration**
* Export existing SQLite schema from delegation-api
* Convert schema to PostgreSQL-compatible SQL
* Create migration script using SQLAlchemy or raw SQL
* Test migration with sample data locally using PostgreSQL container
**2.3 Code Updates**
* Update delegation-api database connection:
    * Replace SQLite connection string with PostgreSQL
    * Add Cloud SQL Python connector or use unix socket
    * Update requirements.txt: add `psycopg2-binary`, `cloud-sql-python-connector`
* Update environment variables for database connection
* Test locally with PostgreSQL before deploying
### Phase 3: Identity Provider Migration
**Option A: Keep Keycloak (Recommended for minimal code changes)**
* Deploy Keycloak on Cloud Run with persistent Cloud SQL backend
* Configure custom domain and TLS certificate via Certificate Manager
* Update Keycloak configuration for cloud environment
* Update JWKS_URI, ISSUER, TOKEN_URL in all services
**Option B: Migrate to Cloud Identity Platform**
* Create Firebase project linked to GCP project
* Configure OIDC providers and custom claims
* Migrate users from Keycloak (export/import)
* Update all services to use Firebase Auth:
    * Replace JWT validation with Firebase Admin SDK
    * Update token acquisition flows
    * Map Keycloak personas to Firebase custom claims
* This requires significant code changes across all services
**Recommendation:** Start with Option A (keep Keycloak) for faster migration, plan Option B as a future optimization.
### Phase 4: Container Preparation
**4.1 Dockerfile Updates**
For each service (authz-api, delegation-api, domain-services-api, ai-agent-api):
* Remove mkcert CA certificate dependencies (Cloud Run handles TLS)
* Update certificate handling for managed certificates
* Ensure WORKDIR and file paths are consistent
* Optimize image size (multi-stage builds if needed)
* Update health check endpoints to return 200 OK
**4.2 OPA Container**
* Create Dockerfile for OPA with policies baked in:
    * Base image: `openpolicyagent/opa:latest`
    * COPY policies from `infra/opa/policies/` to `/policies`
    * CMD: `["run", "--server", "--addr", "0.0.0.0:8080"]`
* Note: Cloud Run expects port 8080, so change OPA from 8181 to 8080
**4.3 Environment Variable Updates**
Replace localhost and container name references:
* `OPA_URL`: From `http://opa:8181` to Cloud Run service URL
* `DELEGATION_API_BASE_URL`: From `http://flowpilot-delegation-api:8000` to Cloud Run URL
* `AUTHZ_BASE_URL`: From `http://flowpilot-authz-api:8000` to Cloud Run URL
* `WORKFLOW_BASE_URL`: From `http://flowpilot-domain-services-api:8000` to Cloud Run URL
* `KEYCLOAK_JWKS_URI`: From `https://keycloak:8443/...` to public Keycloak URL
* `KEYCLOAK_ISSUER`: From `https://localhost:8443/...` to public Keycloak URL
* `KEYCLOAK_TOKEN_URL`: From `https://keycloak:8443/...` to public Keycloak URL
* `HTTP_VERIFY_TLS`: Change from `false` to `true` (Cloud Run uses valid certificates)
* `VERIFY_TLS`: Change from `false` to `true`
### Phase 5: Build and Push Images
**5.1 Build Images**
For each service, build multi-platform images:
```warp-runnable-command
cd /Users/Me/Documents/Python/FlowPilot
# Build authz-api
docker build -f flowpilot-services/authz-api/Dockerfile \
  -t us-central1-docker.pkg.dev/vision-course-476214/flowpilot/authz-api:latest \
  --platform linux/amd64 .
# Build delegation-api
docker build -f flowpilot-services/delegation-api/Dockerfile \
  -t us-central1-docker.pkg.dev/vision-course-476214/flowpilot/delegation-api:latest \
  --platform linux/amd64 .
# Build domain-services-api
docker build -f flowpilot-services/domain-services-api/Dockerfile \
  -t us-central1-docker.pkg.dev/vision-course-476214/flowpilot/domain-services-api:latest \
  --platform linux/amd64 .
# Build ai-agent-api
docker build -f flowpilot-services/ai-agent-api/Dockerfile \
  -t us-central1-docker.pkg.dev/vision-course-476214/flowpilot/ai-agent-api:latest \
  --platform linux/amd64 .
# Build OPA (create new Dockerfile)
docker build -f infra/opa/Dockerfile \
  -t us-central1-docker.pkg.dev/vision-course-476214/flowpilot/opa:latest \
  --platform linux/amd64 .
```
**5.2 Push Images**
```warp-runnable-command
docker push us-central1-docker.pkg.dev/vision-course-476214/flowpilot/authz-api:latest
docker push us-central1-docker.pkg.dev/vision-course-476214/flowpilot/delegation-api:latest
docker push us-central1-docker.pkg.dev/vision-course-476214/flowpilot/domain-services-api:latest
docker push us-central1-docker.pkg.dev/vision-course-476214/flowpilot/ai-agent-api:latest
docker push us-central1-docker.pkg.dev/vision-course-476214/flowpilot/opa:latest
```
### Phase 6: Deploy to Cloud Run
**Deployment Order** (bottom-up dependency order):
1. OPA (no dependencies)
2. Delegation-API (depends on Cloud SQL + OPA indirectly)
3. AuthZ-API (depends on OPA, Delegation-API)
4. Domain-Services-API (depends on AuthZ-API, Delegation-API)
5. AI-Agent-API (depends on Domain-Services-API, AuthZ-API)
**6.1 Deploy OPA**
```warp-runnable-command
gcloud run deploy flowpilot-opa \
  --image us-central1-docker.pkg.dev/vision-course-476214/flowpilot/opa:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated=false \
  --ingress internal \
  --memory 512Mi \
  --cpu 1 \
  --port 8080
```
Note the service URL: `https://flowpilot-opa-<hash>-uc.a.run.app`
**6.2 Deploy Delegation-API**
```warp-runnable-command
gcloud run deploy flowpilot-delegation-api \
  --image us-central1-docker.pkg.dev/vision-course-476214/flowpilot/delegation-api:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated=false \
  --ingress internal \
  --memory 512Mi \
  --cpu 1 \
  --port 8000 \
  --add-cloudsql-instances <CLOUD_SQL_CONNECTION_NAME> \
  --set-env-vars DB_PATH=/cloudsql/<connection-name> \
  --set-secrets KEYCLOAK_CLIENT_SECRET=KEYCLOAK_CLIENT_SECRET:latest,AGENT_CLIENT_SECRET=AGENT_CLIENT_SECRET:latest \
  --set-env-vars KEYCLOAK_JWKS_URI=<keycloak-url>,KEYCLOAK_ISSUER=<issuer>,ENABLE_API_LOGGING=1
```
**6.3 Deploy AuthZ-API**
```warp-runnable-command
gcloud run deploy flowpilot-authz-api \
  --image us-central1-docker.pkg.dev/vision-course-476214/flowpilot/authz-api:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated=false \
  --ingress internal \
  --memory 1Gi \
  --cpu 2 \
  --port 8000 \
  --set-env-vars OPA_URL=<opa-service-url>,DELEGATION_API_BASE_URL=<delegation-api-url> \
  --set-secrets AGENT_CLIENT_SECRET=AGENT_CLIENT_SECRET:latest \
  --set-env-vars KEYCLOAK_JWKS_URI=<keycloak-url>,KEYCLOAK_ISSUER=<issuer>,HTTP_VERIFY_TLS=true
```
**6.4 Deploy Domain-Services-API**
```warp-runnable-command
gcloud run deploy flowpilot-domain-services-api \
  --image us-central1-docker.pkg.dev/vision-course-476214/flowpilot/domain-services-api:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated=false \
  --ingress all \
  --memory 512Mi \
  --cpu 1 \
  --port 8000 \
  --set-env-vars AUTHZ_BASE_URL=<authz-api-url>,DELEGATION_API_BASE_URL=<delegation-api-url> \
  --set-secrets AGENT_CLIENT_SECRET=AGENT_CLIENT_SECRET:latest \
  --set-env-vars KEYCLOAK_TOKEN_URL=<keycloak-token-url>,ENABLE_API_LOGGING=1
```
Note: This service has `--ingress all` as it serves external requests.
**6.5 Deploy AI-Agent-API**
```warp-runnable-command
gcloud run deploy flowpilot-ai-agent-api \
  --image us-central1-docker.pkg.dev/vision-course-476214/flowpilot/ai-agent-api:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated=false \
  --ingress internal \
  --memory 512Mi \
  --cpu 1 \
  --port 8000 \
  --set-env-vars WORKFLOW_BASE_URL=<domain-services-url>,AUTHZ_BASE_URL=<authz-api-url> \
  --set-secrets AGENT_CLIENT_SECRET=AGENT_CLIENT_SECRET:latest \
  --set-env-vars AGENT_SUB=agent-runner,VERIFY_TRAVELER_TOKEN=false
```
**6.6 Deploy Keycloak (if self-hosting)**
```warp-runnable-command
gcloud run deploy flowpilot-keycloak \
  --image quay.io/keycloak/keycloak:26.4.7 \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated=true \
  --ingress all \
  --memory 1Gi \
  --cpu 2 \
  --port 8080 \
  --add-cloudsql-instances <keycloak-db-connection> \
  --set-env-vars KC_DB=postgres,KC_DB_URL=<jdbc-url> \
  --set-secrets KC_DB_PASSWORD=KEYCLOAK_DB_PASSWORD:latest \
  --command start \
  --args="--optimized,--hostname-strict=false"
```
Note: Configure custom domain and TLS for production.
### Phase 7: Service-to-Service Authentication
**7.1 Configure IAM**
Grant Cloud Run Invoker role between services:
```warp-runnable-command
# Grant authz-api permission to call delegation-api and OPA
gcloud run services add-iam-policy-binding flowpilot-delegation-api \
  --member=serviceAccount:<authz-sa>@vision-course-476214.iam.gserviceaccount.com \
  --role=roles/run.invoker
# Repeat for all service dependencies
```
**7.2 Update Service Code**
Add Cloud Run authentication headers:
```python
import google.auth.transport.requests
import google.auth
# Get identity token for service-to-service calls
auth_req = google.auth.transport.requests.Request()
credentials, project = google.auth.default()
if hasattr(credentials, 'id_token'):
    credentials.refresh(auth_req)
    id_token = credentials.id_token
else:
    # Use service account impersonation
    id_token = ...
headers = {
    "Authorization": f"Bearer {id_token}",
    "Content-Type": "application/json"
}
```
Alternatively, use `google-auth` library with automatic token management.
### Phase 8: Testing and Validation
**8.1 Health Checks**
Verify all services are running:
```warp-runnable-command
curl https://flowpilot-opa-<hash>-uc.a.run.app/health -H "Authorization: Bearer $(gcloud auth print-identity-token)"
curl https://flowpilot-delegation-api-<hash>-uc.a.run.app/health -H "Authorization: Bearer $(gcloud auth print-identity-token)"
curl https://flowpilot-authz-api-<hash>-uc.a.run.app/health -H "Authorization: Bearer $(gcloud auth print-identity-token)"
curl https://flowpilot-domain-services-api-<hash>-uc.a.run.app/health -H "Authorization: Bearer $(gcloud auth print-identity-token)"
curl https://flowpilot-ai-agent-api-<hash>-uc.a.run.app/health -H "Authorization: Bearer $(gcloud auth print-identity-token)"
```
**8.2 Integration Tests**
* Run existing integration tests from `flowpilot_testing/` against Cloud Run URLs
* Update test configuration to use production endpoints
* Verify authorization flows work end-to-end
* Test delegation chain resolution
* Test OPA policy evaluation
**8.3 Logging Verification**
* Check Cloud Logging for structured JSON logs
* Verify log correlation across services (trace IDs)
* Set up log-based metrics and alerts
**8.4 Performance Testing**
* Test cold start times (Cloud Run instances)
* Verify service-to-service latency is acceptable
* Load test with expected traffic patterns
* Monitor Cloud Run instance scaling
### Phase 9: CI/CD Pipeline (Optional)
**9.1 Cloud Build Setup**
Create `cloudbuild.yaml` for automated deployments:
```yaml
steps:
- name: 'gcr.io/cloud-builders/docker'
  args: ['build', '-f', 'flowpilot-services/authz-api/Dockerfile', 
         '-t', 'us-central1-docker.pkg.dev/vision-course-476214/flowpilot/authz-api:$SHORT_SHA', '.']
- name: 'gcr.io/cloud-builders/docker'
  args: ['push', 'us-central1-docker.pkg.dev/vision-course-476214/flowpilot/authz-api:$SHORT_SHA']
- name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
  args: ['gcloud', 'run', 'deploy', 'flowpilot-authz-api',
         '--image', 'us-central1-docker.pkg.dev/vision-course-476214/flowpilot/authz-api:$SHORT_SHA',
         '--region', 'us-central1']
```
**9.2 GitHub Actions Integration**
Create `.github/workflows/deploy.yml` for automated deployments on push to main branch.
### Phase 10: Monitoring and Operations
**10.1 Monitoring Dashboard**
* Create Cloud Monitoring dashboard with:
    * Request rate per service
    * Error rate per service
    * Latency percentiles (p50, p95, p99)
    * Instance count per service
    * CPU and memory utilization
**10.2 Alerting**
Set up alerts for:
* High error rate (>5% of requests)
* High latency (p95 > 2 seconds)
* Service unavailability
* Database connection failures
* OPA policy evaluation failures
**10.3 Cost Monitoring**
* Set up billing alerts
* Monitor Cloud Run instance hours
* Monitor Cloud SQL usage
* Optimize instance sizes based on actual usage
## Security Considerations
### Production Configuration Changes
1. **TLS Verification**: Set `HTTP_VERIFY_TLS=true` and `VERIFY_TLS=true` (remove insecure flags)
2. **Error Details**: Set `INCLUDE_ERROR_DETAILS=0` to hide internal errors in production
3. **Request Limits**: Review `MAX_REQUEST_SIZE_MB` and `MAX_STRING_LENGTH` for production workloads
4. **Secrets**: All secrets must be in Secret Manager, never in environment variables or code
5. **IAM**: Use least-privilege service accounts for each Cloud Run service
6. **Network**: Enable VPC Service Controls for additional security
7. **Audit Logging**: Enable Cloud Audit Logs for all API calls
### JWT Validation Updates
* Update JWKS caching for production (currently local JWKS validation)
* Consider using Cloud Endpoints for centralized JWT validation
* Ensure JWKS_URI is accessible from Cloud Run
### PII Protection
* Verify no PII is logged to Cloud Logging
* Review log retention policies
* Ensure compliance with GDPR/CCPA if applicable
## Rollback Strategy
### Cloud Run Rollback
Cloud Run supports instant rollback to previous revisions:
```warp-runnable-command
gcloud run services update-traffic flowpilot-authz-api \
  --to-revisions <previous-revision>=100
```
### Database Rollback
* Take Cloud SQL snapshot before schema migrations
* Test restore procedure before production deployment
* Maintain backward-compatible schema changes
### DNS/Traffic Rollback
* Use Cloud Load Balancer traffic splitting for gradual rollout
* Keep local Docker Compose stack available for emergency fallback
## Cost Estimates (Monthly)
### Development Environment
* Cloud Run: $10-50 (minimal traffic, scales to zero)
* Cloud SQL (db-f1-micro): $7-15
* Secret Manager: $0.06 per secret per month ($0.30 total)
* Artifact Registry: $0.10/GB storage
* Networking: $1-5
**Total: ~$20-80/month**
### Production Environment (low-medium traffic)
* Cloud Run: $50-200 (depends on traffic and instance size)
* Cloud SQL (db-custom-2-7680 with HA): $150-300
* Cloud Load Balancer: $18 + data processing fees
* Secret Manager: $0.30
* Artifact Registry: $1-5
* Cloud Logging: $0.50/GB ingested (first 50GB free)
* Networking: $10-50
**Total: ~$230-600/month**
## Success Criteria
* All services deployed and accessible via Cloud Run
* End-to-end authorization flow works (PEP → AuthZ → Delegation → OPA)
* Database migration successful with no data loss
* Integration tests pass against production environment
* Logs flowing to Cloud Logging with proper structure
* Service-to-service authentication working
* No PII exposed in logs or errors
* Latency within acceptable bounds (< 2s p95)
* macOS Swift client can connect to Cloud Run endpoints
## Next Steps After Migration
1. Set up custom domain and SSL certificates
2. Implement API rate limiting and quotas
3. Add distributed tracing with Cloud Trace
4. Optimize container images for faster cold starts
5. Consider migrating from Keycloak to Cloud Identity Platform
6. Implement backup and disaster recovery procedures
7. Document runbooks for common operational tasks
8. Set up staging environment for testing before production deployments
