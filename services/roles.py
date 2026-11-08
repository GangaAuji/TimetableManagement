"""Role list and role changes. This module does not read the request."""

from flask import current_app, flash

from data_access.roles import (
    count_permissions,
    count_roles,
    delete_one_role_permission,
    delete_role_permissions,
    delete_role_permissions_for_update,
    delete_role_row,
    fetch_assigned_permissions,
    fetch_common_permissions,
    fetch_existing_role_permission,
    fetch_permission_choices,
    fetch_permission_distribution,
    fetch_permission_names,
    fetch_permissions_for_modules,
    fetch_permissions_with_description,
    fetch_role_id_by_name,
    fetch_role_name,
    fetch_role_name_and_description,
    fetch_role_permission_ids,
    fetch_role_record,
    fetch_role_usage,
    fetch_roles_for_export,
    fetch_roles_with_counts,
    fetch_users_by_role_id,
    fetch_users_for_role,
    insert_role,
    insert_role_permission,
    insert_role_permission_for_update,
    update_role_row,
)
from extensions import get_db_connection
from security import log_activity
from security.authority import DEFAULT_LEVEL, role_level_by_id, role_permission_ids, role_problem

_ROLE_REFUSED = {
    'protected': 'You cannot change a role senior to your own.',
    'unheld': 'You can only grant permissions you hold yourself.',
}


def _cursor():
    connection = get_db_connection()
    return connection, connection.cursor(dictionary=True)


def list_roles():
    """Return permissions, roles, and the users grouped by role name."""
    connection, cursor = _cursor()
    permissions = fetch_permission_choices(cursor)
    roles = fetch_roles_with_counts(cursor)
    role_users = {}
    for role in roles:
        role_users[role['name']] = fetch_users_for_role(cursor, role['name'])
    cursor.close()
    return permissions, roles, role_users


def load_permission_name_rows():
    """Return permission rows for the request form. The connection stays open."""
    connection, cursor = _cursor()
    rows = fetch_permission_names(cursor)
    cursor.close()
    return rows


def permission_form_choices():
    """Return the permission choices used to validate a role form."""
    connection, cursor = _cursor()
    try:
        perms = fetch_permission_choices(cursor)
        return [(p['id'], f"{p['module']} - {p['name']}") for p in perms]
    finally:
        cursor.close()
        connection.close()


def _permission_ids(permissions):
    ids = []
    for perm_id in permissions or ():
        try:
            ids.append(int(perm_id))
        except (TypeError, ValueError):
            continue
    return ids


def _store_permission_ids(cursor, role_id, permissions):
    for pid in _permission_ids(permissions):
        insert_role_permission(cursor, role_id, pid)


def _role_change_problem(cursor, session, role_id, permissions=None):
    """Return 'protected', 'unheld', or None for a change to an existing role."""
    _name, level = role_level_by_id(cursor, role_id)
    added = set(_permission_ids(permissions)) - role_permission_ids(cursor, role_id) if permissions else ()
    return role_problem(cursor, session['user_id'], current_level=level, added_permission_ids=added)


def create_role(name, description, permissions, session):
    """Create a role and its permissions. A taken name is reported without rolling back."""
    connection, cursor = _cursor()
    try:
        if fetch_role_id_by_name(cursor, name):
            flash('Role already exists.', 'danger')
            return
        problem = role_problem(cursor, session['user_id'], new_level=DEFAULT_LEVEL,
                               added_permission_ids=_permission_ids(permissions))
        if problem:
            flash(_ROLE_REFUSED[problem], 'danger')
            return
        role_id = insert_role(cursor, name, description)
        _store_permission_ids(cursor, role_id, permissions)
        log_activity(session['user_id'], 'create_role', f'Created new role: {name}',
                     entity_type='role', entity_id=role_id, cursor=cursor)
        connection.commit()
        flash('Role created successfully.', 'success')
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error creating role: {str(exc)}")
        flash('Error creating role. Please try again.', 'danger')
    finally:
        cursor.close()
        connection.close()


def remove_role(role_id, session):
    """Delete a role after its permissions. Super Admin is refused without rolling back."""
    connection, cursor = _cursor()
    try:
        row = fetch_role_name(cursor, role_id)
        if not row:
            flash('Role not found.', 'danger')
            return
        role_name = row['name']
        if role_name == 'Super Admin':
            flash('Cannot delete Super Admin role.', 'danger')
            return
        problem = _role_change_problem(cursor, session, role_id)
        if problem:
            flash(_ROLE_REFUSED[problem], 'danger')
            return
        delete_role_permissions(cursor, role_id)
        delete_role_row(cursor, role_id)
        log_activity(
            session['user_id'],
            'delete_role',
            f'Deleted role {role_name} (ID: {role_id})',
            entity_type='role',
            entity_id=role_id,
            cursor=cursor,
        )
        connection.commit()
        flash('Role deleted successfully.', 'success')
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error deleting role: {str(exc)}")
        flash('Error deleting role. Please try again.', 'danger')
    finally:
        cursor.close()
        connection.close()


