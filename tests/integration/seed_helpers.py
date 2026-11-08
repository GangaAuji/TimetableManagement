"""Reading seeded rows back for the seeder tests."""

from seeders import run_seeders
from seeders.data.roles import ROLE_DEFAULTS

SEEDED_TABLES = ('roles', 'permissions', 'role_permissions', 'branding_settings', 'seed_history')


def seed(connection, apply_role_defaults=False):
    cursor = connection.cursor()
    try:
        results = run_seeders(cursor, apply_role_defaults=apply_role_defaults)
        connection.commit()
    finally:
        cursor.close()
    return {result.table: result for result in results}


def snapshot(connection):
    """Every row of the seeded tables, in a stable order."""
    cursor = connection.cursor()
    try:
        rows = {}
        for table in SEEDED_TABLES:
            cursor.execute(f'SELECT * FROM {table}')
            rows[table] = sorted(cursor.fetchall(), key=repr)
        connection.commit()
        return rows
    finally:
        cursor.close()


def mapping(connection):
    """{(role name, permission name)} from role_permissions."""
    cursor = connection.cursor()
    try:
        cursor.execute(
            'SELECT r.name, p.name FROM role_permissions rp '
            'JOIN roles r ON r.id = rp.role_id JOIN permissions p ON p.id = rp.permission_id'
        )
        pairs = set(cursor.fetchall())
        connection.commit()
        return pairs
    finally:
        cursor.close()


def ledger(connection, seeder='role_permissions'):
    """seed_history items for one seeder, duplicates kept."""
    cursor = connection.cursor()
    try:
        cursor.execute('SELECT item FROM seed_history WHERE seeder = %s', (seeder,))
        items = [row[0] for row in cursor.fetchall()]
        connection.commit()
        return items
    finally:
        cursor.close()


def unique_keys(connection, table):
    """{index name: [columns]} for the unique indexes of `table`."""
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(f'SHOW INDEX FROM {table} WHERE Non_unique = 0')
        keys = {}
        for row in sorted(cursor.fetchall(), key=lambda row: (row['Key_name'], row['Seq_in_index'])):
            keys.setdefault(row['Key_name'], []).append(row['Column_name'])
        connection.commit()
        return keys
    finally:
        cursor.close()


def default_pairs():
    return {(role, permission) for role, grants in ROLE_DEFAULTS.items() for permission in grants}


def execute(connection, statement, params=()):
    cursor = connection.cursor()
    try:
        cursor.execute(statement, params)
        connection.commit()
    finally:
        cursor.close()
