from seeders.base import SeedResult, ids_by_name
from seeders.data.roles import ROLES


class RolesSeeder:
    """Insert each built-in role that is missing by name. Existing roles are never changed."""

    name = 'roles'

    def run(self, cursor):
        result = SeedResult('roles')
        existing = ids_by_name(cursor, 'roles')
        for role in ROLES:
            if role.name.lower() in existing:
                result.present += 1
                continue
            cursor.execute(
                'INSERT INTO roles (name, description, hierarchy_level) VALUES (%s, %s, %s)',
                (role.name, role.description, role.level),
            )
            result.added += 1
        return result