def change_role(role_id, name, description, permissions, session):
    """Replace a role's name, description, and permissions."""
    connection, cursor = _cursor()
    try:
        row = fetch_role_name(cursor, role_id)
        if not row:
            flash('Role not found.', 'danger')
            return
        old_name = row['name']
        if old_name == 'Super Admin' and name != 'Super Admin':
            flash('Cannot rename Super Admin role.', 'danger')
            return
        problem = _role_change_problem(cursor, session, role_id, permissions or [])
        if problem:
            flash(_ROLE_REFUSED[problem], 'danger')
            return
        update_role_row(cursor, name, description, role_id)
        delete_role_permissions(cursor, role_id)
        _store_permission_ids(cursor, role_id, permissions)
        log_activity(session['user_id'], 'edit_role', f'Edited role {name} (ID: {role_id})',
                     entity_type='role', entity_id=role_id, cursor=cursor)
        connection.commit()
        flash('Role updated successfully.', 'success')
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error editing role: {str(exc)}")
        flash('Error editing role. Please try again.', 'danger')
    finally:
        cursor.close()
        connection.close()


def find_role(role_id):
    """Return the role payload and status. Permission ids are loaded only for a found role."""
    connection, cursor = _cursor()
    try:
        role = fetch_role_record(cursor, role_id)
        if not role:
            return {'error': 'Role not found'}, 404
        perms = fetch_role_permission_ids(cursor, role_id)
        return {
            'id': role['id'],
            'name': role['name'],
            'description': role['description'],
            'permissions': [p['permission_id'] for p in perms],
        }, 200
    finally:
        cursor.close()
        connection.close()


def users_for_role(role_id):
    """Return the users assigned to a role id."""
    connection, cursor = _cursor()
    try:
        users = fetch_users_by_role_id(cursor, role_id)
        return [
            {'id': user['id'], 'username': user['username'], 'email': user['email']}
            for user in users
        ]
    finally:
        cursor.close()
        connection.close()


def load_role_permission_page(role_id):
    """Return the role permission page, or None when the role is missing."""
    connection, cursor = _cursor()
    try:
        role_tuple = fetch_role_record(cursor, role_id)
        if not role_tuple:
            return None
        role = {
            'id': role_tuple['id'],
            'name': role_tuple['name'],
            'description': role_tuple['description'],
        }
        all_permissions = fetch_permissions_with_description(cursor)
        permissions_by_module = {}
        for perm in all_permissions:
            module = perm['module'] or 'General'
            if module not in permissions_by_module:
                permissions_by_module[module] = []
            permissions_by_module[module].append({
                'id': perm['id'],
                'name': perm['name'],
                'description': perm['description'],
            })
        role_permissions = fetch_assigned_permissions(cursor, role_id)
        return {
            'role': role,
            'permissions_by_module': permissions_by_module,
            'role_permission_ids': [p['id'] for p in role_permissions],
        }
    finally:
        cursor.close()
        connection.close()


def replace_role_permissions(role_id, permission_ids, session):
    """Replace a role's permissions. Return ok, protected, unheld, or error."""
    connection, cursor = _cursor()
    try:
        problem = _role_change_problem(cursor, session, role_id, permission_ids or [])
        if problem:
            return problem
        delete_role_permissions_for_update(cursor, role_id)
        if permission_ids:
            for perm_id in permission_ids:
                insert_role_permission_for_update(cursor, role_id, perm_id)
        log_activity(
            session['user_id'],
            'update_role_permissions',
            f'Updated permissions for role ID {role_id}',
            entity_type='role',
            entity_id=role_id,
            cursor=cursor,
        )
        connection.commit()
        return 'ok'
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error updating role permissions: {exc}")
        return 'error'
    finally:
        cursor.close()
        connection.close()


