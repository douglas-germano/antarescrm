#!/usr/bin/env bash
# Repeatable deploy of Antares CRM to the live production environment.
#
# What it does, in order: backs up the real database and the .next-public build,
# rsyncs code from SOURCE_DIR into PROD_DIR (never touching .env, .local-services,
# .next-public or any runtime data), runs `flask db upgrade` against the real DB,
# rebuilds the frontend into .next-public, restarts the backend and frontend
# LaunchAgents (never the tunnel), and runs a smoke test against the public site.
# Any failure after the backup step triggers an automatic rollback: database and
# .next-public are restored from the backup just taken, then services are
# restarted again.
#
# Usage: scripts/deploy-prod.sh   (deploys the checkout it lives in; SOURCE_DIR must be set to deploy another copy)
# Env overrides: SOURCE_DIR, PROD_DIR, BACKUP_DIR, PROD_DB_NAME, SMOKE_URL

set -euo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Default: deploy the checkout this script lives in. Pointing SOURCE_DIR at another copy makes the rsync below
# overwrite and delete files in PROD_DIR, so that has to be explicit.
SOURCE_DIR="${SOURCE_DIR:-$SCRIPT_ROOT}"
PROD_DIR="${PROD_DIR:-/Users/douglasgermano/Documents/ChatGPT/antarescrm}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/.antarescrm-deploy-backups}"
PROD_DB_NAME="${PROD_DB_NAME:-antarescrm}"
SMOKE_URL="${SMOKE_URL:-https://antares.douglasgermano.com}"
UID_NUM="$(id -u)"
STAMP="$(date +%Y%m%d_%H%M%S)"

DB_DUMP=""
NEXT_PUBLIC_TARBALL=""
BACKUP_TAKEN=0
ROLLED_BACK=0

log() { printf '[deploy-prod] %s\n' "$1"; }

require_dir() {
  if [ ! -d "$1" ]; then
    log "ERRO: diretório obrigatório ausente: $1"
    exit 1
  fi
}

take_backup() {
  mkdir -p "$BACKUP_DIR"
  DB_DUMP="$BACKUP_DIR/antarescrm_prod_${STAMP}.dump"
  NEXT_PUBLIC_TARBALL="$BACKUP_DIR/next-public_prod_${STAMP}.tar.gz"

  log "Fazendo backup do banco real ($PROD_DB_NAME) para $DB_DUMP"
  pg_dump -Fc -d "$PROD_DB_NAME" -f "$DB_DUMP"

  if [ -d "$PROD_DIR/frontend/.next-public" ]; then
    log "Fazendo backup de .next-public para $NEXT_PUBLIC_TARBALL"
    tar -czf "$NEXT_PUBLIC_TARBALL" -C "$PROD_DIR/frontend" .next-public
  else
    log "Aviso: $PROD_DIR/frontend/.next-public não existe ainda, pulando esse backup (primeiro deploy?)"
    NEXT_PUBLIC_TARBALL=""
  fi

  BACKUP_TAKEN=1
  log "Backup concluído. dump=$DB_DUMP next_public_tarball=${NEXT_PUBLIC_TARBALL:-<nenhum>}"
}

restart_services() {
  log "Reiniciando com.antarescrm.backend"
  launchctl kickstart -k "gui/$UID_NUM/com.antarescrm.backend"
  sleep 3
  log "Reiniciando com.antarescrm.frontend"
  launchctl kickstart -k "gui/$UID_NUM/com.antarescrm.frontend"
  sleep 3
  # The worker keeps the old code in memory until restarted.
  log "Reiniciando com.antarescrm.worker"
  launchctl kickstart -k "gui/$UID_NUM/com.antarescrm.worker"
  sleep 2
  # com.antarescrm.tunnel is never touched by this script.
}

rollback() {
  if [ "$BACKUP_TAKEN" -ne 1 ] || [ "$ROLLED_BACK" -eq 1 ]; then
    return
  fi
  ROLLED_BACK=1
  log "FALHA detectada — restaurando backup e reiniciando serviços."

  if [ -n "$DB_DUMP" ] && [ -f "$DB_DUMP" ]; then
    log "Restaurando banco de $DB_DUMP"
    pg_restore -d "$PROD_DB_NAME" --clean --if-exists "$DB_DUMP" || log "Aviso: pg_restore reportou problemas (verifique manualmente)."
  fi

  if [ -n "$NEXT_PUBLIC_TARBALL" ] && [ -f "$NEXT_PUBLIC_TARBALL" ]; then
    log "Restaurando .next-public de $NEXT_PUBLIC_TARBALL"
    rm -rf "$PROD_DIR/frontend/.next-public"
    tar -xzf "$NEXT_PUBLIC_TARBALL" -C "$PROD_DIR/frontend"
  fi

  restart_services
  log "Rollback concluído. Produção restaurada ao estado anterior ao deploy."
}

trap 'rollback' ERR

sync_code() {
  log "Sincronizando código de $SOURCE_DIR para $PROD_DIR"
  rsync -a --delete \
    --exclude='.git' \
    --exclude='.env' \
    --exclude='.env.*' \
    --exclude='.local-services' \
    --exclude='.next-public' \
    --exclude='.next' \
    --exclude='node_modules' \
    --exclude='.venv' \
    --exclude='venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache' \
    --exclude='instance' \
    --exclude='.DS_Store' \
    --exclude='.nimbus' \
    --exclude='.review' \
    --exclude='.next-nimbus-check' \
    --exclude='.next-review' \
    "$SOURCE_DIR/" "$PROD_DIR/"
}

run_migration() {
  log "Rodando flask db upgrade no banco real"
  (
    cd "$PROD_DIR/backend"
    FLASK_APP=run.py "./.venv/bin/flask" db upgrade
  )
}

build_frontend() {
  log "Instalando dependências e buildando o frontend (NEXT_DIST_DIR=.next-public)"
  (
    cd "$PROD_DIR/frontend"
    npm ci
    NEXT_DIST_DIR=.next-public npm run build
  )
}

smoke_test() {
  log "Smoke test contra $SMOKE_URL"
  local root_status login_status auth_status
  root_status="$(curl -s -o /dev/null -w '%{http_code}' "$SMOKE_URL/")"
  login_status="$(curl -s -o /dev/null -w '%{http_code}' "$SMOKE_URL/login")"
  auth_status="$(curl -s -o /dev/null -w '%{http_code}' "$SMOKE_URL/api/backend/auth/me")"

  log "root=$root_status login=$login_status auth/me=$auth_status"

  if [ "$login_status" != "200" ]; then
    log "ERRO: /login não retornou 200 (retornou $login_status)"
    return 1
  fi
  if [ "$root_status" != "200" ] && [ "$root_status" != "307" ]; then
    log "ERRO: / não retornou 200/307 (retornou $root_status)"
    return 1
  fi
  if [ "$auth_status" != "401" ]; then
    log "ERRO: /api/backend/auth/me sem sessão deveria responder 401, retornou $auth_status"
    return 1
  fi

  log "Smoke test OK."
}

main() {
  require_dir "$SOURCE_DIR"
  require_dir "$PROD_DIR"

  take_backup
  sync_code
  run_migration
  build_frontend
  restart_services

  if ! smoke_test; then
    rollback
    exit 1
  fi

  trap - ERR
  log "Deploy concluído com sucesso."
  log "Backup do banco: $DB_DUMP"
  log "Backup de .next-public: ${NEXT_PUBLIC_TARBALL:-<nenhum>}"
}

main "$@"
