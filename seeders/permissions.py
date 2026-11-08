from seeders.base import SeedResult, ids_by_name
from seeders.data.permissions import PERMISSIONS


class PermissionsSeeder:
    """Insert each permission that is missing by name. Existing rows are never changed."""

    name = 'permissions'

    def run(self, cursor):
        result = SeedResult('permissions')
        existing = ids_by_name(cursor, 'permissions')
        for permission in PERMISSIONS:
            if permission.name.lower() in existing:
                result.present += 1
                continue
            cursor.execute(
                'INSERT INTO permissions (name, description, module) VALUES (%s, %s, %s)',
                (permission.name, permission.description, permission.group),
            )
            result.added += 1
        return result