def copy_role(role_id, session):
    """Clone a role. Return the JSON payload and status."""
    connection, cursor = _cursor()
    try:
        role = fetch_role_name_and_description(cursor, role_id)
        if not role:
            return {'error': 'Role not found.'}, 404
        problem = role_problem(cursor, session['user_id'], new_level=DEFAULT_LEVEL,
                               added_permission_ids=role_permission_ids(cursor, role_id))
        if problem:
            return {'error': _ROLE_REFUSED[problem]}, 403
        new_name = f"{role['name']} (Copy)"
        counter = 1
        while True:
            if not fetch_role_id_by_name(cursor, new_name):
                break
            counter += 1
            new_name = f"{role['name']} (Copy {counter})"
        new_role_id = insert_role(cursor, new_name, role['description'])
        perms = fetch_role_permission_ids(cursor, role_id)
        for perm in perms:
            insert_role_permission(cursor, new_role_id, perm['permission_id'])
        log_activity(
            session['user_id'],
            'clone_role',
            f'Cloned role "{role["name"]}" to "{new_name}" (ID: {new_role_id})',
            entity_type='role',
            entity_id=new_role_id,
            cursor=cursor,
        )
        connection.commit()
        return {
            'message': 'Role cloned successfully.',
            'new_role_id': new_role_id,
            'new_role_name': new_name,
        }, 200
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error cloning role: {str(exc)}")
        return {'error': 'Failed to clone role.'}, 500
    finally:
        cursor.close()
        connection.close()


def update_many_role_permissions(action, role_ids, perm_ids, session):
    """Add or remove permissions on several roles. Return the JSON payload and status."""
    connection, cursor = _cursor()
    try:
        for role_id in role_ids:
            problem = _role_change_problem(cursor, session, role_id, perm_ids if action == 'add' else None)
            if problem:
                return {'error': _ROLE_REFUSED[problem]}, 403
        if action == 'add':
            for role_id in role_ids:
                role = fetch_role_name(cursor, role_id)
                if role and role['name'] == 'Super Admin':
                    continue
                for perm_id in perm_ids:
                    if not fetch_existing_role_permission(cursor, role_id, perm_id):
                        insert_role_permission(cursor, role_id, perm_id)
            log_activity(
                session['user_id'],
                'bulk_add_permissions',
                f'Added permissions to roles: {",".join(role_ids)}',
                cursor=cursor,
            )
            connection.commit()
            return {'message': 'Permissions added successfully.'}, 200
        if action == 'remove':
            for role_id in role_ids:
                role = fetch_role_name(cursor, role_id)
                if role and role['name'] == 'Super Admin':
                    continue
                for perm_id in perm_ids:
                    delete_one_role_permission(cursor, role_id, perm_id)
            log_activity(
                session['user_id'],
                'bulk_remove_permissions',
                f'Removed permissions from roles: {",".join(role_ids)}',
                cursor=cursor,
            )
            connection.commit()
            return {'message': 'Permissions removed successfully.'}, 200
        return {'error': 'Invalid action.'}, 400
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Bulk permissions error: {str(exc)}")
        return {'error': 'Operation failed.'}, 500
    finally:
        cursor.close()
        connection.close()


def load_role_statistics():
    """Return role statistics, or the failure payload."""
    connection, cursor = _cursor()
    try:
        total_roles = count_roles(cursor)['total']
        total_permissions = count_permissions(cursor)['total']
        role_usage = fetch_role_usage(cursor)
        perm_distribution = fetch_permission_distribution(cursor)
        common_perms = fetch_common_permissions(cursor)
        return {
            'total_roles': total_roles,
            'total_permissions': total_permissions,
            'role_usage': [{'name': r['name'], 'users': r['user_count']} for r in role_usage],
            'permission_distribution': [
                {'module': p['module'], 'roles': p['role_count']} for p in perm_distribution
            ],
            'common_permissions': [
                {'name': p['name'], 'module': p['module'], 'roles': p['role_count']}
                for p in common_perms
            ],
        }, 200
    except Exception as exc:
        current_app.logger.error(f"Role stats error: {str(exc)}")
        return {'error': 'Failed to fetch statistics.'}, 500
    finally:
        cursor.close()
        connection.close()


def load_permissions_by_module():
    """Return permissions grouped by module, or the failure payload."""
    connection, cursor = _cursor()
    try:
        all_perms = fetch_permissions_for_modules(cursor)
        by_module = {}
        for perm in all_perms:
            module = perm['module'] or 'General'
            if module not in by_module:
                by_module[module] = []
            by_module[module].append({
                'id': perm['id'],
                'name': perm['name'],
                'description': perm['description'],
            })
        return by_module, 200
    except Exception as exc:
        current_app.logger.error(f"Permissions by module error: {str(exc)}")
        return {'error': 'Failed to fetch permissions.'}, 500
    finally:
        cursor.close()
        connection.close()


def export_role_rows():
    """Return the role export rows. Both the cursor and connection are closed."""
    connection, cursor = _cursor()
    try:
        return fetch_roles_for_export(cursor)
    finally:
        cursor.close()
        connection.close()
