"""Role-list SQL. Callers pass a cursor."""


def fetch_permission_choices(cursor):
    """Return permissions in module and name order."""
    cursor.execute('SELECT id, name, module FROM permissions ORDER BY module, name')
    return cursor.fetchall()


def fetch_roles_with_counts(cursor):
    """Return each role with its permission names and user count."""
    cursor.execute("""
        SELECT r.id, r.name, r.description, r.created_at, r.updated_at,
               GROUP_CONCAT(DISTINCT p.name) as permissions,
               COUNT(DISTINCT u.id) as user_count
        FROM roles r
        LEFT JOIN role_permissions rp ON r.id = rp.role_id
        LEFT JOIN permissions p ON rp.permission_id = p.id
        LEFT JOIN users u ON u.role = r.name
        GROUP BY r.id, r.name, r.description, r.created_at, r.updated_at
        ORDER BY r.name
    """)
    return cursor.fetchall()


def fetch_users_for_role(cursor, role_name):
    """Return the accounts assigned to one role name."""
    cursor.execute("""
            SELECT id, username, status, department_id
            FROM users
            WHERE role = %s
            ORDER BY username
        """, [role_name])
    return cursor.fetchall()


def fetch_permission_names(cursor):
    """Return permission ids and names for the role form."""
    cursor.execute('SELECT id, name FROM permissions ORDER BY module, name')
    return cursor.fetchall()


def fetch_role_id_by_name(cursor, name):
    """Return a role id when the name is already used."""
    cursor.execute('SELECT id FROM roles WHERE name = %s', [name])
    return cursor.fetchone()


def insert_role(cursor, name, description):
    """Insert a role and return its id."""
    cursor.execute(
        'INSERT INTO roles (name, description) VALUES (%s, %s)',
        [name, description],
    )
    return cursor.lastrowid


def insert_role_permission(cursor, role_id, permission_id):
    """Attach one permission to a role."""
    cursor.execute(
        'INSERT INTO role_permissions (role_id, permission_id) VALUES (%s, %s)',
        [role_id, permission_id],
    )


def fetch_role_name(cursor, role_id):
    """Return the role name row."""
    cursor.execute('SELECT name FROM roles WHERE id = %s', [role_id])
    return cursor.fetchone()


def delete_role_permissions(cursor, role_id):
    """Remove every permission attached to a role."""
    cursor.execute('DELETE FROM role_permissions WHERE role_id = %s', [role_id])


def delete_role_row(cursor, role_id):
    """Delete the role row."""
    cursor.execute('DELETE FROM roles WHERE id = %s', [role_id])


def update_role_row(cursor, name, description, role_id):
    """Rename a role and replace its description."""
    cursor.execute(
        'UPDATE roles SET name=%s, description=%s WHERE id=%s',
        [name, description, role_id],
    )


def fetch_role_record(cursor, role_id):
    """Return the role fields shown in the editor."""
    cursor.execute('SELECT id, name, description FROM roles WHERE id = %s', [role_id])
    return cursor.fetchone()


def fetch_role_permission_ids(cursor, role_id):
    """Return the permission id rows for a role."""
    cursor.execute('SELECT permission_id FROM role_permissions WHERE role_id = %s', [role_id])
    return cursor.fetchall()


def fetch_users_by_role_id(cursor, role_id):
    """Return users whose role name matches this role id."""
    cursor.execute("""
            SELECT u.id, u.username, u.email
            FROM users u
            WHERE u.role = (SELECT name FROM roles WHERE id = %s)
            ORDER BY u.username
        """, [role_id])
    return cursor.fetchall()


def fetch_permissions_with_description(cursor):
    """Return every permission in module and name order."""
    cursor.execute("""
            SELECT id, name, description, module 
            FROM permissions 
            ORDER BY module, name
        """)
    return cursor.fetchall()


def fetch_assigned_permissions(cursor, role_id):
    """Return the permissions currently attached to a role."""
    cursor.execute("""
            SELECT p.id, p.name, p.description, p.module
            FROM role_permissions rp
            JOIN permissions p ON rp.permission_id = p.id
            WHERE rp.role_id = %s
            ORDER BY p.module, p.name
        """, [role_id])
    return cursor.fetchall()


def delete_role_permissions_for_update(cursor, role_id):
    """Clear a role's permissions before they are replaced."""
    cursor.execute("DELETE FROM role_permissions WHERE role_id = %s", [role_id])


def insert_role_permission_for_update(cursor, role_id, permission_id):
    """Attach one submitted permission id."""
    cursor.execute("""
                    INSERT INTO role_permissions (role_id, permission_id)
                    VALUES (%s, %s)
                """, [role_id, permission_id])


def fetch_role_name_and_description(cursor, role_id):
    """Return the name and description used when cloning a role."""
    cursor.execute('SELECT name, description FROM roles WHERE id = %s', [role_id])
    return cursor.fetchone()


def fetch_existing_role_permission(cursor, role_id, permission_id):
    """Return a row when the role already has this permission."""
    cursor.execute(
        'SELECT id FROM role_permissions WHERE role_id = %s AND permission_id = %s',
        [role_id, permission_id],
    )
    return cursor.fetchone()


def delete_one_role_permission(cursor, role_id, permission_id):
    """Remove one permission from a role."""
    cursor.execute(
        'DELETE FROM role_permissions WHERE role_id = %s AND permission_id = %s',
        [role_id, permission_id],
    )


def count_roles(cursor):
    """Return the role count row."""
    cursor.execute('SELECT COUNT(*) AS total FROM roles')
    return cursor.fetchone()


def count_permissions(cursor):
    """Return the permission count row."""
    cursor.execute('SELECT COUNT(*) AS total FROM permissions')
    return cursor.fetchone()


def fetch_role_usage(cursor):
    """Return each role with its user count."""
    cursor.execute("""
            SELECT r.name, COUNT(u.id) as user_count
            FROM roles r
            LEFT JOIN users u ON u.role = r.name
            GROUP BY r.name
            ORDER BY user_count DESC
        """)
    return cursor.fetchall()


def fetch_permission_distribution(cursor):
    """Return how many roles use each permission module."""
    cursor.execute("""
            SELECT p.module, COUNT(DISTINCT rp.role_id) as role_count
            FROM permissions p
            LEFT JOIN role_permissions rp ON p.id = rp.permission_id
            GROUP BY p.module
            ORDER BY role_count DESC
        """)
    return cursor.fetchall()


def fetch_common_permissions(cursor):
    """Return the ten permissions used by the most roles."""
    cursor.execute("""
            SELECT p.name, p.module, COUNT(rp.role_id) as role_count
            FROM permissions p
            LEFT JOIN role_permissions rp ON p.id = rp.permission_id
            GROUP BY p.id, p.name, p.module
            ORDER BY role_count DESC
            LIMIT 10
        """)
    return cursor.fetchall()


def fetch_permissions_for_modules(cursor):
    """Return permissions for the module grouping response."""
    cursor.execute("""
            SELECT module, id, name, description
            FROM permissions
            ORDER BY module, name
        """)
    return cursor.fetchall()


def fetch_roles_for_export(cursor):
    """Return roles and their permission names for the CSV export."""
    cursor.execute(
        """
            SELECT r.id, r.name, r.description,
                   GROUP_CONCAT(p.name ORDER BY p.module, p.name SEPARATOR '; ') as permissions_list
            FROM roles r
            LEFT JOIN role_permissions rp ON r.id = rp.role_id
            LEFT JOIN permissions p ON rp.permission_id = p.id
            GROUP BY r.id, r.name, r.description
            ORDER BY r.name
            """
    )
    return cursor.fetchall()
