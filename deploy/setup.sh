#!/usr/bin/env bash
# First boot on a Debian or Ubuntu server. Idempotent install.sh still does the packages and units.
#
#   sudo deploy/setup.sh
#
# Asks for the database password, the public hostname, the first Super Admin, and an optional license file.
# A license file turns LICENSE_REQUIRED on. An empty path leaves the flag off.
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run setup as root: sudo deploy/setup.sh" >&2
  exit 1
fi

APP_DIR="${APP_DIR:-/opt/timetable/app}"
VENV_DIR="${VENV_DIR:-/opt/timetable/venv}"
SERVICE_USER="${SERVICE_USER:-timetable}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -f /etc/os-release ]] || ! grep -Eq '^(ID|ID_LIKE)=.*(debian|ubuntu)' /etc/os-release; then
  echo "This installer supports Debian and Ubuntu." >&2
  exit 1
fi

if [[ "$here" != "$APP_DIR" ]]; then
  echo "Copy this repository to $APP_DIR first (it is at $here)." >&2
  exit 1
fi

if ! command -v mysql >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1 || ! command -v openssl >/dev/null 2>&1; then
  apt-get update -qq
  packages=()
  command -v mysql >/dev/null 2>&1 || packages+=(mariadb-server)
  command -v python3 >/dev/null 2>&1 || packages+=(python3)
  command -v openssl >/dev/null 2>&1 || packages+=(openssl)
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${packages[@]}"
  if [[ " ${packages[*]} " == *" mariadb-server "* ]]; then
    systemctl enable --now mariadb
  fi
fi

read -r -p "MariaDB host [127.0.0.1]: " mysql_host
mysql_host="${mysql_host:-127.0.0.1}"
read -r -p "MariaDB user [timetable]: " mysql_user
mysql_user="${mysql_user:-timetable}"
read -r -s -p "MariaDB password: " mysql_password
echo
read -r -p "Database name [timetable]: " mysql_db
mysql_db="${mysql_db:-timetable}"
read -r -p "Public hostname [timetable.example]: " hostname
hostname="${hostname:-timetable.example}"
read -r -p "Super Admin username: " admin_user
read -r -p "Super Admin email: " admin_email
read -r -p "License file path (empty to leave the flag off): " license_source

if [[ -z "$admin_user" || -z "$admin_email" || -z "$mysql_password" ]]; then
  echo "The database password, Super Admin username, and email are required." >&2
  exit 1
fi

secret="$(openssl rand -hex 32)"
umask 077
if [[ ! -f "$APP_DIR/.env" ]]; then
  APP_DIR="$APP_DIR" \
  SETUP_SECRET="$secret" \
  SETUP_MYSQL_HOST="$mysql_host" \
  SETUP_MYSQL_USER="$mysql_user" \
  SETUP_MYSQL_PASSWORD="$mysql_password" \
  SETUP_MYSQL_DB="$mysql_db" \
  SETUP_HOSTNAME="$hostname" \
  python3 - <<'PY'
import os
from pathlib import Path

root = Path(os.environ['APP_DIR'])
replacements = {
    'SECRET_KEY': os.environ['SETUP_SECRET'],
    'MYSQL_HOST': os.environ['SETUP_MYSQL_HOST'],
    'MYSQL_USER': os.environ['SETUP_MYSQL_USER'],
    'MYSQL_PASSWORD': os.environ['SETUP_MYSQL_PASSWORD'],
    'MYSQL_DB': os.environ['SETUP_MYSQL_DB'],
    'BASE_URL': 'https://' + os.environ['SETUP_HOSTNAME'],
}
lines = []
seen = set()
for line in (root / '.env.example').read_text(encoding='utf-8').splitlines():
    key, sep, _value = line.partition('=')
    if sep and not key.startswith('#') and key in replacements:
        lines.append(f'{key}={replacements[key]}')
        seen.add(key)
    else:
        lines.append(line)
missing = [key for key in replacements if key not in seen]
if missing:
    raise SystemExit('Could not write .env from .env.example: ' + ', '.join(missing))
(root / '.env').write_text('\n'.join(lines) + '\n', encoding='utf-8')
PY
fi
unset mysql_password secret

license_required=false
if [[ -n "$license_source" ]]; then
  if [[ ! -f "$license_source" ]]; then
    echo "No license file at $license_source." >&2
    exit 1
  fi
  install -m 640 -o "$SERVICE_USER" -g "$SERVICE_USER" "$license_source" "$APP_DIR/license.json"
  license_required=true
fi
APP_DIR="$APP_DIR" SETUP_LICENSE_REQUIRED="$license_required" python3 - <<'PY'
import os
from pathlib import Path

root = Path(os.environ['APP_DIR'])
path = root / '.env'
lines = path.read_text(encoding='utf-8').splitlines()
wanted = {
    'LICENSE_REQUIRED': os.environ['SETUP_LICENSE_REQUIRED'],
    'LICENSE_FILE': str(root / 'license.json'),
}
seen = set()
updated = []
for line in lines:
    key, sep, _value = line.partition('=')
    if sep and not key.startswith('#') and key in wanted:
        updated.append(f'{key}={wanted[key]}')
        seen.add(key)
    else:
        updated.append(line)
for key, value in wanted.items():
    if key not in seen:
        updated.append(f'{key}={value}')
path.write_text('\n'.join(updated) + '\n', encoding='utf-8')
PY

"$APP_DIR/deploy/install.sh"
chown "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"

sudo -u "$SERVICE_USER" \
  env APP_DIR="$APP_DIR" VENV_DIR="$VENV_DIR" SETUP_ADMIN_USER="$admin_user" SETUP_ADMIN_EMAIL="$admin_email" \
  bash -c 'set -a; source "$APP_DIR/.env"; set +a; export FLASK_APP=wsgi:app; cd "$APP_DIR"; "$VENV_DIR/bin/flask" db upgrade && "$VENV_DIR/bin/flask" seed run && "$VENV_DIR/bin/flask" admin create-superadmin "$SETUP_ADMIN_USER" "$SETUP_ADMIN_EMAIL"'

systemctl restart timetable-web timetable-workers
systemctl reload nginx || true
systemctl start timetable-backup.timer || true
echo "Setup finished. Check: curl -s https://$hostname/health"
