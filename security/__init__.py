import json
from functools import wraps
from flask import session, flash, redirect, url_for, request, current_app, has_request_context
from extensions import get_db_connection
import datetime


def login_required(f):
    """
    Decorator to ensure user is logged in before accessing a route
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def has_permission(permission_name, department_id=None):
    """
    Decorator to check if the current user has the required permission
    Supports department-based filtering for HOD access control
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login'))

            user_id = session.get('user_id')
            user_role = session.get('role')
            user_dept_id = session.get('department_id')

            # Super Admin has all permissions
            if user_role == 'Super Admin':
                return f(*args, **kwargs)

            # Add debug logging
            current_app.logger.debug(f"Checking permission {permission_name} for user {user_id}, role {user_role}, dept {user_dept_id}")

            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            try:
                # Check if user has the permission through various sources
                has_perm = False
                
                # 1. Check role-based permissions
                cursor.execute("""
                    SELECT 1 FROM permissions p
                    JOIN role_permissions rp ON p.id = rp.permission_id
                    JOIN roles r ON rp.role_id = r.id
                    WHERE r.name = %s AND p.name = %s
                    LIMIT 1
                """, [user_role, permission_name])
                if cursor.fetchone():
                    has_perm = True
                    current_app.logger.debug(f"Permission granted via role: {user_role}")
                
                # 2. Check individual user permissions
                if not has_perm:
                    dept_filter = ""
                    params = [user_id, permission_name]
                    
                    # If department filtering is required
                    if department_id:
                        dept_filter = "AND (up.department_id IS NULL OR up.department_id = %s)"
                        params.append(department_id)
                    elif user_dept_id:
                        # For HODs, check department-specific permissions
                        dept_filter = "AND (up.department_id IS NULL OR up.department_id = %s)"
                        params.append(user_dept_id)
                    
                    cursor.execute(f"""
                        SELECT 1 FROM user_permissions up
                        JOIN permissions p ON up.permission_id = p.id
                        WHERE up.user_id = %s AND p.name = %s 
                        AND up.is_active = TRUE 
                        AND (up.expires_at IS NULL OR up.expires_at > NOW())
                        {dept_filter}
                        LIMIT 1
                    """, params)
                    if cursor.fetchone():
                        has_perm = True
                        current_app.logger.debug(f"Permission granted via individual assignment")
                
                # 3. Check permission groups
                if not has_perm:
                    dept_filter = ""
                    params = [user_id, permission_name]
                    
                    if department_id:
                        dept_filter = "AND (upg.department_id IS NULL OR upg.department_id = %s)"
                        params.append(department_id)
                    elif user_dept_id:
                        dept_filter = "AND (upg.department_id IS NULL OR upg.department_id = %s)"
                        params.append(user_dept_id)
                    
                    cursor.execute(f"""
                        SELECT 1 FROM user_permission_groups upg
                        JOIN permission_group_permissions pgp ON upg.group_id = pgp.group_id
                        JOIN permissions p ON pgp.permission_id = p.id
                        WHERE upg.user_id = %s AND p.name = %s 
                        AND upg.is_active = TRUE
                        {dept_filter}
                        LIMIT 1
                    """, params)
                    if cursor.fetchone():
                        has_perm = True
                        current_app.logger.debug(f"Permission granted via permission group")

                if not has_perm:
                    current_app.logger.warning(f"Permission denied: {permission_name} for user {user_id}")
                    flash('You do not have permission to access this page.', 'danger')
                    
                    # Redirect based on role
                    if user_role == 'Teacher':
                        return redirect(url_for('teacher.dashboard'))
                    elif user_role == 'Student':
                        return redirect(url_for('student.dashboard'))
                    elif user_role in ('Admin', 'Super Admin'):
                        return redirect(url_for('admin.dashboard'))
                    else:
                        return redirect(url_for('auth.login'))
                
                current_app.logger.debug(f"Permission granted: {permission_name}")
                return f(*args, **kwargs)
            finally:
                cursor.close()
                connection.close()
        return decorated_function
    return decorator


def _request_details():
    if not has_request_context():
        return None, None, None, None, None
    return (
        request.remote_addr,
        request.user_agent.string,
        request.method,
        request.path,
        session.get('session_id'),
    )


