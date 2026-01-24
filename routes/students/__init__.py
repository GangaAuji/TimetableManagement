from flask import Blueprint

# Import all module blueprints (relative imports)
from .student import student_bp
# Export all blueprints for registration
__all__ = ['student_bp']