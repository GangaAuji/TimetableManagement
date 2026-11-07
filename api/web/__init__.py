"""JSON API. Routes are /api/<resource>, with no version prefix."""

from flask import Blueprint

from api.web.account import register_account_routes
from api.web.attendance import register_attendance_routes
from api.web.audit import register_audit_routes
from api.web.branding import register_branding_routes
from api.web.catalog import register_catalog_routes
from api.web.courses import register_course_routes
from api.web.dashboard import register_dashboard_routes
from api.web.departments import register_department_routes
from api.web.devices import register_device_routes
from api.web.invitations import register_invitation_routes
from api.web.people import register_people_routes
from api.web.permissions import register_permission_routes
from api.web.portal_actions import register_portal_action_routes
from api.web.proxy import register_proxy_routes
from api.web.reports import register_report_routes
from api.web.roles import register_role_routes
from api.web.rooms import register_room_routes
from api.web.security import apply_api_security_headers, reject_unsafe_request, require_authenticated_api
from api.web.session import register_session_routes
from api.web.settings import register_settings_routes
from api.web.shifts import register_shift_routes
from api.web.student import register_student_home_routes
from api.web.teacher import register_teacher_routes
from api.web.timetable import register_timetable_routes
from api.web.users import register_user_routes

json_api_bp = Blueprint('json_api', __name__, url_prefix='/api')
json_api_bp.before_request(reject_unsafe_request)
json_api_bp.before_request(require_authenticated_api)
json_api_bp.after_request(apply_api_security_headers)

register_session_routes(json_api_bp)
register_branding_routes(json_api_bp)
register_dashboard_routes(json_api_bp)
register_room_routes(json_api_bp)
register_department_routes(json_api_bp)
register_course_routes(json_api_bp)
register_catalog_routes(json_api_bp)
register_people_routes(json_api_bp)
register_user_routes(json_api_bp)
register_role_routes(json_api_bp)
register_permission_routes(json_api_bp)
register_invitation_routes(json_api_bp)
register_audit_routes(json_api_bp)
register_settings_routes(json_api_bp)
register_timetable_routes(json_api_bp)
register_attendance_routes(json_api_bp)
register_report_routes(json_api_bp)
register_shift_routes(json_api_bp)
register_proxy_routes(json_api_bp)
register_device_routes(json_api_bp)
register_account_routes(json_api_bp)
register_teacher_routes(json_api_bp)
register_student_home_routes(json_api_bp)
register_portal_action_routes(json_api_bp)

__all__ = ['json_api_bp']
