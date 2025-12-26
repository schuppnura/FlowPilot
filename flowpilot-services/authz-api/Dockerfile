FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tini curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps
COPY flowpilot-services/authz-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Shared libs (as top-level modules)
COPY flowpilot-services/shared-libraries/utils.py /app/utils.py
COPY flowpilot-services/shared-libraries/security.py /app/security.py
COPY flowpilot-services/shared-libraries/api_logging.py /app/api_logging.py
COPY flowpilot-services/shared-libraries/profile.py /app/profile.py

# App code
COPY flowpilot-services/authz-api/main.py /app/main.py
COPY flowpilot-services/authz-api/core.py /app/core.py

ENTRYPOINT ["tini", "--"]
CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000"]