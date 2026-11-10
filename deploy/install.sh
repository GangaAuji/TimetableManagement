#!/usr/bin/env bash
# First install or code update on one Debian/Ubuntu VPS. Idempotent: safe to run again after `git pull`.
#
#   sudo deploy/install.sh            # from a checkout anywhere; copies nothing, works in place
#
# Layout: /opt/timetable/app (this checkout), /opt/timetable/venv, service user `timetable`.
# It does not create databases or .env: see docs/RUNBOOK.md for the steps that need secrets.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/timetable/app}"
VENV_DIR="${VENV_DIR:-/opt/timetable/venv}"
SERVICE_USER="${SERVICE_USER:-timetable}"
PYTHON="${PYTHON:-python3}"
NODE="${NODE:-npm}"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$here" != "$APP_DIR" ]]; then
  echo "This checkout is at $here but APP_DIR is $APP_DIR. Clone or move the repository to $APP_DIR (or set APP_DIR)." >&2
  exit 1
fi

if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home-dir /opt/timetable --shell /usr/sbin/nologin "$SERVICE_USER"
fi

apt-get update -qq
apt-get install -y -qq nginx mariadb-client python3-venv python3-dev build-essential default-libmysqlclient-dev pkg-config

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON" -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --quiet --upgrade pip wheel
"$VENV_DIR/bin/pip" install --quiet -r "$APP_DIR/deploy/requirements-prod.txt"

if command -v "$NODE" >/dev/null 2>&1 && [[ -f "$APP_DIR/frontend/package.json" ]]; then
  (cd "$APP_DIR/frontend" && "$NODE" ci --silent && "$NODE" run build --silent)
else
  echo "npm not found or frontend missing: the React bundle was not built." >&2
fi

mkdir -p "$APP_DIR/logs" "$APP_DIR/uploads" "$APP_DIR/static/uploads" "$APP_DIR/ml_models/models" /var/www/letsencrypt
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/logs" "$APP_DIR/uploads" "$APP_DIR/static/uploads" "$APP_DIR/ml_models/models"
if [[ -f "$APP_DIR/.env" ]]; then
  chown "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
else
  echo "No $APP_DIR/.env yet. Copy .env.example and fill it in before starting the services." >&2
fi

install -m 644 "$APP_DIR/deploy/systemd/timetable-web.service" /etc/systemd/system/
install -m 644 "$APP_DIR/deploy/systemd/timetable-workers.service" /etc/systemd/system/
install -m 644 "$APP_DIR/deploy/systemd/timetable-backup.service" /etc/systemd/system/
install -m 644 "$APP_DIR/deploy/systemd/timetable-backup.timer" /etc/systemd/system/
install -m 644 "$APP_DIR/deploy/nginx/timetable-proxy.conf" /etc/nginx/snippets/timetable-proxy.conf
if [[ ! -f /etc/nginx/sites-available/timetable.conf ]]; then
  install -m 644 "$APP_DIR/deploy/nginx/timetable.conf" /etc/nginx/sites-available/timetable.conf
  ln -sf /etc/nginx/sites-available/timetable.conf /etc/nginx/sites-enabled/timetable.conf
  echo "Installed nginx site; edit server_name and the certificate paths in /etc/nginx/sites-available/timetable.conf." >&2
fi
chmod 755 "$APP_DIR/deploy/backup.sh" "$APP_DIR/deploy/restore.sh" "$APP_DIR/deploy/upgrade.sh" "$APP_DIR/deploy/support-bundle.sh" "$APP_DIR/deploy/setup.sh"

systemctl daemon-reload
systemctl enable timetable-web.service timetable-workers.service timetable-backup.timer >/dev/null
nginx -t

cat <<EOF

Installed. Next (docs/RUNBOOK.md):
  1. Fill in $APP_DIR/.env (BACKGROUND_WORKERS=False is set by the web unit; TRUSTED_PROXY_COUNT=1).
  2. Create the database(s): single college -> flask db upgrade && flask seed run && flask admin create-superadmin ...
                              several colleges -> flask tenant init && flask tenant create <slug> --hostname <host> ...
  3. systemctl restart timetable-web timetable-workers && systemctl reload nginx
  4. curl -s https://<host>/health
EOF
