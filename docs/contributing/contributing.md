# Contributing

Thanks for your interest in improving 'Authorization using AuthZEN / OPA'.

## Development setup
- Python 3.10+
- uv recommended: https://docs.astral.sh/uv/
- pre-commit hooks

```bash
uv venv
uv sync
pre-commit install
```

## Workflow
- Branch from `main`, name as `feat/...`, `fix/...`, or `docs/...`
- Write tests for new behaviour
- Run `make format lint typecheck test`
- Use conventional commits
- Open a pull request with a clear description

## Code style
- Black + Ruff, PEP8
- mypy for typing
- Avoid nested functions; explicit names
- CLI entry points for components to ease testing

## Security
When contributin, ensure you are not (accidently) sharing secrets or real PII. See `SECURITY.md`.