def _write_activity(cursor, user_id, activity_type, description, entity_type, entity_id, old_values, new_values):
    address, agent, method, path, session_id = _request_details()
    if user_id:
        cursor.execute(
            """
            INSERT INTO user_activity_log (user_id, activity_type, description, ip_address, user_agent)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, activity_type, description, address, agent),
        )
    cursor.execute(
        """
        INSERT INTO audit_logs
        (user_id, username, action, entity_type, entity_id, old_values, new_values,
         ip_address, user_agent, request_method, request_url, status, session_id)
        VALUES (%s, (SELECT username FROM users WHERE id = %s), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            user_id,
            user_id,
            activity_type,
            entity_type,
            entity_id,
            json.dumps(old_values, default=str) if old_values else None,
            json.dumps(new_values, default=str) if new_values else None,
            address,
            agent,
            method,
            path,
            'success',
            session_id,
        ),
    )


def log_activity(user_id, activity_type, description=None, entity_type=None, entity_id=None,
                 old_values=None, new_values=None, cursor=None):
    """Write the action to user_activity_log and audit_logs.

    Pass the cursor of the transaction that made the change: the audit rows then
    commit or roll back with it, and a failed write raises so the caller rolls
    back. Without a cursor the rows are committed on their own connection and a
    failure is only logged; that is for events that change nothing else.
    """
    if cursor is not None:
        _write_activity(cursor, user_id, activity_type, description, entity_type, entity_id, old_values, new_values)
        return
    connection = get_db_connection()
    own = connection.cursor()
    try:
        _write_activity(own, user_id, activity_type, description, entity_type, entity_id, old_values, new_values)
        connection.commit()
    except Exception as e:
        current_app.logger.error(f"Failed to log activity: {str(e)}")
    finally:
        own.close()
        connection.close()


def log_login_attempt(username, status='success', failure_reason=None, cursor=None):
    """Record a sign-in attempt.

    A failure is always committed on its own connection, so it survives the
    request rolling back. A success passes the sign-in's cursor.
    """
    address, agent = _request_details()[:2]
    statement = """
        INSERT INTO login_attempts (username, ip_address, user_agent, status, failure_reason)
        VALUES (%s, %s, %s, %s, %s)
    """
    values = (username, address or '', agent, status, failure_reason)
    if cursor is not None:
        cursor.execute(statement, values)
        return
    connection = get_db_connection()
    own = connection.cursor()
    try:
        own.execute(statement, values)
        connection.commit()
    except Exception as e:
        current_app.logger.error(f"Failed to log login attempt: {str(e)}")
    finally:
        own.close()
        connection.close()

def get_user_permissions(user_id):
    """
    Get all permissions for a user based on their role, individual assignments, and groups
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        # Get role-based permissions
        cursor.execute("""
            SELECT DISTINCT p.name, p.description, p.module, 'role' as source,
                   NULL as department_id, NULL as expires_at
            FROM users u
            JOIN roles r ON u.role = r.name
            JOIN role_permissions rp ON r.id = rp.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE u.id = %s
            
            UNION ALL
            
            -- Get individual permissions
            SELECT DISTINCT p.name, p.description, p.module, 'individual' as source,
                   up.department_id, up.expires_at
            FROM user_permissions up
            JOIN permissions p ON up.permission_id = p.id
            WHERE up.user_id = %s AND up.is_active = TRUE 
            AND (up.expires_at IS NULL OR up.expires_at > NOW())
            
            UNION ALL
            
            -- Get group permissions
            SELECT DISTINCT p.name, p.description, p.module, 'group' as source,
                   upg.department_id, NULL as expires_at
            FROM user_permission_groups upg
            JOIN permission_group_permissions pgp ON upg.group_id = pgp.group_id
            JOIN permissions p ON pgp.permission_id = p.id
            WHERE upg.user_id = %s AND upg.is_active = TRUE
            
            ORDER BY module, name
        """, [user_id, user_id, user_id])
        results = cursor.fetchall()
        cursor.close()
        connection.close()
        return results
    except:
        connection.close()
        raise


def check_user_permission(user_id, permission_name, department_id=None):
    """
    Check if a user has a specific permission, optionally filtered by department
    Returns: (has_permission: bool, source: str, department_restricted: bool)
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        # Get user info
        cursor.execute("SELECT role, department_id, is_hod FROM users WHERE id = %s", [user_id])
        user_info = cursor.fetchone()
        if not user_info:
            cursor.close()
            connection.close()
            return False, None, False
        
        user_role = user_info['role']
        user_dept_id = user_info['department_id']
        is_hod = user_info['is_hod']
        
        # Super Admin has all permissions
        if user_role == 'Super Admin':
            return True, 'super_admin', False
        
        # Check role-based permissions
        cursor.execute("""
            SELECT 1 FROM permissions p
            JOIN role_permissions rp ON p.id = rp.permission_id
            JOIN roles r ON rp.role_id = r.id
            WHERE r.name = %s AND p.name = %s
        """, [user_role, permission_name])
        if cursor.fetchone():
            cursor.close()
            connection.close()
            return True, 'role', False
        
        # Check individual permissions
        dept_params = [user_id, permission_name]
        dept_filter = ""
        
        if department_id:
            dept_filter = "AND (up.department_id IS NULL OR up.department_id = %s)"
            dept_params.append(department_id)
        
        cursor.execute(f"""
            SELECT up.department_id FROM user_permissions up
            JOIN permissions p ON up.permission_id = p.id
            WHERE up.user_id = %s AND p.name = %s 
            AND up.is_active = TRUE 
            AND (up.expires_at IS NULL OR up.expires_at > NOW())
            {dept_filter}
        """, dept_params)
        result = cursor.fetchone()
        if result:
            cursor.close()
            connection.close()
            return True, 'individual', result.get('department_id') is not None
        
        # Check permission groups
        cursor.execute(f"""
            SELECT upg.department_id FROM user_permission_groups upg
            JOIN permission_group_permissions pgp ON upg.group_id = pgp.group_id
            JOIN permissions p ON pgp.permission_id = p.id
            WHERE upg.user_id = %s AND p.name = %s 
            AND upg.is_active = TRUE
            {dept_filter}
        """, dept_params)
        result = cursor.fetchone()
        if result:
            cursor.close()
            connection.close()
            return True, 'group', result.get('department_id') is not None
        
        cursor.close()
        connection.close()
        return False, None, False
    except:
        connection.close()
        raise


