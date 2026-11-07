"""User management blueprint. View modules register their routes on it."""

from flask import Blueprint, request
from utils.forms import RoleForm
from services.roles import load_permission_name_rows

user_mgmt_bp = Blueprint('user_mgmt_bp', __name__, url_prefix='/admin/users')


@user_mgmt_bp.before_request
def update_forms():
    """Update dynamic form choices before each request"""
    if 'role' in request.form:
        form = RoleForm()
        permissions = load_permission_name_rows()
        form.permissions.choices = [(p['id'], p['name']) for p in permissions]
