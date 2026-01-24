"""
Admin Permissions Routes
Handles viewing and managing user permissions
"""

from flask import Blueprint, render_template, session
from security import get_user_permissions
from routes.admin_utils import admin_required

permissions_bp = Blueprint('permissions', __name__, url_prefix='/admin')


@permissions_bp.route('/my-permissions')
@admin_required
def my_permissions():
    """Display current user's permissions"""
    user_id = session.get('user_id')
    role = session.get('role')
    
    permissions = get_user_permissions(user_id, role)
    
    return render_template(
        'admin/my_permissions.html',
        permissions=permissions,
        user_id=user_id,
        role=role
    )
