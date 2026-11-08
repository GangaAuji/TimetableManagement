"""Built-in roles and the permissions each one is granted by default.

ROLE_DEFAULTS maps role -> {permission: since}. `since` is the defaults
version that introduced the grant. Raise DEFAULTS_VERSION and use it as
`since` when a later release adds a grant; databases already set up then get
that grant once on their next seed run.
"""

from collections import namedtuple

from seeders.data.permissions import PERMISSIONS

Role = namedtuple('Role', 'name description level')

DEFAULTS_VERSION = 1

ROLES = (
    Role('Super Admin', 'Has complete access to all system features', 1),
    Role('Admin', 'Manages academic setup, timetables, people and reports', 2),
    Role('HOD', 'Head of department', 3),
    Role('Teacher', 'Has access to teaching-related features', 4),
    Role('Student', 'Has access to student-related features', 5),
)


def _grants(names, since=1):
    return {name: since for name in names}


def _crud(prefix, suffix='', actions=('add', 'change', 'delete', 'view')):
    return tuple(f'{prefix}_{action}{suffix}' for action in actions)


_ADMIN = (
    *_crud('academicyears'), *_crud('allocations'), *_crud('batches'), *_crud('departments'),
    *_crud('semesters'), *_crud('shifts'), *_crud('holidays'), *_crud('subjects', '_subject'),
    *_crud('courses', '_course', ('add', 'change', 'view')), *_crud('rooms', '_room', ('add', 'change', 'view')),
    'attendance_manage', 'attendance_manage_faculty', 'attendance_view', 'attendance_view_defaulters',
    'attendance_view_details', 'attendance_view_faculty', 'attendance_view_reports',
    'courses_view_subjects',
    'faculty_add_absence', 'faculty_add_faculty', 'faculty_approve_absence', 'faculty_approve_proxy',
    'faculty_change_availability', 'faculty_change_faculty', 'faculty_delete_absence', 'faculty_delete_faculty',
    'faculty_export_data', 'faculty_view_absence', 'faculty_view_availability', 'faculty_view_faculty',
    'faculty_view_proxy', 'faculty_view_timetable',
    'reports_export', 'reports_view', 'reports_view_attendance', 'reports_view_audit',
    'reports_view_invitations', 'reports_view_proxy', 'reports_view_shifts', 'reports_view_timetable',
    'students_add_student', 'students_bulk_invite', 'students_change_student', 'students_view_student',
    'timetable_change', 'timetable_delete', 'timetable_export', 'timetable_generate', 'timetable_view',
    'timetable_view_conflicts',
    'users_view_user',
)

_HOD = (
    *_crud('allocations'), *_crud('holidays'),
    'academicyears_view', 'batches_view', 'courses_view_course', 'courses_view_subjects', 'departments_view',
    'semesters_view', 'subjects_view_subject', 'rooms_view_room',
    'attendance_view', 'attendance_view_defaulters', 'attendance_view_details', 'attendance_view_faculty',
    'faculty_approve_absence', 'faculty_approve_proxy', 'faculty_export_data', 'faculty_view_absence',
    'faculty_view_availability', 'faculty_view_faculty', 'faculty_view_proxy', 'faculty_view_timetable',
    'reports_view', 'reports_view_attendance', 'reports_view_timetable',
    'shifts_change', 'shifts_view',
    'students_add_student', 'students_bulk_invite', 'students_change_student', 'students_delete_student',
    'students_export_data', 'students_view_student',
    'timetable_export', 'timetable_view', 'timetable_view_conflicts',
)

_TEACHER = (
    'faculty_add_absence', 'faculty_change_availability', 'faculty_view_availability', 'faculty_view_timetable',
    'students_view_student', 'timetable_view',
)

ROLE_DEFAULTS = {
    'Super Admin': {permission.name: permission.since for permission in PERMISSIONS},
    'Admin': _grants(_ADMIN),
    'HOD': _grants(_HOD),
    'Teacher': _grants(_TEACHER),
    'Student': _grants(('timetable_view',)),
}
