FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tini curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps
COPY services/flowpilot-authz-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Shared libs (as top-level modules)
COPY services/shared-libraries/utils.py /app/utils.py
COPY services/shared-libraries/security.py /app/security.py

# App code
COPY services/flowpilot-authz-api/main.py /app/main.py
COPY services/flowpilot-authz-api/core.py /app/core.py

ENTRYPOINT ["tini", "--"]
CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000"]