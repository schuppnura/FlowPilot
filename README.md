# FlowPilot

FlowPilot is a reference implementation of a small “agentic” workflow with a dedicated authorization service. The project includes:
- A Swift demo client (traveller and travel agent personas)
- Backend microservices (services API, AI agent API, authz API)
- A local OIDC provider (Keycloak) for issuing bearer tokens
- An OPA (Open Policy Agent) policy engine that evaluates Rego policies

This repository previously experimented with ***REMOVED***, OCI policy bundles, and an HTTPS registry proxy. That approach has been removed from the default developer workflow in favor of a simpler, more transparent OPA server-mode setup.

## Architecture at a glance

1. PDP: OPA server for ABAC. It evaluates relationship-based delegation and permissions via an authorization graph.

2. An AuthZ integration layer that acts as integration beteeen PEP and PDP and maintaing the graph for workflow ownership relations enriches requests with profile attributes.

3. PEP using PDP authorization as a domain backend that owns workflow state (system of record) in the context of a travel agent use case: autonomous booking is gated by attribute-based policy conditions (consent, cost, advance days, airline risk) after delegation is verified.

4. Keycloak as the IdP with OIDC Authorization Code + PKCE for the desktop client and Client Credntails for Agentic AI servers. It shows end-to-end authentication: bearer token validation across all services with service-to-service authentication.

5. An Agentic AI server that executes workflow items item-by-item to produce mixed allow/deny outcomes in a single run.

## Security & Privacy

FlowPilot adopts a strict privacy discipline: no PII exposure to the LLM and no PII handling in the domain backend beyond `sub` (UUID).

All API endpoints (except health) verify and sanitize the inoput, in order to thwart known attack types.
All API endpoints (except health) verify and validate the access token, to ensure only authenticated calls are accepted and to ensure the access token is issued by the expected IpD and contains the expected fields.


- `flowpilot-authz-api` is the authorization façade used by other services and clients.
  - It validates access tokens and extracts identity context.
  - It calls OPA to evaluate Rego policies.
  - It returns an allow/deny decision (plus optional reasons/obligations depending on the endpoint).

- `opa` is a plain OPA container started in server mode.
  - Policies are mounted from the repository.
  - Policies can be edited locally and reloaded via container restart (or via `--watch`, depending on your OPA args).

## Quick start (Docker Compose)

From the repo root:

```bash
docker compose up -d --build
docker compose ps
```

To see OPA startup logs:

```bash
docker compose logs -f opa
```

To see authz API logs:

```bash
docker compose logs -f flowpilot-authz-api
```

### Verify OPA is reachable (inside the compose network)

This avoids host-port assumptions and is the most reliable check:

```bash
docker run --rm --network flowpilot_default curlimages/curl:8.5.0 -sS   http://opa:8181/health
```

Expected output is JSON indicating healthy status (exact fields vary by OPA version).

### Verify the policy is loaded

Example: evaluate the `auto_book` policy directly in OPA (the repository includes `auto_book.rego` under the mounted policies directory).

```bash
docker run --rm --network flowpilot_default curlimages/curl:8.5.0 -sS   -H "Content-Type: application/json"   -d '{
    "input": {
      "user": {
        "auto_book_consent": true,
        "auto_book_max_cost_eur": 300,
        "auto_book_min_advance_hours": 24,
        "risk_profile": "medium"
      },
      "trip": {
        "total_cost_eur": 250,
        "departure_hours_from_now": 48,
        "risk_level": "low"
      }
    }
  }'   http://opa:8181/v1/data/auto_book/allow
```

Expected result:

```json
{"result":true}
```

If you see `{"result":false}`, check the input payload against the policy conditions and/or query the policy reason:

```bash
docker run --rm --network flowpilot_default curlimages/curl:8.5.0 -sS   -H "Content-Type: application/json"   -d '{"input":{...}}'   http://opa:8181/v1/data/auto_book/reason
```

## Policy development workflow

### Policy location

The compose file mounts a policy directory into the OPA container. Recommended layout:

- `infra/opa/policies/`
  - `auto_book.rego`
  - other policy modules
- `infra/opa/data/` (optional)
  - static data documents consumed by policy

If you prefer to keep policies alongside the authz service, that also works as long as the OPA container mounts the correct path.

### Validate and test policies locally

Run tests inside the OPA container:

```bash
docker compose exec -T opa opa test /policies -v
```

(Adjust `/policies` if your compose mounts to a different path.)

### Reload policies

The simplest workflow is a container restart:

```bash
docker compose restart opa
```

If you want automatic reload on file changes, you can run OPA with `--watch` in the compose `command:` (see `docker-compose.yml`), but note that file watching behavior depends on the container filesystem and your Docker Desktop configuration.

## flowpilot-authz-api integration

`flowpilot-authz-api` talks to OPA over HTTP. In Compose, the correct way to refer to OPA is via the service name (`opa`), not `127.0.0.1`:

- `OPA_URL=http://opa:8181`
- Policy package/rule typically:
  - package: `auto_book`
  - decision rule: `allow` (boolean)

If you expose authz-api to the host, call it using its published port (see `docker-compose.yml`). The OpenAPI specification is available in `flowpilot-authz.openapi.yaml`.

## Troubleshooting

### OPA is running but requests fail

- Confirm you are calling the correct network endpoint:
  - Inside compose network: `http://opa:8181/...`
  - From the host: only works if the OPA service publishes a host port.

### `MANIFEST_UNKNOWN`, registry, HTTPS proxy errors (legacy)

Those errors are typically caused by OCI/registry-based policy distribution attempts (OCI manifest types, Accept headers, TLS, namespace rewrite rules). The current default FlowPilot workflow does not require an OCI registry, nginx registry proxy, or ***REMOVED***.

If you still have legacy services in your compose file (registry, registry-proxy, ***REMOVED***), remove or disable them so they cannot interfere with your network and ports.

### Authz API cannot reach OPA

If you see connection errors in `flowpilot-authz-api` logs:
- Ensure the `opa` service is running: `docker compose ps`
- Ensure the authz container uses `OPA_URL=http://opa:8181` (service name routing), not `localhost`.

## Repository structure (selected)

- `services/flowpilot-authz-api/` authorization API
- `services/flowpilot-services-api/` business APIs
- `services/flowpilot-ai-agent-api/` AI agent API
- `services/shared-libraries/` shared Python utilities
- `infra/opa/` OPA policy and data (recommended)
- `infra/keycloak/` Keycloak realm config and certs

## Notes

This repo is intended as a practical reference implementation. The design goal for policy loading is to keep the developer loop short and observable:
- edit Rego locally
- restart (or watch) OPA
- call OPA directly to validate
- call flowpilot-authz-api to validate end-to-end behavior
