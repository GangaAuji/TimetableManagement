#!/usr/bin/env bash
# Restore one dump into a database. Used for the restore drill and for real recovery.
#
#   deploy/restore.sh <dump.sql.gz> <target database> [--replace]
#
# Without --replace the target database must not exist (it is created). With --replace it is dropped
# first: use that only when restoring over a broken database, and stop the services before you do.
# Reads MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD from the environment (source .env or let systemd load it).
set -euo pipefail

dump="${1:?dump file}"
target="${2:?target database}"
mode="${3:-}"
: "${MYSQL_HOST:=127.0.0.1}"
: "${MYSQL_USER:?MYSQL_USER is not set}"
: "${MYSQL_PASSWORD:?MYSQL_PASSWORD is not set}"

if [[ ! "$target" =~ ^[a-z0-9_]{1,64}$ ]]; then
  echo "Refusing database name: $target" >&2
  exit 1
fi
[[ -f "$dump" ]] || { echo "No such file: $dump" >&2; exit 1; }

defaults="$(mktemp)"
trap 'rm -f "$defaults"' EXIT
chmod 600 "$defaults"
printf '[client]\nhost=%s\nuser=%s\npassword=%s\n' "$MYSQL_HOST" "$MYSQL_USER" "$MYSQL_PASSWORD" > "$defaults"

exists="$(mysql --defaults-extra-file="$defaults" -N -B -e "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = '$target'")"
if [[ "$exists" != "0" ]]; then
  if [[ "$mode" == "--replace" ]]; then
    mysql --defaults-extra-file="$defaults" -e "DROP DATABASE \`$target\`"
  else
    echo "Database $target exists. Pass --replace to drop it first (stop the services before that)." >&2
    exit 1
  fi
fi
mysql --defaults-extra-file="$defaults" -e "CREATE DATABASE \`$target\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
gunzip -c "$dump" | mysql --defaults-extra-file="$defaults" "$target"
stamp="$(mysql --defaults-extra-file="$defaults" -N -B -e "SELECT version_num FROM alembic_version" "$target" 2>/dev/null || echo 'no alembic_version')"
echo "restored $dump into $target (migration stamp: $stamp)"
