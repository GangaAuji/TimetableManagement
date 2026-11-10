#!/bin/sh
# Container entry. Migrations run only when TIMETABLE_AUTO_UPGRADE=1, which the first boot sets.
# Later releases use deploy/upgrade.sh on the host so a backup happens first.
set -eu
cd /opt/timetable/app
export FLASK_APP="${FLASK_APP:-wsgi:app}"
if [ "${TIMETABLE_AUTO_UPGRADE:-}" = "1" ]; then
  echo "Applying database upgrade and seed."
  if [ -n "${TENANT_REGISTRY_DB:-}" ]; then
    flask tenant upgrade --all
    flask tenant list | while IFS= read -r line; do
      case "$line" in
        *"	"*) flask seed run --tenant "${line%%	*}" ;;
      esac
    done
  else
    flask db upgrade
    flask seed run
  fi
fi
exec "$@"
