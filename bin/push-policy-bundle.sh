#!/usr/bin/env bash
set -euo pipefail

# Purpose:
#   Build an OPA bundle (bundle.tar.gz) and push it as an OCI image to the in-stack HTTPS registry.
#
# Usage:
#   ./bin/push-policy-bundle.sh [tag]
#
# Examples:
#   ./bin/push-policy-bundle.sh dev-20251219-03
#   ./bin/push-policy-bundle.sh   # auto tag

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BUNDLE_DIR="infra/***REMOVED***/cfg/bundle"
TAG="${1:-dev-$(date +%Y%m%d-%H%M%S)}"

REGISTRY_IN_DOCKER="registry-proxy:5443"
REPO_PATH="my-org/flowpilot-policy"
IMAGE_REF="${REGISTRY_IN_DOCKER}/${REPO_PATH}:${TAG}"

echo ">>> Building OPA bundle tarball (bundle.tar.gz) from ${BUNDLE_DIR}"

docker run --rm \
  -v "${REPO_ROOT}/${BUNDLE_DIR}:/work" -w /work \
  openpolicyagent/opa:latest \
  build . -o bundle.tar.gz

echo ">>> Preparing OCI manifest config"
printf '{}' > "${REPO_ROOT}/${BUNDLE_DIR}/manifest-config.json"

echo ">>> Pushing bundle to ${IMAGE_REF} (self-signed TLS: insecure)"
docker run --rm --network flowpilot_default \
  -v "${REPO_ROOT}/${BUNDLE_DIR}:/work" -w /work \
  ghcr.io/oras-project/oras:v1.2.0 push \
  --insecure \
  "${IMAGE_REF}" \
  --manifest-config manifest-config.json:application/vnd.oci.image.config.v1+json \
  bundle.tar.gz:application/vnd.oci.image.layer.v1.tar+gzip

echo ">>> Verifying tag exists"
docker run --rm --network flowpilot_default curlimages/curl:8.5.0 -k -sS \
  "https://${REGISTRY_IN_DOCKER}/v2/${REPO_PATH}/tags/list" || true

echo ""
echo "✓ Pushed: ${IMAGE_REF}"
echo "Next: set ***REMOVED*** bundle resource to '${REPO_PATH}:${TAG}' (or fully-qualified) and restart ***REMOVED***."