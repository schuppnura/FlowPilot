FROM python:3.12-slim

WORKDIR /app

COPY services/flowpilot-services-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Shared utilities copied into the module name used by the code ("utils").
COPY services/shared-libraries/utils.py /app/utils.py
COPY services/shared-libraries/security.py /app/security.py
COPY services/flowpilot-services-api/main.py /app/main.py
COPY services/flowpilot-services-api/main.py /app/main.py
COPY services/flowpilot-services-api/core.py /app/core.py
COPY services/flowpilot-services-api/template_loader.py /app/template_loader.py

# Internal container port (compose maps host 8003 -> container 8000)
EXPOSE 8000

CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000"]