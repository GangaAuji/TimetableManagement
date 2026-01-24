"""
Template Helper Functions for Permission-based UI Control
Provides Django-like template permission checks
"""

from flask import session
from security import check_user_permission, get_user_permissions

def user_has_perm(permission_name, department_id=None, course_id=None, class_id=None):
    """
    Check if current user has a specific permission
    
    Usage in templates:
        {% if user_has_perm('students_add_student') %}
            <button>Add Student</button>
        {% endif %}
        
        {% if user_has_perm('students_view_student', department_id=dept.id) %}
            <a href="/students?dept={{ dept.id }}">View Students</a>
        {% endif %}
    
    Args:
        permission_name: Name of the permission (e.g., 'students_add_student')
        department_id: Optional department ID for department-specific check
        course_id: Optional course ID for course-specific check
        class_id: Optional class ID for class-specific check
    
    Returns:
        bool: True if user has the permission, False otherwise
    """
    user_id = session.get('user_id')
    user_role = session.get('role')
    
    if not user_id:
        return False
    
    # Super Admin has all permissions
    if user_role == 'Super Admin':
        return True
    
    has_perm, _, _ = check_user_permission(user_id, permission_name, department_id)
    return has_perm


def user_has_any_perm(permission_names, department_id=None):
    """
    Check if user has ANY of the specified permissions
    
    Usage:
        {% if user_has_any_perm(['students_add_student', 'students_change_student']) %}
            <div class="actions">...</div>
        {% endif %}
    """
    for perm in permission_names:
        if user_has_perm(perm, department_id):
            return True
    return False


def user_has_all_perms(permission_names, department_id=None):
    """
    Check if user has ALL of the specified permissions
    
    Usage:
        {% if user_has_all_perms(['students_view_student', 'students_export_data']) %}
            <button>Export Students</button>
        {% endif %}
    """
    for perm in permission_names:
        if not user_has_perm(perm, department_id):
            return False
    return True


def get_user_perms(module=None):
    """
    Get all permissions for current user, optionally filtered by module
    
    Usage:
        {% set perms = get_user_perms('students') %}
        {% if 'students_add_student' in perms %}
            <button>Add</button>
        {% endif %}
    
    Returns:
        list: List of permission names ['students_view_student', 'students_add_student', ...]
    """
    user_id = session.get('user_id')
    user_role = session.get('role')
    
    if not user_id:
        return []
    
    # Super Admin has all permissions - return a special marker
    if user_role == 'Super Admin':
        return ['__super_admin__']  # Special marker for templates
    
    perms = get_user_permissions(user_id)
    
    if module:
        return [p['name'] for p in perms if p['module'] == module]
    return [p['name'] for p in perms]


def get_user_perms_by_module():
    """
    Get permissions grouped by module
    
    Returns:
        dict: {'students': ['students_view_student', ...], 'faculty': [...]}
    """
    user_id = session.get('user_id')
    
    if not user_id:
        return {}
    
    perms = get_user_permissions(user_id)
    
    grouped = {}
    for perm in perms:
        module = perm['module']
        if module not in grouped:
            grouped[module] = []
        grouped[module].append(perm['name'])
    
    return grouped


def can_view_module(module_name):
    """
    Check if user can access a module at all
    Checks for any view permission in the module
    
    Usage:
        {% if can_view_module('students') %}
            <li><a href="/admin/students">Students</a></li>
        {% endif %}
    """
    perms = get_user_perms(module_name)
    
    # Super Admin check
    if '__super_admin__' in perms:
        return True
    
    # Check for any view permission
    view_perms = [p for p in perms if 'view' in p]
    return len(view_perms) > 0


def can_manage_module(module_name):
    """
    Check if user can manage (add/change/delete) in a module
    
    Usage:
        {% if can_manage_module('students') %}
            <button>Manage Students</button>
        {% endif %}
    """
    perms = get_user_perms(module_name)
    
    # Super Admin check
    if '__super_admin__' in perms:
        return True
    
    # Check for any management permission (add, change, delete)
    manage_perms = [p for p in perms if any(action in p for action in ['add', 'change', 'delete'])]
    return len(manage_perms) > 0


def get_accessible_departments():
    """
    Get departments the current user can access
    
    Returns:
        list: List of (department_id, department_name) tuples
    """
    from security import get_accessible_departments as get_depts
    
    user_id = session.get('user_id')
    if not user_id:
        return []
    
    return get_depts(user_id)


def is_hod():
    """
    Check if current user is a Head of Department
    
    Usage:
        {% if is_hod() %}
            <div class="hod-dashboard">...</div>
        {% endif %}
    """
    return session.get('is_hod', False)


def is_super_admin():
    """
    Check if current user is Super Admin
    """
    return session.get('role') == 'Super Admin'


def get_user_department():
    """
    Get current user's department ID
    
    Returns:
        int or None: Department ID if user belongs to a department
    """
    return session.get('department_id')


def user_can_access_department(department_id):
    """
    Check if user can access a specific department
    
    Usage:
        {% if user_can_access_department(dept_id) %}
            <a href="/students?dept={{ dept_id }}">View Students</a>
        {% endif %}
    """
    if is_super_admin():
        return True
    
    accessible_depts = get_accessible_departments()
    dept_ids = [d[0] for d in accessible_depts]
    
    return department_id in dept_ids


# Context processor to make all helpers available in templates
def register_template_helpers(app):
    """
    Register all template helper functions with Flask app
    
    Call this in app.py:
        from template_helpers import register_template_helpers
        register_template_helpers(app)
    """
    app.jinja_env.globals.update({
        'user_has_perm': user_has_perm,
        'user_has_any_perm': user_has_any_perm,
        'user_has_all_perms': user_has_all_perms,
        'get_user_perms': get_user_perms,
        'get_user_perms_by_module': get_user_perms_by_module,
        'can_view_module': can_view_module,
        'can_manage_module': can_manage_module,
        'get_accessible_departments': get_accessible_departments,
        'is_hod': is_hod,
        'is_super_admin': is_super_admin,
        'get_user_department': get_user_department,
        'user_can_access_department': user_can_access_department,
    })
    
    print("✓ Template helpers registered successfully")
