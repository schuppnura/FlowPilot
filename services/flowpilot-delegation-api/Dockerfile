FROM python:3.12-slim

WORKDIR /app

COPY services/flowpilot-delegation-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Shared utilities copied into the module name used by the code ("utils").
COPY services/shared-libraries/utils.py /app/utils.py
COPY services/shared-libraries/security.py /app/security.py
COPY services/shared-libraries/api_logging.py /app/api_logging.py
COPY services/flowpilot-delegation-api/main.py /app/main.py
COPY services/flowpilot-delegation-api/core.py /app/core.py
COPY services/flowpilot-delegation-api/graphdb.py /app/graphdb.py

# Internal container port (compose maps host 8005 -> container 8000)
EXPOSE 8000

CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000"]

