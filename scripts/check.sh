#!/usr/bin/env bash
# Lint, tests and typecheck for the whole project. Run before committing.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== backend: ruff =="
(cd backend && .venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests)
echo "== backend: pytest =="
(cd backend && .venv/bin/python -m pytest -q --cov=app --cov-report=term:skip-covered)
echo "== frontend: typecheck + gateway tests =="
(cd frontend && npm run -s typecheck && npm run -s test:gateway)
