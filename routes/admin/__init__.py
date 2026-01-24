from flask import Blueprint

# Import all module blueprints (relative imports)
from .students import students_bp
from .faculty import faculty_bp
from .rooms import rooms_bp
from .timetable import timetable_bp
from .holiday import holiday_bp
from .invitations import invitations_bp
from .proxy_log import proxy_bp
from .audit_logs import audit_logs_bp
from .dashboard import dashboard_bp
from .departments import departments_bp
from .api import api_bp
from .permissions import permissions_bp

# Export all blueprints for registration
__all__ = [
    'students_bp', 
    'faculty_bp', 
    'rooms_bp', 
    'timetable_bp', 
    'holiday_bp', 
    'invitations_bp', 
    'proxy_bp',
    'audit_logs_bp',
    'dashboard_bp',
    'departments_bp',
    'api_bp',
    'permissions_bp'
]