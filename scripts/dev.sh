#!/usr/bin/env bash
# Sobe backend e frontend localmente, sem Docker. Ctrl+C encerra os dois.
# Portas próprias (5002/3002) para não colidir com outros projetos locais.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_PORT="${API_PORT:-5002}"
WEB_PORT="${WEB_PORT:-3002}"
trap 'kill 0' EXIT
(cd "$ROOT/backend" && .venv/bin/flask --app run db upgrade && .venv/bin/flask --app run run --host 127.0.0.1 --port "$API_PORT" --debug) &
(cd "$ROOT/frontend" && FLASK_API_URL="http://127.0.0.1:${API_PORT}/api/v1" COOKIE_SECURE=false npm run dev -- --port "$WEB_PORT") &
wait
