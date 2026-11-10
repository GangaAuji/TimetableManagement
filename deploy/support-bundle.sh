#!/usr/bin/env bash
# Diagnosis archive for a support request. Not a backup: no dumps, uploads, or secrets.
#
#   sudo -u timetable deploy/support-bundle.sh [output.zip]
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/timetable/app}"
VENV_DIR="${VENV_DIR:-/opt/timetable/venv}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/timetable}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="${1:-$APP_DIR/logs/timetable-support-$stamp.zip}"
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

if [[ -f "$APP_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$APP_DIR/.env"
  set +a
fi
export FLASK_APP="${FLASK_APP:-wsgi:app}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/timetable}"

(
  cd "$APP_DIR"
  "$VENV_DIR/bin/flask" support bundle --output "$workdir/report.json"
)

{
  echo "collected_at=$stamp"
  df -h || true
  if command -v systemctl >/dev/null 2>&1; then
    systemctl is-active timetable-web timetable-workers timetable-backup.timer || true
  fi
  if [[ -f "$BACKUP_DIR/LATEST" ]]; then
    echo "backup_latest=$(cat "$BACKUP_DIR/LATEST")"
    latest="$(cat "$BACKUP_DIR/LATEST")"
    if [[ -f "$BACKUP_DIR/$latest/SHA256SUMS" ]]; then
      awk '{print $2}' "$BACKUP_DIR/$latest/SHA256SUMS"
    fi
  fi
} > "$workdir/host.txt"

if command -v journalctl >/dev/null 2>&1; then
  journalctl -u timetable-web -u timetable-workers -n 200 --no-pager > "$workdir/journal.txt" || true
fi

mkdir -p "$(dirname "$destination")"
(
  cd "$APP_DIR"
  SUPPORT_WORKDIR="$workdir" SUPPORT_DESTINATION="$destination" "$VENV_DIR/bin/python" - <<'PY'
import os
import zipfile

from core.support_bundle import scrub, secret_name

workdir = os.environ['SUPPORT_WORKDIR']
destination = os.environ['SUPPORT_DESTINATION']
journal = os.path.join(workdir, 'journal.txt')
if os.path.isfile(journal):
    secrets = [value for name, value in os.environ.items() if secret_name(name) and isinstance(value, str)]
    with open(journal, encoding='utf-8', errors='replace') as handle:
        text = handle.read()
    with open(journal, 'w', encoding='utf-8') as handle:
        handle.write(scrub(text, secrets))
with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for name in sorted(os.listdir(workdir)):
        path = os.path.join(workdir, name)
        if os.path.isfile(path):
            archive.write(path, arcname=name)
PY
)
chmod 600 "$destination"
echo "Wrote $destination"