def get_accessible_departments(user_id):
    """
    Get list of departments the user has access to based on their permissions
    Returns all departments for Super Admin, user's department for HOD, etc.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        # Get user info
        cursor.execute("SELECT role, department_id, is_hod FROM users WHERE id = %s", [user_id])
        user_info = cursor.fetchone()
        if not user_info:
            cursor.close()
            connection.close()
            return []
        
        user_role = user_info['role']
        user_dept_id = user_info['department_id']
        is_hod = user_info['is_hod']
        
        # Super Admin can access all departments
        if user_role == 'Super Admin':
            cursor.execute("SELECT id, name FROM departments ORDER BY name")
            return cursor.fetchall()
        
        # HOD can access their department
        if is_hod and user_dept_id:
            cursor.execute("SELECT id, name FROM departments WHERE id = %s", [user_dept_id])
            results = cursor.fetchall()
            cursor.close()
            connection.close()
            return results
        
        # Check department-specific permissions
        cursor.execute("""
            SELECT DISTINCT d.id, d.name 
            FROM departments d
            WHERE d.id IN (
                SELECT DISTINCT up.department_id 
                FROM user_permissions up 
                WHERE up.user_id = %s AND up.department_id IS NOT NULL
                AND up.is_active = TRUE 
                AND (up.expires_at IS NULL OR up.expires_at > NOW())
                
                UNION
                
                SELECT DISTINCT upg.department_id 
                FROM user_permission_groups upg 
                WHERE upg.user_id = %s AND upg.department_id IS NOT NULL
                AND upg.is_active = TRUE
            )
            ORDER BY d.name
        """, [user_id, user_id])
        dept_specific = cursor.fetchall()
        
        # If user has department-specific permissions, return those
        if dept_specific:
            cursor.close()
            connection.close()
            return dept_specific
        
        # If user has general permissions but no department-specific ones,
        # and they're not an HOD, they may have access to all departments
        # (depending on business logic)
        cursor.close()
        connection.close()
        return []
    except:
        connection.close()
        raise


ACCOUNT_PROTECTED = 'You cannot change permissions for that account.'
PERMISSION_UNHELD = 'You can only grant permissions you hold yourself.'


def _grant_problem(cursor, actor_id, user_id, permission_names, department_id):
    from security.authority import account_problem, unheld_permissions

    if not actor_id or account_problem(cursor, actor_id, user_id) == 'protected':
        return ACCOUNT_PROTECTED
    if unheld_permissions(cursor, actor_id, permission_names, department_id):
        return PERMISSION_UNHELD
    return None


def permission_grant_problem(actor_id, user_id, permission_names, department_id=None):
    """Return ACCOUNT_PROTECTED, PERMISSION_UNHELD, or None before granting several permissions."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        return _grant_problem(cursor, actor_id, user_id, permission_names, department_id)
    finally:
        cursor.close()
        connection.close()


