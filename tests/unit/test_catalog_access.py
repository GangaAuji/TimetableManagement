"""Department, course, and room checks keep their current JSON and log text."""

import pytest

from app import create_app
from api.web.courses import _CourseInputError
from api.web.courses import _optional_text as course_optional_text
from api.web.courses import _required_text as course_required_text
from api.web.departments import _DepartmentInputError
from api.web.departments import _optional_text as department_optional_text
from api.web.departments import _required_text as department_required_text


def _deny(*_args, **_kwargs):
    raise RuntimeError('db down')


@pytest.fixture(scope='module')
def app():
    return create_app()


def test_text_helpers_raise_the_local_error():
    assert department_required_text('  Math ', 100, 'department_name_invalid') == 'Math'
    assert department_optional_text(None, 10, 'description_invalid') == ''
    with pytest.raises(_DepartmentInputError) as department_error:
        department_required_text('', 100, 'department_name_invalid')
    assert department_error.value.code == 'department_name_invalid'

    assert course_required_text('  BSc ', 100, 'course_name_invalid') == 'BSc'
    assert course_optional_text(None, 10, 'description_invalid') == ''
    with pytest.raises(_CourseInputError) as course_error:
        course_optional_text('bad\x00', 10, 'description_invalid')
    assert course_error.value.code == 'description_invalid'


@pytest.mark.live_db
def test_signed_out_lists_stay_unauthorized(app):
    client = app.test_client()
    expected = {
        'success': False,
        'error': {'code': 'unauthorized', 'message': 'Authentication required.'},
    }
    for path in ('/api/departments', '/api/courses', '/api/rooms'):
        response = client.get(path)
        assert response.status_code == 401
        assert response.get_json() == expected


@pytest.mark.live_db
def test_permission_failures_keep_status_and_log_text(app, monkeypatch, caplog):
    monkeypatch.setattr('api.web.access.check_user_permission', _deny)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'Admin'

    cases = (
        ('/api/departments', 'departments_unavailable', 'The department list could not be loaded.', 'Department permission check failed'),
        ('/api/courses', 'courses_unavailable', 'The course list could not be loaded.', 'Course permission check failed'),
        ('/api/rooms', 'rooms_unavailable', 'The room list could not be loaded.', 'Room permission check failed: db down'),
    )
    for path, code, message, log_text in cases:
        caplog.clear()
        with caplog.at_level('ERROR'):
            response = client.get(path)
        assert response.status_code == 500
        assert response.get_json()['error'] == {'code': code, 'message': message}
        assert log_text in caplog.text
