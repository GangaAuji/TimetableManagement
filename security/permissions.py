"""
Department-Filtered Access Control Helper Functions
Django-like permission system with department-level filtering
"""
from flask import session
from database import get_db_connection

def get_accessible_student_ids(user_id=None):
    """
    Get list of student IDs the user has access to based on department permissions
    Returns: list of student IDs or None (None means access to all)
    """
    if not user_id:
        user_id = session.get('user_id')
    
    user_role = session.get('role')
    user_dept_id = session.get('department_id')
    is_hod = session.get('is_hod', False)
    
    # Super Admin has access to all
    if user_role == 'Super Admin':
        return None
    
    # Admin has access to all
    if user_role == 'Admin':
        return None
    
    # HOD has access to their department only
    if is_hod and user_dept_id:
        connection = get_db_connection()

        cursor = connection.cursor(dictionary=True)
        try:
            # Get students through their course department
            cursor.execute("""
                SELECT DISTINCT s.id
                FROM students s
                JOIN courses c ON s.course_id = c.id
                WHERE c.department_id = %s
            """, [user_dept_id])
            return [row[0] for row in cursor.fetchall()]
        finally:

            cursor.close()

            connection.close()
    
    # Check for individual department-specific permissions
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT DISTINCT up.department_id
            FROM user_permissions up
            JOIN permissions p ON up.permission_id = p.id
            WHERE up.user_id = %s 
            AND p.name IN ('view_students', 'edit_student', 'add_student', 'delete_student')
            AND up.department_id IS NOT NULL
            AND up.is_active = TRUE
        """, [user_id])
        dept_ids = [row[0] for row in cursor.fetchall()]
        
        if dept_ids:
            format_strings = ','.join(['%s'] * len(dept_ids))
            cursor.execute(f"""
                SELECT DISTINCT s.id
                FROM students s
                JOIN courses c ON s.course_id = c.id
                WHERE c.department_id IN ({format_strings})
            """, dept_ids)
            return [row[0] for row in cursor.fetchall()]
    finally:

        cursor.close()

        connection.close()
    
    # No access by default
    return []

def get_accessible_faculty_ids(user_id=None):
    """
    Get list of faculty IDs the user has access to based on department permissions
    """
    if not user_id:
        user_id = session.get('user_id')
    
    user_role = session.get('role')
    user_dept_id = session.get('department_id')
    is_hod = session.get('is_hod', False)
    
    # Super Admin has access to all
    if user_role == 'Super Admin':
        return None
    
    # Admin has access to all
    if user_role == 'Admin':
        return None
    
    # HOD has access to their department only
    if is_hod and user_dept_id:
        connection = get_db_connection()

        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT id FROM faculty
                WHERE department_id = %s
            """, [user_dept_id])
            return [row[0] for row in cursor.fetchall()]
        finally:

            cursor.close()

            connection.close()
    
    # Check for individual department-specific permissions
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT DISTINCT up.department_id
            FROM user_permissions up
            JOIN permissions p ON up.permission_id = p.id
            WHERE up.user_id = %s 
            AND p.name IN ('view_faculty', 'edit_faculty', 'add_faculty', 'delete_faculty')
            AND up.department_id IS NOT NULL
            AND up.is_active = TRUE
        """, [user_id])
        dept_ids = [row[0] for row in cursor.fetchall()]
        
        if dept_ids:
            format_strings = ','.join(['%s'] * len(dept_ids))
            cursor.execute(f"""
                SELECT id FROM faculty
                WHERE department_id IN ({format_strings})
            """, dept_ids)
            return [row[0] for row in cursor.fetchall()]
    finally:

        cursor.close()

        connection.close()
    
    # No access by default
    return []

def get_department_filter_clause(table_alias='', user_id=None):
    """
    Generate SQL WHERE clause for department filtering
    Returns: (where_clause, params)
    """
    if not user_id:
        user_id = session.get('user_id')
    
    user_role = session.get('role')
    user_dept_id = session.get('department_id')
    is_hod = session.get('is_hod', False)
    
    # Super Admin and Admin have no restrictions
    if user_role in ('Super Admin', 'Admin'):
        return ('', [])
    
    # HOD restricted to their department
    if is_hod and user_dept_id:
        prefix = f"{table_alias}." if table_alias else ""
        return (f"AND {prefix}department_id = %s", [user_dept_id])
    
    # Check for specific department permissions
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT DISTINCT up.department_id
            FROM user_permissions up
            WHERE up.user_id = %s 
            AND up.department_id IS NOT NULL
            AND up.is_active = TRUE
        """, [user_id])
        dept_ids = [row[0] for row in cursor.fetchall()]
        
        if dept_ids:
            prefix = f"{table_alias}." if table_alias else ""
            placeholders = ','.join(['%s'] * len(dept_ids))
            return (f"AND {prefix}department_id IN ({placeholders})", dept_ids)
    finally:

        cursor.close()

        connection.close()
    
    # No access - return impossible condition
    return ('AND 1=0', [])

def can_access_department(department_id, user_id=None):
    """
    Check if user can access a specific department
    """
    if not user_id:
        user_id = session.get('user_id')
    
    user_role = session.get('role')
    user_dept_id = session.get('department_id')
    is_hod = session.get('is_hod', False)
    
    # Super Admin and Admin can access all
    if user_role in ('Super Admin', 'Admin'):
        return True
    
    # HOD can access only their department
    if is_hod:
        return user_dept_id == department_id
    
    # Check individual permissions
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT 1 FROM user_permissions up
            WHERE up.user_id = %s 
            AND (up.department_id = %s OR up.department_id IS NULL)
            AND up.is_active = TRUE
            LIMIT 1
        """, [user_id, department_id])
        return cursor.fetchone() is not None
    finally:

        cursor.close()

        connection.close()
