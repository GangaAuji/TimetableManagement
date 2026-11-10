#!/usr/bin/env bash
# Upgrade one installation. Backs up first, then migrates, then requires /health to be healthy.
#
#   sudo deploy/upgrade.sh
#
# Docker (from the repository, with deploy/docker.env):
#   TIMETABLE_RUNTIME=docker deploy/upgrade.sh
#
# A failed migration leaves the workers stopped. The printed backup stamp is the one to restore.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/timetable/app}"
SERVICE_USER="${SERVICE_USER:-timetable}"
VENV_DIR="${VENV_DIR:-/opt/timetable/venv}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"
RUNTIME="${TIMETABLE_RUNTIME:-systemd}"

if [[ "$RUNTIME" == docker ]]; then
  APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
  COMPOSE_FILE="${COMPOSE_FILE:-$APP_DIR/deploy/docker-compose.yml}"
  compose=(docker compose --env-file "$APP_DIR/deploy/docker.env" -f "$COMPOSE_FILE")
  if [[ -z "${HEALTH_URL+set}" || "$HEALTH_URL" == "http://127.0.0.1:8000/health" ]]; then
    http_port="$(awk -F= '$1=="HTTP_PORT" {print $2; exit}' "$APP_DIR/deploy/docker.env" 2>/dev/null | tr -d '\r[:space:]' || true)"
    http_port="${http_port:-80}"
    HEALTH_URL="http://127.0.0.1:${http_port}/health"
  fi
  echo "Backing up before the Docker upgrade."
  "${compose[@]}" exec -T web deploy/backup.sh
  stamp="$("${compose[@]}" exec -T web sh -c 'cat "${BACKUP_DIR:-/var/backups/timetable}/LATEST"' | tr -d '\r')"
  echo "Backup stamp: $stamp"
  "${compose[@]}" stop workers
  if "${compose[@]}" exec -T web sh -c 'test -n "$TENANT_REGISTRY_DB"'; then
    "${compose[@]}" exec -T web flask tenant upgrade --all
    "${compose[@]}" exec -T web sh -c 'flask tenant list | while IFS= read -r line; do case "$line" in *"	"*) flask seed run --tenant "${line%%	*}"; esac; done'
  else
    "${compose[@]}" exec -T web flask db upgrade
    "${compose[@]}" exec -T web flask seed run
  fi
  "${compose[@]}" up -d web workers nginx
  code=""
  for _ in 1 2 3 4 5 6 7 8; do
    code="$(curl -sS -o /tmp/timetable-health.json -w '%{http_code}' "$HEALTH_URL" || true)"
    if [[ "$code" == 200 || "$code" == 503 ]]; then
      break
    fi
    sleep 2
  done
  if [[ "$code" != 200 ]]; then
    echo "Health returned ${code:-none} after the upgrade. Restore the backup volume from stamp $stamp if the schema change must be undone." >&2
    cat /tmp/timetable-health.json >&2 || true
    exit 1
  fi
  echo "Upgrade finished. Backup stamp $stamp. $HEALTH_URL is healthy."
  exit 0
fi

cd "$APP_DIR"
if [[ ! -x "$VENV_DIR/bin/flask" ]]; then
  echo "No flask at $VENV_DIR/bin/flask. Run deploy/install.sh first." >&2
  exit 1
fi

code="$(curl -sS -o /dev/null -w '%{http_code}' "$HEALTH_URL" || true)"
if [[ "$code" != 200 && "$code" != 503 ]]; then
  echo "Nothing answered at $HEALTH_URL (HTTP ${code:-none}). Start timetable-web before upgrading." >&2
  exit 1
fi
if ! systemctl cat timetable-workers.service >/dev/null 2>&1; then
  echo "timetable-workers.service is not installed." >&2
  exit 1
fi

echo "Backing up before the upgrade."
sudo -u "$SERVICE_USER" "$APP_DIR/deploy/backup.sh"
stamp="$(sudo -u "$SERVICE_USER" bash -c 'set -a; source "'"$APP_DIR"'/.env"; set +a; cat "${BACKUP_DIR:-/var/backups/timetable}/LATEST"')"
echo "Backup stamp: $stamp"

systemctl stop timetable-workers
"$APP_DIR/deploy/install.sh"

run_flask() {
  sudo -u "$SERVICE_USER" bash -c "set -a; source '$APP_DIR/.env'; set +a; export FLASK_APP=wsgi:app; cd '$APP_DIR'; '$VENV_DIR/bin/flask' $*"
}

registry="$(sudo -u "$SERVICE_USER" bash -c "set -a; source '$APP_DIR/.env'; set +a; printf '%s' \"\${TENANT_REGISTRY_DB:-}\"")"
if [[ -n "$registry" ]]; then
  run_flask tenant upgrade --all
  run_flask tenant list | while IFS= read -r line; do
    case "$line" in
      *"	"*) run_flask seed run --tenant "${line%%	*}" ;;
    esac
  done
else
  run_flask db upgrade
  run_flask seed run
fi

systemctl restart timetable-web timetable-workers
code=""
for _ in 1 2 3 4 5 6 7 8; do
  code="$(curl -sS -o /tmp/timetable-health.json -w '%{http_code}' "$HEALTH_URL" || true)"
  if [[ "$code" == 200 || "$code" == 503 ]]; then
    break
  fi
  sleep 2
done
if [[ "$code" != 200 ]]; then
  echo "Health returned $code. Workers were restarted. Restore with deploy/restore.sh from stamp $stamp if the schema change must be undone." >&2
  cat /tmp/timetable-health.json >&2 || true
  exit 1
fi
echo "Upgrade finished. Backup stamp $stamp. $HEALTH_URL is healthy."