def grant_user_permission(user_id, permission_name, department_id=None, course_id=None, class_id=None, granted_by=None, expires_at=None, notes=None):
    """
    Grant a specific permission to a user with optional department/course/class restrictions.
    granted_by must manage the account and hold the permission (ACCOUNT_PROTECTED, PERMISSION_UNHELD).
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        problem = _grant_problem(cursor, granted_by, user_id, [permission_name], department_id)
        if problem:
            cursor.close()
            connection.close()
            return False, problem
        # Get permission ID
        cursor.execute("SELECT id FROM permissions WHERE name = %s", [permission_name])
        perm_result = cursor.fetchone()
        if not perm_result:
            cursor.close()
            connection.close()
            return False, "Permission not found"
        
        permission_id = perm_result['id']
        
        # Check if already exists
        cursor.execute("""
            SELECT id FROM user_permissions 
            WHERE user_id = %s AND permission_id = %s 
            AND (department_id = %s OR (department_id IS NULL AND %s IS NULL))
            AND (course_id = %s OR (course_id IS NULL AND %s IS NULL))
            AND (class_id = %s OR (class_id IS NULL AND %s IS NULL))
        """, [user_id, permission_id, department_id, department_id, course_id, course_id, class_id, class_id])
        
        if cursor.fetchone():
            cursor.close()
            connection.close()
            return False, "Permission already granted with these restrictions"
        
        # Insert new permission
        cursor.execute("""
            INSERT INTO user_permissions 
            (user_id, permission_id, department_id, course_id, class_id, granted_by, expires_at, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, [user_id, permission_id, department_id, course_id, class_id, granted_by, expires_at, notes])
        
        restriction_parts = []
        if department_id:
            restriction_parts.append(f'department {department_id}')
        if course_id:
            restriction_parts.append(f'course {course_id}')
        if class_id:
            restriction_parts.append(f'class {class_id}')
        
        restriction_msg = f" for {', '.join(restriction_parts)}" if restriction_parts else ""
        
        log_activity(
            granted_by,
            'grant_permission',
            f'Granted permission {permission_name} to user {user_id}{restriction_msg}',
            entity_type='user',
            entity_id=user_id,
            new_values={'permission': permission_name, 'department_id': department_id},
            cursor=cursor,
        )
        connection.commit()
        
        cursor.close()
        connection.close()
        return True, "Permission granted successfully"
    except Exception as e:
        connection.rollback()
        cursor.close()
        connection.close()
        return False, f"Error granting permission: {str(e)}"


def revoke_user_permission(user_id, permission_name, department_id=None, revoked_by=None):
    """
    Revoke a specific permission from a user. revoked_by must manage the account (ACCOUNT_PROTECTED).
    """
    from security.authority import account_problem

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        if not revoked_by or account_problem(cursor, revoked_by, user_id) == 'protected':
            cursor.close()
            connection.close()
            return False, ACCOUNT_PROTECTED
        # Get permission ID
        cursor.execute("SELECT id FROM permissions WHERE name = %s", [permission_name])
        perm_result = cursor.fetchone()
        if not perm_result:
            cursor.close()
            connection.close()
            return False, "Permission not found"
        
        permission_id = perm_result['id']
        
        # Delete the permission
        cursor.execute("""
            DELETE FROM user_permissions 
            WHERE user_id = %s AND permission_id = %s 
            AND (department_id = %s OR (department_id IS NULL AND %s IS NULL))
        """, [user_id, permission_id, department_id, department_id])
        
        if cursor.rowcount == 0:
            cursor.close()
            connection.close()
            return False, "Permission not found or already revoked"
        
        log_activity(
            revoked_by,
            'revoke_permission',
            f'Revoked permission {permission_name} from user {user_id}' + 
            (f' for department {department_id}' if department_id else ''),
            entity_type='user',
            entity_id=user_id,
            old_values={'permission': permission_name, 'department_id': department_id},
            cursor=cursor,
        )
        connection.commit()
        
        cursor.close()
        connection.close()
        return True, "Permission revoked successfully"
    except Exception as e:
        connection.rollback()
        cursor.close()
        connection.close()
        return False, f"Error revoking permission: {str(e)}"
