"""
Admin Department Management Routes
Handles department listing and management
"""

from flask import Blueprint, jsonify
from database import get_db_connection
from routes.admin_utils import admin_required

departments_bp = Blueprint('departments', __name__, url_prefix='/admin')


@departments_bp.route('/departments/list')
@admin_required
def list_departments():
    """API endpoint to get all departments for dropdowns"""
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, name FROM departments ORDER BY name")
        departments = cursor.fetchall()
        return jsonify([{'id': d[0], 'name': d[1]} for d in departments])
    finally:

        cursor.close()

        connection.close()
