#!/usr/bin/env bash
# Nightly backup: every database this installation uses plus the upload folders, then optional off-box copy.
#
#   deploy/backup.sh                 # reads .env from the current directory (the systemd unit loads it)
#
# Databases: MYSQL_DB in single-college mode; with TENANT_REGISTRY_DB, the registry itself and every
# db_name in its tenants table. Each dump is gzip'd separately so one college can be restored alone.
# Files: static/uploads and UPLOAD_FOLDER (CSV exports) as one tar.gz.
# Retention: BACKUP_KEEP_DAYS (default 14). Off-box: BACKUP_REMOTE as an rclone remote path (e.g. s3:bucket/timetable)
# or an rsync destination (user@host:/path); BACKUP_REMOTE_TOOL selects rclone (default) or rsync.
set -euo pipefail

: "${MYSQL_HOST:=127.0.0.1}"
: "${MYSQL_USER:?MYSQL_USER is not set}"
: "${MYSQL_PASSWORD:?MYSQL_PASSWORD is not set}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/timetable}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
APP_DIR="${APP_DIR:-$(pwd)}"
UPLOAD_FOLDER="${UPLOAD_FOLDER:-$APP_DIR/uploads}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$BACKUP_DIR/$stamp"
mkdir -p "$target"
chmod 700 "$BACKUP_DIR"

# Credentials go through a defaults file so they never appear on the command line or in `ps`.
defaults="$(mktemp)"
trap 'rm -f "$defaults"' EXIT
chmod 600 "$defaults"
printf '[client]\nhost=%s\nuser=%s\npassword=%s\n' "$MYSQL_HOST" "$MYSQL_USER" "$MYSQL_PASSWORD" > "$defaults"

databases=()
if [[ -n "${TENANT_REGISTRY_DB:-}" ]]; then
  databases+=("$TENANT_REGISTRY_DB")
  while IFS= read -r name; do
    [[ -n "$name" ]] && databases+=("$name")
  done < <(mysql --defaults-extra-file="$defaults" -N -B -e "SELECT db_name FROM tenants ORDER BY slug" "$TENANT_REGISTRY_DB")
else
  : "${MYSQL_DB:?MYSQL_DB is not set}"
  databases+=("$MYSQL_DB")
fi

for name in "${databases[@]}"; do
  if [[ ! "$name" =~ ^[a-z0-9_]{1,64}$ ]]; then
    echo "Skipping database with an unexpected name: $name" >&2
    continue
  fi
  mysqldump --defaults-extra-file="$defaults" --single-transaction --quick --routines --triggers --events \
    --default-character-set=utf8mb4 "$name" | gzip -6 > "$target/$name.sql.gz"
  echo "dumped $name -> $target/$name.sql.gz ($(du -h "$target/$name.sql.gz" | cut -f1))"
done

tar_sources=()
[[ -d "$APP_DIR/static/uploads" ]] && tar_sources+=("-C" "$APP_DIR/static" "uploads")
[[ -d "$UPLOAD_FOLDER" ]] && tar_sources+=("-C" "$(dirname "$UPLOAD_FOLDER")" "$(basename "$UPLOAD_FOLDER")")
if [[ ${#tar_sources[@]} -gt 0 ]]; then
  tar -czf "$target/files.tar.gz" "${tar_sources[@]}"
  echo "archived uploads -> $target/files.tar.gz ($(du -h "$target/files.tar.gz" | cut -f1))"
fi

(cd "$target" && sha256sum ./* > SHA256SUMS)
echo "$stamp" > "$BACKUP_DIR/LATEST"

find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime "+$BACKUP_KEEP_DAYS" -exec rm -rf {} +

if [[ -n "${BACKUP_REMOTE:-}" ]]; then
  case "${BACKUP_REMOTE_TOOL:-rclone}" in
    rclone) rclone copy "$target" "$BACKUP_REMOTE/$stamp" --quiet && rclone copy "$BACKUP_DIR/LATEST" "$BACKUP_REMOTE" --quiet ;;
    rsync)  rsync -a --quiet "$target" "$BACKUP_REMOTE/" && rsync -a --quiet "$BACKUP_DIR/LATEST" "$BACKUP_REMOTE/" ;;
    *) echo "Unknown BACKUP_REMOTE_TOOL: $BACKUP_REMOTE_TOOL" >&2; exit 1 ;;
  esac
  echo "copied to $BACKUP_REMOTE/$stamp"
fi
echo "backup $stamp complete"
