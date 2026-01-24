from flask import Blueprint

# Import the main teacher blueprint
from .teacher import teacher_bp

# Import all the route modules to register their routes with teacher_bp
from . import absences
from . import availability
from . import classes
from . import timetable
from . import shifts
from . import proxy_requests

# Export all blueprints for registration
__all__ = ['teacher_bp']
