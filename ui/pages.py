"""Send a browser request to the React page for that URL.

The Flask views below still call render_template with the old template path.
Those templates are not rendered. This module is the one place that decides
where the browser goes, and views import it directly.
"""

from flask import Response, redirect, request

_EXACT = {
    '/login': '/',
    '/admin': '/admin',
    '/admin/login': '/admin/login',
    '/admin/dashboard': '/admin',
    '/profile': '/account',
    '/profile/edit': '/account',
    '/profile/change-password': '/account',
    '/teacher': '/',
    '/teacher/dashboard': '/',
    '/teacher/timetable': '/my-timetable',
    '/teacher/my-classes': '/my-classes',
    '/teacher/my-shifts': '/my-shifts',
    '/teacher/availability': '/my-availability',
    '/teacher/proxy-requests': '/my-proxy',
    '/teacher/assignments': '/',
    '/teacher/attendance': '/my-attendance',
    '/teacher/attendance/report': '/my-attendance',
    '/student': '/',
    '/student/dashboard': '/',
    '/student/timetable': '/my-timetable',
    '/student/attendance': '/my-attendance',
    '/admin/rooms': '/admin/rooms',
    '/admin/departments': '/admin/departments',
    '/admin/courses': '/admin/courses',
    '/admin/academic': '/admin/academic-years',
    '/admin/academic/years': '/admin/academic-years',
    '/admin/academic/semesters': '/admin/semesters',
    '/admin/academic/subjects': '/admin/subjects',
    '/admin/academic/batches': '/admin/batches',
    '/admin/academic/allocations': '/admin/allocations',
    '/admin/holidays': '/admin/holidays',
    '/admin/students': '/admin/students',
    '/admin/students/bulk-invite': '/admin/invitations',
    '/admin/faculty': '/admin/faculty',
    '/admin/users': '/admin/users',
    '/admin/users/roles': '/admin/roles',
    '/admin/users/activity-log': '/admin/audit',
    '/admin/invitations': '/admin/invitations',
    '/admin/settings': '/admin/settings',
    '/admin/branding': '/admin/settings',
    '/admin/audit-logs': '/admin/audit',
    '/admin/timetable': '/admin/timetable',
    '/admin/timetable/generate': '/admin/timetable/generate',
    '/admin/attendance': '/admin/attendance',
    '/admin/attendance/defaulters': '/admin/attendance',
    '/admin/attendance/manage': '/admin/attendance/manage',
    '/admin/attendance/faculty': '/admin/attendance/faculty',
    '/admin/attendance/mobile-logs': '/admin/attendance/mobile',
    '/admin/attendance/faculty-mobile-logs': '/admin/attendance/mobile',
    '/admin/reports': '/admin/reports',
    '/admin/reports/attendance': '/admin/reports',
    '/admin/reports/timetable': '/admin/reports',
    '/admin/reports/audit-logs': '/admin/reports',
    '/admin/reports/shifts': '/admin/reports',
    '/admin/reports/proxy-log': '/admin/reports',
    '/admin/reports/invitations': '/admin/reports',
    '/admin/shifts': '/admin/shifts',
    '/admin/shifts/change-requests': '/admin/shifts/requests',
    '/admin/shifts/faculty-availability': '/admin/shifts/availability',
    '/admin/proxy': '/admin/proxy',
    '/admin/proxy-log': '/admin/proxy',
    '/admin/mobile-devices': '/admin/devices',
    '/admin/devices': '/admin/devices',
}


def react_path(pathname):
    path = (pathname or '/').rstrip('/') or '/'
    if path in _EXACT:
        return _EXACT[path]
    if path.startswith('/register/'):
        return path
    parts = path.split('/')
    if len(parts) >= 5 and parts[1] == 'admin' and parts[2] == 'faculty' and parts[3].isdigit():
        if parts[4] in ('details', 'sessions'):
            return f'/admin/faculty/{parts[3]}'
        if parts[4] == 'availability':
            return '/admin/shifts/availability'
        return '/admin/proxy'
    if len(parts) >= 6 and parts[1:4] == ['admin', 'users', 'roles'] and parts[4].isdigit():
        return f'/admin/roles/{parts[4]}'
    if path.startswith('/admin/users/permissions/'):
        user_id = path.rsplit('/', 1)[-1]
        if user_id.isdigit():
            return f'/admin/users/{user_id}/permissions'
        return '/admin/users'
    if path.startswith('/admin/attendance/student/'):
        return '/admin/attendance'
    if path.startswith('/admin/attendance/faculty/'):
        return '/admin/attendance/faculty'
    if path.startswith('/admin/audit-logs/'):
        return '/admin/audit'
    if path.startswith('/student/attendance/'):
        return '/my-attendance'
    if path.startswith('/teacher/attendance/'):
        return '/my-attendance'
    return '/'


def page_response():
    """Response for a browser page: the React route, or the API/login result."""
    path = (request.path or '/').rstrip('/') or '/'
    if path.startswith('/api') or path.startswith('/admin/api') or path.startswith('/mobile-sync'):
        from api.web.responses import json_error
        return json_error('The page could not be loaded.', 404, 'not_found')
    if request.method != 'GET' and path in ('/login', '/admin/login'):
        return Response('Sign in failed.', status=401, mimetype='text/plain')
    if request.method != 'GET' and path.startswith('/register/'):
        return redirect(request.path)
    target = react_path(path)
    if target == path:
        return Response('Open this application in the web interface.', status=200, mimetype='text/plain')
    return redirect(target)


def render_template(*_template_name, **_template_context):
    """Views call this where they used to render HTML. The React app serves the page."""
    return page_response()
