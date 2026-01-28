FROM python:3.12-slim

# Build argument for deployment environment (firebase or keycloak)
ARG DEPLOYMENT_ENV=firebase

# Install ca-certificates
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY flowpilot-services/delegation-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --root-user-action=ignore --disable-pip-version-check -r /app/requirements.txt

# Shared utilities copied into the module name used by the code ("utils").
COPY flowpilot-services/shared-libraries/utils.py /app/utils.py
COPY flowpilot-services/shared-libraries/api_logging.py /app/api_logging.py

# Copy environment-specific modules
COPY flowpilot-services/shared-libraries/security_${DEPLOYMENT_ENV}.py /app/security.py
COPY flowpilot-services/shared-libraries/profile_${DEPLOYMENT_ENV}.py /app/profile.py

# Copy service code
COPY flowpilot-services/delegation-api/delegation_main.py /app/delegation_main.py
COPY flowpilot-services/delegation-api/delegation_core.py /app/delegation_core.py

# Copy environment-specific graphdb module
COPY flowpilot-services/delegation-api/graphdb_postgresql.py /app/graphdb_postgresql.py
COPY flowpilot-services/delegation-api/graphdb_sqlite.py /app/graphdb_sqlite.py

# Create symlink based on deployment environment
RUN if [ "$DEPLOYMENT_ENV" = "keycloak" ]; then \
        ln -s /app/graphdb_sqlite.py /app/graphdb.py; \
    else \
        ln -s /app/graphdb_postgresql.py /app/graphdb.py; \
    fi

# Internal container port (Cloud Run uses PORT env var, defaults to 8080)
EXPOSE 8080

CMD ["sh", "-c", "python delegation_main.py --host 0.0.0.0 --port ${PORT:-8080}"]

