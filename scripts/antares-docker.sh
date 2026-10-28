#!/bin/bash
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export DOCKER_CONTEXT="${ANTARES_DOCKER_CONTEXT:-colima}"
RUNTIME="${ANTARES_RUNTIME_DIR:-$HOME/.config/antares-docker}"
# Serialize startup, backup and stop, including launchd jobs that may fire together.
case "${1:-status}" in
  start|stop|backup)
    if [[ "${ANTARES_DOCKER_LOCK_HELD:-}" != "1" ]]; then
      exec python3 - "$RUNTIME" "$0" "$@" <<'PY'
import fcntl
import os
from pathlib import Path
import subprocess
import sys

with (Path(sys.argv[1]) / 'operation.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    result = subprocess.run(['/bin/bash', sys.argv[2], *sys.argv[3:]],
                            env={**os.environ, 'ANTARES_DOCKER_LOCK_HELD': '1'})
    raise SystemExit(result.returncode)
PY
    fi
    ;;
esac
compose() {
  docker compose --env-file "$RUNTIME/.env" -f "$RUNTIME/compose.yaml" --profile live "$@"
}
case "${1:-status}" in
  start)
    for ((attempt=0; attempt<90; attempt++)); do
      if docker info >/dev/null 2>&1; then break; fi
      sleep 2
    done
    compose up -d --wait --wait-timeout 180
    ;;
  status) compose ps ;;
  logs) compose logs --tail 100 ;;
  stop) compose stop ;;
  backup) exec python3 "$RUNTIME/docker-backup.py" ;;
  *) echo "Usage: $0 {start|status|logs|stop|backup}" >&2; exit 2 ;;
esac
