"""
Admin Department Management Routes
Handles department listing and management
"""

from flask import Blueprint, jsonify
from routes.admin_utils import admin_required
from services.admin_departments import list_department_choices

departments_bp = Blueprint('departments', __name__, url_prefix='/admin')


@departments_bp.route('/departments/list')
@admin_required
def list_departments():
    """API endpoint to get all departments for dropdowns"""
    return jsonify(list_department_choices())
