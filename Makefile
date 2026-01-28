.PHONY: up down logs status reset smoke generate-opa-config

up:
	./bin/stack-up.sh

down:
	./bin/stack-down.sh

logs:
	./bin/stack-logs.sh

status:
	./bin/stack-status.sh

reset:
	./bin/stack-reset.sh

smoke:
	./bin/stack-smoke.sh

generate-opa-config:
	@echo "Generating OPA persona_config.json from manifest.yaml..."
	@if python3 -c "import yaml" 2>/dev/null; then \
		python3 scripts/generate-opa-persona-config.py travel; \
	else \
		echo "PyYAML not found, using Docker..."; \
		docker run --rm -v $$(pwd):/workspace -w /workspace python:3.11-alpine sh -c "pip install -q pyyaml && python3 scripts/generate-opa-persona-config.py travel"; \
	fi
	@echo "✓ Done! OPA will pick up changes automatically if running with --watch"

