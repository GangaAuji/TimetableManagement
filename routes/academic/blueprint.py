"""Academic blueprint. View modules register their routes on it."""

from flask import Blueprint

academic_bp = Blueprint('academic', __name__, url_prefix='/admin/academic')
