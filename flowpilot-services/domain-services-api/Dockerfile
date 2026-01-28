FROM python:3.12-slim

# Build argument for deployment environment (firebase or keycloak)
ARG DEPLOYMENT_ENV=firebase

# Install ca-certificates
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY flowpilot-services/domain-services-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --root-user-action=ignore --disable-pip-version-check -r /app/requirements.txt

# Shared utilities copied into the module name used by the code ("utils").
COPY flowpilot-services/shared-libraries/utils.py /app/utils.py
COPY flowpilot-services/shared-libraries/api_logging.py /app/api_logging.py

# Copy environment-specific security module
COPY flowpilot-services/shared-libraries/security_${DEPLOYMENT_ENV}.py /app/security.py
COPY flowpilot-services/domain-services-api/domain_services_main.py /app/domain_services_main.py
COPY flowpilot-services/domain-services-api/domain_services_core.py /app/domain_services_core.py
COPY flowpilot-services/domain-services-api/template_loader.py /app/template_loader.py

# Copy data directory with trip templates
COPY data /data

# Internal container port (Cloud Run uses PORT env var, defaults to 8080)
EXPOSE 8080

CMD ["sh", "-c", "python domain_services_main.py --host 0.0.0.0 --port ${PORT:-8080}"]
