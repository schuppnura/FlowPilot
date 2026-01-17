FROM openpolicyagent/opa:latest AS opa-base

# Use Python image to generate persona_config.json from manifest.yaml
FROM python:3.11-alpine AS generator

# Install PyYAML
RUN pip install --no-cache-dir pyyaml

# Copy generation script and policy manifests
COPY scripts/generate-opa-persona-config.py /tmp/generate.py
COPY infra/opa/policies /tmp/policies

# Generate persona_config.json for each policy
RUN python3 /tmp/generate.py travel && \
    echo "Generated travel persona_config.json"

# Final image with OPA and generated configs
FROM openpolicyagent/opa:latest

# Copy policies from generator stage (includes generated JSON files)
COPY --from=generator /tmp/policies /policies

# Cloud Run expects services to listen on port 8080
# OPA defaults to 8181, so we need to override the port
EXPOSE 8080

# Run OPA server on port 8080
CMD ["run", "--server", "--addr", "0.0.0.0:8080", "/policies"]
