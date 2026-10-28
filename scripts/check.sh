#!/usr/bin/env bash
# Lint, tests and typecheck for the whole project. Run before committing.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== backend: ruff =="
(cd backend && .venv/bin/ruff check --config pyproject.toml app tests ../scripts/dev.py ../scripts/deploy.py && .venv/bin/ruff format --config pyproject.toml --check app tests ../scripts/dev.py ../scripts/deploy.py)
echo "== backend: pytest =="
(cd backend && .venv/bin/python -m pytest -q --cov=app --cov-report=term:skip-covered --cov-fail-under=85)
echo "== frontend: typecheck + gateway tests =="
(cd frontend && npm run -s typecheck && npm run -s test:gateway)
