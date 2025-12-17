FROM python:3.12-slim

WORKDIR /app

COPY services/flowpilot-authz-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/shared-utils.py /app/utils.py
COPY services/shared_auth.py /app/shared_auth.py
COPY services/shared-sanitizer.py /app/sanitizer.py
COPY services/flowpilot-authz-api/main.py /app/main.py
COPY services/flowpilot-authz-api/core.py /app/core.py

EXPOSE 8002

CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8002"]