#!/usr/bin/env bash
# Lint, tests and typecheck for the whole project. Run before committing.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== backend: ruff =="
(cd backend && .venv/bin/ruff check --config pyproject.toml ../scripts/code-graph-share.py && .venv/bin/ruff format --config pyproject.toml --check ../scripts/code-graph-share.py)
(cd backend && .venv/bin/ruff check --config pyproject.toml app tests ../scripts/dev.py ../scripts/deploy.py ../scripts/generate-api-contracts.py ../scripts/code-graph.py ../scripts/code_graph && .venv/bin/ruff format --config pyproject.toml --check app tests ../scripts/dev.py ../scripts/deploy.py ../scripts/generate-api-contracts.py ../scripts/code-graph.py ../scripts/code_graph)
echo "== backend: pytest =="
(cd backend && .venv/bin/python -m pytest -q --cov=app --cov-report=term:skip-covered --cov-fail-under=85)
echo "== frontend: typecheck + gateway tests =="
backend/.venv/bin/python scripts/generate-api-contracts.py --check
(cd frontend && npm run -s typecheck && npm run -s test:gateway)
