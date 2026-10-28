#!/bin/bash
# Secrets and the installed compose live outside the source checkout.
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
RUNTIME="${EVOLUTION_RUNTIME_DIR:-$HOME/.config/antares-evolution}"
export EVOLUTION_ENV_FILE="$RUNTIME/.env"
DOCKER_CONTEXT="${EVOLUTION_DOCKER_CONTEXT:-colima}"
export DOCKER_CONTEXT
compose() {
  docker compose --env-file "$EVOLUTION_ENV_FILE" -f "$RUNTIME/compose.yaml" "$@"
}
case "${1:-status}" in
  start)
    for ((attempt=0; attempt<90; attempt++)); do
      if docker info >/dev/null 2>&1; then break; fi
      sleep 2
    done
    compose up -d --wait --wait-timeout 240
    ;;
  status) compose ps ;;
  logs) compose logs --tail 100 ;;
  stop) compose stop ;;
  backup)
    umask 077
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    destination="$RUNTIME/backups/$stamp"
    mkdir -p "$destination"
    # Stop only the API for a consistent DB/Redis/session snapshot; always restore it.
    trap 'compose start api >/dev/null' EXIT
    compose stop api >/dev/null
    compose exec -T postgres pg_dump -U evolution -d evolution -Fc > "$destination/postgres.dump"
    compose exec -T redis redis-cli SAVE >/dev/null
    compose run --rm --no-deps --entrypoint tar api czf - -C /evolution instances > "$destination/instances.tar.gz"
    compose cp redis:/data/dump.rdb "$destination/redis.rdb" >/dev/null
    cp "$EVOLUTION_ENV_FILE" "$RUNTIME/compose.yaml" "$destination/"
    echo "$destination"
    ;;
  *) echo "Usage: $0 {start|status|logs|stop|backup}" >&2; exit 2 ;;
esac
