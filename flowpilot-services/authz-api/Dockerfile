FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tini curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Keycloak CA certificate to system trust store
# Use mkcert root CA (which signed the Keycloak cert) for proper SSL verification
COPY infra/certs/mkcert-rootCA.pem /usr/local/share/ca-certificates/mkcert-rootCA.crt
RUN update-ca-certificates

WORKDIR /app

# Install deps
COPY flowpilot-services/authz-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Also create a combined certificate bundle for Python requests (certifi + mkcert CA)
# This ensures requests library can verify Keycloak's certificate
RUN python3 <<EOF
import certifi
certifi_path = certifi.where()
with open(certifi_path, 'rb') as f1, open('/usr/local/share/ca-certificates/mkcert-rootCA.crt', 'rb') as f2:
    combined = f1.read() + b'\n' + f2.read()
with open('/app/ca-bundle.crt', 'wb') as f:
    f.write(combined)
EOF

# Shared libs (as top-level modules)
COPY flowpilot-services/shared-libraries/utils.py /app/utils.py
COPY flowpilot-services/shared-libraries/security.py /app/security.py
COPY flowpilot-services/shared-libraries/api_logging.py /app/api_logging.py
COPY flowpilot-services/shared-libraries/profile.py /app/profile.py

# App code
COPY flowpilot-services/authz-api/authz_main.py /app/authz_main.py
COPY flowpilot-services/authz-api/authz_core.py /app/authz_core.py

ENTRYPOINT ["tini", "--"]
CMD ["python", "authz_main.py", "--host", "0.0.0.0", "--port", "8000"]
