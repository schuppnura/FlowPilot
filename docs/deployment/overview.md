# Self-Hosting Overview

FlowPilot is offered as a managed service, but you can also self-host your own instance.

## Why Self-Host?

Consider self-hosting if you:

- Need full control over infrastructure
- Have strict data residency requirements
- Want to customize policies beyond what the managed service offers
- Are building a white-label solution

## Deployment Options

- **Local Development**: Docker Compose for testing and development
- **GCP Cloud Run**: Production-ready deployment on Google Cloud
- **Custom**: Deploy to any Kubernetes cluster or cloud provider

## Prerequisites

Self-hosting requires:

- Infrastructure expertise (Docker, cloud platforms)
- Security expertise (JWT validation, TLS, secrets management)
- Policy authoring expertise (Rego/OPA)

## Next Steps

For most developers, we recommend using the **managed service** at the production endpoints listed in the [Integration Guide](../getting-started/integration.md).

If you still want to self-host, see:
- [GCP Cloud Run](gcp.md) - Production deployment
- [Local Development](local.md) - Docker Compose setup

