"""User permission page and permission-group assignment."""

from flask import current_app

from data_access.roles import fetch_permissions_with_description
from data_access.user_permissions import (
    delete_user_group,
    fetch_active_user_group,
    fetch_classes,
    fetch_courses,
    fetch_department_name,
    fetch_departments,
    fetch_group_name,
    fetch_permission_groups,
    fetch_permission_user,
    fetch_user_groups,
    insert_user_group,
)
from extensions import get_db_connection
from security import get_user_permissions, log_activity


def _cursor():
    connection = get_db_connection()
    return connection, connection.cursor(dictionary=True)


def load_user_permission_page(user_id):
    """Return the permission-page context, or None when the user is missing."""
    connection, cursor = _cursor()
    try:
        user_tuple = fetch_permission_user(cursor, user_id)
        if not user_tuple:
            return None
        user = {
            'id': user_tuple['id'],
            'username': user_tuple['username'],
            'role': user_tuple['role'],
            'department_id': user_tuple['department_id'],
            'is_hod': user_tuple['is_hod'],
        }
        if user['department_id']:
            dept_result = fetch_department_name(cursor, user['department_id'])
            user['department_name'] = dept_result['name'] if dept_result else None
        else:
            user['department_name'] = None
        user_permissions_raw = get_user_permissions(user_id)
        user_permissions = []
        for perm in user_permissions_raw:
            module = perm['module'] or 'General'
            module = module.capitalize() if module else 'General'
            user_permissions.append({
                'name': perm['name'],
                'description': perm['description'],
                'module': module,
                'source': perm['source'],
                'department_id': perm.get('department_id'),
                'expires_at': perm.get('expires_at'),
            })
        all_permissions_raw = fetch_permissions_with_description(cursor)
        permissions_by_module = {}
        for perm_tuple in all_permissions_raw:
            perm = {
                'id': perm_tuple['id'],
                'name': perm_tuple['name'],
                'description': perm_tuple['description'],
                'module': perm_tuple['module'] or 'General',
            }
            module = perm['module']
            if module not in permissions_by_module:
                permissions_by_module[module] = []
            permissions_by_module[module].append(perm)
        departments_raw = fetch_departments(cursor)
        departments = [{'id': dept['id'], 'name': dept['name']} for dept in departments_raw]
        courses_raw = fetch_courses(cursor)
        courses = [
            {'id': course['id'], 'name': course['name'], 'department_id': course['department_id']}
            for course in courses_raw
        ]
        classes_raw = fetch_classes(cursor)
        classes = [{'id': course['id'], 'name': course['name']} for course in classes_raw]
        permission_groups_raw = fetch_permission_groups(cursor)
        permission_groups = []
        for group_tuple in permission_groups_raw:
            permission_groups.append({
                'id': group_tuple['id'],
                'name': group_tuple['name'],
                'description': group_tuple['description'],
                'module': group_tuple['module'],
                'permissions': group_tuple['permissions'],
            })
        user_groups_raw = fetch_user_groups(cursor, user_id)
        user_groups = []
        for group_tuple in user_groups_raw:
            user_groups.append({
                'group_id': group_tuple['group_id'],
                'department_id': group_tuple['department_id'],
                'name': group_tuple['name'],
            })
        return {
            'user': user,
            'user_permissions': user_permissions,
            'permissions_by_module': permissions_by_module,
            'departments': departments,
            'courses': courses,
            'classes': classes,
            'permission_groups': permission_groups,
            'user_groups': user_groups,
        }
    finally:
        cursor.close()
        connection.close()


def assign_permission_group(user_id, group_id, department_id, session):
    """Grant a permission group. Return the JSON payload and status."""
    connection, cursor = _cursor()
    try:
        department_id = int(department_id) if department_id else None
        group_id = int(group_id)
        if fetch_active_user_group(cursor, user_id, group_id, department_id):
            return {'error': 'Permission group already assigned'}, 400
        insert_user_group(cursor, user_id, group_id, department_id, session.get('user_id'))
        connection.commit()
        group_name = fetch_group_name(cursor, group_id)['name']
        log_activity(
            session['user_id'],
            'grant_permission_group',
            f'Granted permission group {group_name} to user {user_id}' +
            (f' for department {department_id}' if department_id else ''),
        )
        return {'message': 'Permission group granted successfully'}, 200
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error granting permission group: {str(exc)}")
        return {'error': 'Failed to grant permission group'}, 500
    finally:
        cursor.close()
        connection.close()


def unassign_permission_group(user_id, group_id, department_id, session):
    """Revoke a permission group. Return the JSON payload and status."""
    connection, cursor = _cursor()
    try:
        department_id = int(department_id) if department_id else None
        group_id = int(group_id)
        group_result = fetch_group_name(cursor, group_id)
        if not group_result:
            return {'error': 'Permission group not found'}, 404
        group_name = group_result['name']
        delete_user_group(cursor, user_id, group_id, department_id)
        if cursor.rowcount == 0:
            return {'error': 'Permission group assignment not found'}, 404
        connection.commit()
        log_activity(
            session['user_id'],
            'revoke_permission_group',
            f'Revoked permission group {group_name} from user {user_id}' +
            (f' for department {department_id}' if department_id else ''),
        )
        return {'message': 'Permission group revoked successfully'}, 200
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error revoking permission group: {str(exc)}")
        return {'error': 'Failed to revoke permission group'}, 500
    finally:
        cursor.close()
        connection.close()
