"""Maintenance mode leaves the admin panel open and closes everything else."""

from flask import Flask

from ui.maintenance import maintenance_allows, maintenance_response


def test_maintenance_is_off_is_not_this_modules_job():
    assert maintenance_allows('/', 'GET', None, False) is False


def test_visitors_can_open_admin_sign_in_and_the_public_reads():
    assert maintenance_allows('/admin/login', 'POST', None, False) is True
    assert maintenance_allows('/api/session', 'GET', None, False) is True
    assert maintenance_allows('/api/branding', 'GET', None, False) is True
    assert maintenance_allows('/api/csrf-token', 'GET', None, False) is True
    assert maintenance_allows('/health', 'GET', None, False) is True
    assert maintenance_allows('/static/app.js', 'GET', None, False) is True


def test_visitors_cannot_use_the_student_site_or_the_api():
    assert maintenance_allows('/', 'GET', None, False) is False
    assert maintenance_allows('/login', 'POST', None, False) is False
    assert maintenance_allows('/api/timetable', 'GET', None, False) is False
    assert maintenance_allows('/mobile-sync/v1/health', 'GET', None, False) is False


def test_admin_staff_can_use_the_admin_panel_only():
    for role in ('Admin', 'Super Admin', 'HOD'):
        assert maintenance_allows('/admin', 'GET', role, True) is True
        assert maintenance_allows('/admin/students', 'GET', role, True) is True
        assert maintenance_allows('/api/timetable', 'GET', role, True) is True
        assert maintenance_allows('/my-timetable', 'GET', role, True) is False
        assert maintenance_allows('/mobile-sync/v1/health', 'GET', role, True) is False


def test_students_and_teachers_stay_on_the_maintenance_page():
    for role in ('Student', 'Teacher'):
        assert maintenance_allows('/api/timetable', 'GET', role, True) is False
        assert maintenance_allows('/admin', 'GET', role, True) is False
        assert maintenance_allows('/api/session/logout', 'POST', role, True) is True


def test_api_maintenance_response_has_no_application_detail():
    app = Flask(__name__)
    with app.app_context():
        response, status = maintenance_response('/api/timetable')
        assert status == 503
        assert response.get_json() == {
            'success': False,
            'error': {'code': 'maintenance', 'message': 'The system is temporarily unavailable.'},
        }


def test_page_maintenance_response_is_a_page():
    body, status, headers = maintenance_response('/my-timetable')
    assert status == 503
    assert 'be back shortly' in body
    assert 'Admin sign in' not in body
    assert '/admin/login' not in body
    assert headers['Content-Type'].startswith('text/html')


def test_page_uses_the_configured_notice():
    from ui.errors import maintenance_document

    body, status, _headers = maintenance_document({
        'title': 'Library closed <today>',
        'message': 'Back on Monday & Tuesday',
        'site_title': 'North Campus',
        'support_email': 'desk@college.edu',
        'support_phone': '+1 234',
        'logo': '',
    })
    assert status == 503
    assert 'Library closed &lt;today&gt;' in body
    assert 'Back on Monday &amp; Tuesday' in body
    assert 'North Campus' in body
    assert 'mailto:desk@college.edu' in body
    assert '/admin/login' not in body
