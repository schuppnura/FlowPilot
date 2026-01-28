FROM python:3.12-slim

# Build argument for deployment environment (firebase or keycloak)
ARG DEPLOYMENT_ENV=firebase

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tini curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps
COPY flowpilot-services/persona-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --root-user-action=ignore --disable-pip-version-check -r /app/requirements.txt

# Shared libs (as top-level modules)
COPY flowpilot-services/shared-libraries/utils.py /app/utils.py
COPY flowpilot-services/shared-libraries/api_logging.py /app/api_logging.py
COPY flowpilot-services/shared-libraries/persona_config.py /app/persona_config.py

# Copy environment-specific security and profile modules
COPY flowpilot-services/shared-libraries/security_${DEPLOYMENT_ENV}.py /app/security.py
COPY flowpilot-services/shared-libraries/profile_${DEPLOYMENT_ENV}.py /app/profile.py

# App code
COPY flowpilot-services/persona-api/persona_main.py /app/persona_main.py

# Persona management code
COPY flowpilot-services/persona-api/persona_core.py /app/persona_core.py
# Copy both database implementations temporarily
COPY flowpilot-services/persona-api/personadb_firestore.py /app/personadb_firestore.py
COPY flowpilot-services/persona-api/personadb_sqlite.py /app/personadb_sqlite.py
# Copy the appropriate one as personadb.py based on DEPLOYMENT_ENV
RUN if [ "${DEPLOYMENT_ENV}" = "firebase" ]; then \
      cp /app/personadb_firestore.py /app/personadb.py; \
    else \
      cp /app/personadb_sqlite.py /app/personadb.py; \
    fi && \
    rm /app/personadb_firestore.py /app/personadb_sqlite.py

# Policy manifest (required for persona configuration)
COPY infra/opa/policies /policies

ENTRYPOINT ["tini", "--"]
CMD ["sh", "-c", "python persona_main.py --host 0.0.0.0 --port ${PORT:-8080}"]
