# FlowPilot Documentation

This directory contains the source files for the FlowPilot documentation site, built with [MkDocs Material](https://squidfunk.github.io/mkdocs-material/).

## Local Development

### Serve locally

```bash
./serve-docs.sh
```

Or directly:

```bash
mkdocs serve
```

The documentation will be available at http://127.0.0.1:8000

### Build static site

```bash
mkdocs build
```

Output will be in the `site/` directory.

## Deployment

### Deploy to GitHub Pages

```bash
./deploy-docs.sh
```

Or directly:

```bash
mkdocs gh-deploy
```

## Structure

```
docs/
├── index.md                    # Homepage
├── getting-started/            # Getting started guides
│   ├── quick-start.md
│   ├── local-development.md
│   └── gcp-deployment.md
├── architecture/               # Architecture documentation
│   ├── overview.md
│   ├── authorization.md
│   ├── security.md
│   ├── services.md
│   └── authentication.md
├── deployment/                 # Deployment guides
│   ├── local.md
│   ├── gcp.md
│   └── environment.md
├── development/                # Development guides
│   ├── policies.md
│   ├── testing.md
│   ├── commands.md
│   └── troubleshooting.md
├── api/                        # API reference (with OpenAPI embeds)
│   ├── authz.md
│   ├── domain-services.md
│   ├── delegation.md
│   └── ai-agent.md
├── guides/                     # How-to guides
│   ├── personas.md
│   ├── delegations.md
│   └── opa-policies.md
└── contributing/               # Contributing documentation
    ├── code-of-conduct.md
    ├── contributing.md
    └── security.md
```

## Configuration

Documentation configuration is in `mkdocs.yml` at the project root.

## Contributing

To add new documentation pages:

1. Create a new `.md` file in the appropriate directory
2. Add it to the `nav` section in `mkdocs.yml`
3. Test locally with `mkdocs serve`
4. Commit and push (GitHub Pages will auto-deploy if configured)
