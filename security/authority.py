"""Who may manage which accounts and roles, and which permissions they may hand out.

roles.hierarchy_level orders the roles; a smaller number is more senior and
Super Admin is 1. An actor manages only accounts whose role is junior to
their own (a larger level). Only a Super Admin manages a Super Admin. A
permission can be granted only by someone who holds it.

Every check reads the actor's role from the database, not from the session.
Callers pass the cursor of the transaction that will make the change.
"""

SUPER_ADMIN = 'Super Admin'
DEFAULT_LEVEL = 50


def _value(row, key, index=0):
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    return row[index]


def user_role(cursor, user_id):
    cursor.execute('SELECT role FROM users WHERE id = %s', (user_id,))
    return _value(cursor.fetchone(), 'role')


def role_level(cursor, role_name):
    cursor.execute('SELECT hierarchy_level FROM roles WHERE name = %s', (role_name,))
    level = _value(cursor.fetchone(), 'hierarchy_level')
    return DEFAULT_LEVEL if level is None else int(level)


def role_level_by_id(cursor, role_id):
    """Return (name, level) for a role id, or (None, None)."""
    cursor.execute('SELECT name, hierarchy_level FROM roles WHERE id = %s', (role_id,))
    row = cursor.fetchone()
    if row is None:
        return None, None
    level = _value(row, 'hierarchy_level', 1)
    return _value(row, 'name'), DEFAULT_LEVEL if level is None else int(level)


def is_super_admin(cursor, actor_id):
    return user_role(cursor, actor_id) == SUPER_ADMIN


def may_manage_role(cursor, actor_id, target_role):
    """True when the actor may manage an account that holds (or will hold) target_role."""
    actor_role = user_role(cursor, actor_id)
    if actor_role is None:
        return False
    if actor_role == SUPER_ADMIN:
        return True
    if target_role == SUPER_ADMIN:
        return False
    return role_level(cursor, target_role) > role_level(cursor, actor_role)


def account_problem(cursor, actor_id, target_user_id, new_role=None):
    """Return 'missing', 'protected', or None when the actor may change this account.

    new_role is the role the change would give the account, checked the same way.
    """
    target_role = user_role(cursor, target_user_id)
    if target_role is None:
        return 'missing'
    if not may_manage_role(cursor, actor_id, target_role):
        return 'protected'
    if new_role is not None and new_role != target_role and not may_manage_role(cursor, actor_id, new_role):
        return 'protected'
    return None


def removes_last_super_admin(cursor, target_user_id, new_role, new_status):
    """True when the change would leave no active Super Admin."""
    cursor.execute('SELECT role, status FROM users WHERE id = %s', (target_user_id,))
    row = cursor.fetchone()
    if _value(row, 'role') != SUPER_ADMIN or _value(row, 'status', 1) != 'active':
        return False
    if new_role == SUPER_ADMIN and new_status == 'active':
        return False
    cursor.execute(
        "SELECT COUNT(*) AS total FROM users WHERE role = %s AND status = 'active' AND id <> %s",
        (SUPER_ADMIN, target_user_id),
    )
    return int(_value(cursor.fetchone(), 'total') or 0) == 0


def held_permission_names(cursor, actor_id, department_id=None):
    """Names the actor holds everywhere, or in department_id when one is given."""
    cursor.execute(
        """
        SELECT p.name FROM users u
        JOIN roles r ON r.name = u.role
        JOIN role_permissions rp ON rp.role_id = r.id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE u.id = %s
        UNION
        SELECT p.name FROM user_permissions up
        JOIN permissions p ON p.id = up.permission_id
        WHERE up.user_id = %s AND up.is_active = TRUE
          AND (up.expires_at IS NULL OR up.expires_at > NOW())
          AND (up.department_id IS NULL OR up.department_id = %s)
        UNION
        SELECT p.name FROM user_permission_groups upg
        JOIN permission_group_permissions pgp ON pgp.group_id = upg.group_id
        JOIN permissions p ON p.id = pgp.permission_id
        WHERE upg.user_id = %s AND upg.is_active = TRUE
          AND (upg.department_id IS NULL OR upg.department_id = %s)
        """,
        (actor_id, actor_id, department_id, actor_id, department_id),
    )
    return {_value(row, 'name') for row in cursor.fetchall()}


def unheld_permissions(cursor, actor_id, names, department_id=None):
    """Return the names in `names` the actor may not grant. A Super Admin may grant every one."""
    wanted = {name for name in names if name}
    if not wanted or is_super_admin(cursor, actor_id):
        return []
    return sorted(wanted - held_permission_names(cursor, actor_id, department_id))


def permission_names_for_ids(cursor, permission_ids):
    ids = [int(item) for item in permission_ids]
    if not ids:
        return set()
    marks = ', '.join(['%s'] * len(ids))
    cursor.execute(f'SELECT name FROM permissions WHERE id IN ({marks})', tuple(ids))
    return {_value(row, 'name') for row in cursor.fetchall()}


def group_permission_names(cursor, group_id):
    cursor.execute(
        'SELECT p.name FROM permission_group_permissions pgp JOIN permissions p ON p.id = pgp.permission_id '
        'WHERE pgp.group_id = %s',
        (group_id,),
    )
    return {_value(row, 'name') for row in cursor.fetchall()}


def role_problem(cursor, actor_id, current_level=None, new_level=None, added_permission_ids=()):
    """Return 'protected', 'unheld', or None when the actor may make this role change.

    A role more senior than the actor cannot be edited, no role can be made
    more senior than the actor, and added permissions must be held by the actor.
    """
    actor_role = user_role(cursor, actor_id)
    if actor_role is None:
        return 'protected'
    if actor_role == SUPER_ADMIN:
        return None
    own_level = role_level(cursor, actor_role)
    if current_level is not None and current_level < own_level:
        return 'protected'
    if new_level is not None and new_level < own_level:
        return 'protected'
    added = permission_names_for_ids(cursor, added_permission_ids)
    if added - held_permission_names(cursor, actor_id):
        return 'unheld'
    return None


def role_permission_ids(cursor, role_id):
    cursor.execute('SELECT permission_id FROM role_permissions WHERE role_id = %s', (role_id,))
    return {int(_value(row, 'permission_id')) for row in cursor.fetchall()}
