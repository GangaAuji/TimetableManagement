"""Default role permissions, each granted at most once.

seed_history holds one row per (role, permission) default that has been
handled, plus a baseline row written on the first run:

* An empty role_permissions table on the first run is a fresh install, and
  every default is granted.
* Otherwise the first run grants nothing. Defaults the database already has
  are recorded, and the rest are listed until `--apply-role-defaults` grants them.
* A default whose `since` is newer than the baseline came in a later release
  and is granted once without the flag.

A recorded default is never granted again, so a permission a college removed
from a role stays removed.
"""

from dataclasses import dataclass, field

from seeders.base import SeedResult, ids_by_name, record, recorded
from seeders.data.roles import DEFAULTS_VERSION, ROLE_DEFAULTS

SEEDER = 'role_permissions'
BASELINE = '__baseline__'


@dataclass
class RolePermissionsResult(SeedResult):
    fresh: bool = False
    earlier: int = 0
    pending: list = field(default_factory=list)
    missing: list = field(default_factory=list)

    def summary(self):
        return (
            f'role_permissions: {self.added} granted, {self.present} already mapped, '
            f'{self.earlier} handled before, {len(self.pending)} not granted.'
        )


class RolePermissionsSeeder:
    name = SEEDER

    def __init__(self, apply_defaults=False, defaults=None):
        self.apply_defaults = apply_defaults
        self.defaults = ROLE_DEFAULTS if defaults is None else defaults

    def run(self, cursor):
        result = RolePermissionsResult(SEEDER)
        handled = recorded(cursor, SEEDER)
        baseline = handled.get(BASELINE)
        if baseline is None:
            cursor.execute('SELECT COUNT(*) FROM role_permissions')
            result.fresh = cursor.fetchone()[0] == 0
            baseline = str(DEFAULTS_VERSION)
            record(cursor, SEEDER, BASELINE, baseline)
        baseline = int(baseline)

        roles = ids_by_name(cursor, 'roles')
        permissions = ids_by_name(cursor, 'permissions')
        cursor.execute('SELECT role_id, permission_id FROM role_permissions')
        mapped = {tuple(row) for row in cursor.fetchall()}

        for role_name, grants in self.defaults.items():
            for permission_name, since in sorted(grants.items()):
                item = f'{role_name}:{permission_name}'
                if item in handled:
                    result.earlier += 1
                    continue
                role = roles.get(role_name.lower())
                permission = permissions.get(permission_name.lower())
                if role is None or permission is None:
                    result.missing.append(item)
                    continue
                pair = (role[0], permission[0])
                if pair in mapped:
                    record(cursor, SEEDER, item, since)
                    result.present += 1
                elif result.fresh or self.apply_defaults or since > baseline:
                    cursor.execute('INSERT INTO role_permissions (role_id, permission_id) VALUES (%s, %s)', pair)
                    record(cursor, SEEDER, item, since)
                    mapped.add(pair)
                    result.added += 1
                else:
                    result.pending.append((role_name, permission_name))
        result.lines = self._report(result)
        return result

    def _report(self, result):
        lines = []
        if result.pending:
            lines.append(
                f'{len(result.pending)} default role permission(s) were not granted because this database '
                'already had role permissions. Run `flask seed run --apply-role-defaults` to grant them once:'
            )
            by_role = {}
            for role_name, permission_name in result.pending:
                by_role.setdefault(role_name, []).append(permission_name)
            for role_name, names in by_role.items():
                lines.append(f'  {role_name} ({len(names)}): {", ".join(names)}')
        if result.missing:
            lines.append(f'Skipped {len(result.missing)} default(s) whose role or permission is missing: '
                         f'{", ".join(result.missing)}')
        return lines
