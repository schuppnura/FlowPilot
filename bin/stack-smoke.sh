#!/usr/bin/env bash
set -euo pipefail

# Purpose: Minimal smoke test for “is it alive” checks.
# Why: Faster than guessing which container failed.

curl -fsS "http://localhost:8004/health" >/dev/null && echo "agent_runner_api: OK" || echo "agent_runner_api: FAIL"
curl -fsS "http://localhost:8003/health" >/dev/null && echo "cumbaya_api: OK"      || echo "cumbaya_api: FAIL"
curl -fsS "http://localhost:8002/health" >/dev/null && echo "authz_api: OK"        || echo "authz_api: FAIL"
curl -fsS "http://localhost:8001/health" >/dev/null && echo "profile_api: OK"      || echo "profile_api: FAIL"

# Keycloak well-known (realm imported on startup)
curl -fsS "http://localhost:8080/realms/cumbaya/.well-known/openid-configuration" >/dev/null \
  && echo "keycloak realm: OK" || echo "keycloak realm: FAIL"

# ***REMOVED*** health endpoint (if enabled in config)
curl -kfsS "https://localhost:9494/health" >/dev/null \
  && echo "***REMOVED***: OK" || echo "***REMOVED***: FAIL"