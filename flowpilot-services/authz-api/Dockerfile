FROM python:3.12-slim

# Build argument for deployment environment (firebase or keycloak)
ARG DEPLOYMENT_ENV=firebase

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tini curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps
COPY flowpilot-services/authz-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --root-user-action=ignore --disable-pip-version-check -r /app/requirements.txt

# Shared libs (as top-level modules)
COPY flowpilot-services/shared-libraries/utils.py /app/utils.py
COPY flowpilot-services/shared-libraries/api_logging.py /app/api_logging.py

# Copy environment-specific modules
COPY flowpilot-services/shared-libraries/security_${DEPLOYMENT_ENV}.py /app/security.py
COPY flowpilot-services/shared-libraries/profile_${DEPLOYMENT_ENV}.py /app/profile.py

# App code
COPY flowpilot-services/authz-api/authz_main.py /app/authz_main.py
COPY flowpilot-services/authz-api/authz_core.py /app/authz_core.py
COPY flowpilot-services/authz-api/policy_manifest.py /app/policy_manifest.py

# Copy policy manifests (needed to determine which attributes to fetch)
COPY infra/opa/policies /policies

ENTRYPOINT ["tini", "--"]
CMD ["sh", "-c", "python authz_main.py --host 0.0.0.0 --port ${PORT:-8080}"]
