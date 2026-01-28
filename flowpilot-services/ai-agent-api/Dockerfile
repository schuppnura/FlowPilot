FROM python:3.12-slim

# Build argument for deployment environment (firebase or keycloak)
ARG DEPLOYMENT_ENV=firebase

# Install ca-certificates
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY flowpilot-services/ai-agent-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --root-user-action=ignore --disable-pip-version-check -r /app/requirements.txt

COPY flowpilot-services/shared-libraries/utils.py /app/utils.py
COPY flowpilot-services/shared-libraries/api_logging.py /app/api_logging.py

# Copy environment-specific security module
COPY flowpilot-services/shared-libraries/security_${DEPLOYMENT_ENV}.py /app/security.py
COPY flowpilot-services/ai-agent-api/ai_agent_main.py /app/ai_agent_main.py
COPY flowpilot-services/ai-agent-api/ai_agent_core.py /app/ai_agent_core.py

EXPOSE 8080

CMD ["sh", "-c", "python ai_agent_main.py --host 0.0.0.0 --port ${PORT:-8080}"]
