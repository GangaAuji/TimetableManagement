"""User management screens."""

from routes.user_management.blueprint import user_mgmt_bp
from routes.user_management import actions, permissions, roles, users

__all__ = ['user_mgmt_bp']
