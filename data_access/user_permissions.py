"""User permission page and group assignment SQL. Callers pass a cursor."""


def fetch_permission_user(cursor, user_id):
    """Return the account row shown on the permission page."""
    cursor.execute("""
            SELECT id, username, role, department_id, is_hod 
            FROM users WHERE id = %s
        """, [user_id])
    return cursor.fetchone()


def fetch_department_name(cursor, department_id):
    """Return a department name row."""
    cursor.execute("SELECT name FROM departments WHERE id = %s", [department_id])
    return cursor.fetchone()


def fetch_departments(cursor):
    """Return departments in name order."""
    cursor.execute("SELECT id, name FROM departments ORDER BY name")
    return cursor.fetchall()


def fetch_courses(cursor):
    """Return courses in name order."""
    cursor.execute("SELECT id, name, department_id FROM courses ORDER BY name")
    return cursor.fetchall()


def fetch_classes(cursor):
    """Return classes in display order."""
    cursor.execute("SELECT id, name FROM classes ORDER BY display_order, name")
    return cursor.fetchall()


def fetch_permission_groups(cursor):
    """Return active permission groups and their permission names."""
    cursor.execute("""
            SELECT pg.id, pg.name, pg.description, pg.module,
                   GROUP_CONCAT(p.name ORDER BY p.name) as permissions
            FROM permission_groups pg
            LEFT JOIN permission_group_permissions pgp ON pg.id = pgp.group_id
            LEFT JOIN permissions p ON pgp.permission_id = p.id
            WHERE pg.is_active = TRUE
            GROUP BY pg.id, pg.name, pg.description, pg.module
            ORDER BY pg.module, pg.name
        """)
    return cursor.fetchall()


def fetch_user_groups(cursor, user_id):
    """Return the active groups assigned to a user."""
    cursor.execute("""
            SELECT upg.group_id, upg.department_id, pg.name
            FROM user_permission_groups upg
            JOIN permission_groups pg ON upg.group_id = pg.id
            WHERE upg.user_id = %s AND upg.is_active = TRUE
        """, [user_id])
    return cursor.fetchall()


def fetch_active_user_group(cursor, user_id, group_id, department_id):
    """Return a row when this group is already assigned."""
    cursor.execute("""
            SELECT id FROM user_permission_groups 
            WHERE user_id = %s AND group_id = %s 
            AND (department_id = %s OR (department_id IS NULL AND %s IS NULL))
            AND is_active = TRUE
        """, [user_id, group_id, department_id, department_id])
    return cursor.fetchone()


def insert_user_group(cursor, user_id, group_id, department_id, granted_by):
    """Assign a permission group to a user."""
    cursor.execute("""
            INSERT INTO user_permission_groups 
            (user_id, group_id, department_id, granted_by)
            VALUES (%s, %s, %s, %s)
        """, [user_id, group_id, department_id, granted_by])


def fetch_group_name(cursor, group_id):
    """Return the permission group name row."""
    cursor.execute("SELECT name FROM permission_groups WHERE id = %s", [group_id])
    return cursor.fetchone()


def delete_user_group(cursor, user_id, group_id, department_id):
    """Remove one group assignment."""
    cursor.execute("""
            DELETE FROM user_permission_groups 
            WHERE user_id = %s AND group_id = %s 
            AND (department_id = %s OR (department_id IS NULL AND %s IS NULL))
        """, [user_id, group_id, department_id, department_id])
