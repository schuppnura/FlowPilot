FROM python:3.12-slim

WORKDIR /app

COPY flowpilot-services/delegation-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Shared utilities copied into the module name used by the code ("utils").
COPY flowpilot-services/shared-libraries/utils.py /app/utils.py
COPY flowpilot-services/shared-libraries/security.py /app/security.py
COPY flowpilot-services/shared-libraries/api_logging.py /app/api_logging.py
COPY flowpilot-services/shared-libraries/profile.py /app/profile.py
COPY flowpilot-services/delegation-api/main.py /app/main.py
COPY flowpilot-services/delegation-api/core.py /app/core.py
COPY flowpilot-services/delegation-api/graphdb.py /app/graphdb.py

# Internal container port (compose maps host 8005 -> container 8000)
EXPOSE 8000

CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000"]

