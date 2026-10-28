#!/usr/bin/env bash
# Default only prepares a release. Activation is explicit: activate /absolute/release/path.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ "${1:-}" == "activate" && -f "$HOME/.config/antares-docker/ACTIVE" ]]; then
  echo "O Antares está no Docker. A ativação nativa foi bloqueada para evitar duas instalações gravando em bancos diferentes. Consulte docs/DOCKER-OPERACAO.md." >&2
  exit 2
fi
exec "$ROOT/backend/.venv/bin/python" "$ROOT/scripts/deploy.py" "$@"
