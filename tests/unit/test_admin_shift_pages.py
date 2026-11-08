"""Admin shift, availability, and proxy page contracts. No live database."""

from datetime import date, datetime, timedelta

import pytest
from flask import Flask

from api.web.access import InputError
from api.web import proxy as proxy_api
from api.web import shifts as shift_api
from services import shift_management as shift_service


def test_request_view_includes_the_reviewer_and_formatted_dates():
    created = datetime(2026, 11, 8, 9, 30)
    reviewed = datetime(2026, 11, 8, 10, 15)
    page = shift_api.request_view({
        'requests': [{
            'id': 8,
            'faculty_name': 'Ada',
            'department_name': None,
            'day_of_week': 1,
            'current_shift_name': 'Morning',
            'requested_shift_name': 'Evening',
            'reason': 'Clinic',
            'status': 'approved',
            'admin_response': 'Noted',
            'created_at': created,
            'reviewed_by_name': 'hacker',
            'reviewed_at': reviewed,
        }],
        'pending_count': 2,
    }, True)
    row = page['requests'][0]
    assert row['day'] == 'Monday'
    assert row['department'] == ''
    assert row['submitted'] == created.strftime('%b %d, %Y')
    assert row['reviewed_at'] == reviewed.strftime('%b %d, %Y %H:%M')
    assert row['reviewer'] == 'hacker'
    assert row['response'] == 'Noted'
    assert row['status'] == 'approved'
    assert page['pending_count'] == 2
    assert page['can_respond'] is True


def test_availability_view_is_a_weekly_grid_without_raw_slots():
    slot = {
        'is_available': 1,
        'shift_pattern_id': 3,
        'shift_code': 'M',
        'display_text': 'M',
        'time_range': '09:00 - 17:00',
        'notes': 'Lab',
        'start_time': timedelta(hours=9),
    }
    slot['all_slots'] = [slot, {'display_text': 'E'}]
    page = shift_api.availability_view({
        'faculty_list': [{
            'faculty': {'user_id': 4, 'name': 'Ada', 'department_id': 2, 'department_name': 'Civil'},
            'availability': {1: slot},
        }],
        'shift_patterns': [{
            'id': 3,
            'shift_name': 'Morning',
            'shift_code': 'M',
            'start_time': timedelta(hours=9),
            'end_time': timedelta(hours=17),
        }],
        'departments': [{'id': 2, 'name': 'Civil'}],
    }, True)
    day = page['faculty'][0]['days']['1']
    assert day['shift_pattern_id'] == 3
    assert day['extra'] == 1
    assert 'all_slots' not in day
    assert 'start_time' not in day
    assert page['patterns'][0]['start_time'] == '09:00'
    assert page['can_change'] is True
    assert page['departments'][0]['name'] == 'Civil'


def test_day_change_keeps_the_shift_until_the_checkbox_clears_it():
    kept = shift_api.day_change({'faculty_id': 4, 'day_of_week': 1, 'is_available': True})
    cleared = shift_api.day_change({
        'faculty_id': 4,
        'day_of_week': '2',
        'is_available': False,
        'shift_pattern_id': None,
    })
    assert 'shift_pattern_id' not in kept
    assert kept['is_available'] is True
    assert cleared['shift_pattern_id'] is None
    assert cleared['day_of_week'] == 2


def test_proxy_filters_keep_the_old_allow_list():
    assert proxy_api.proxy_filters({
        'status': 'ASSIGNED',
        'approval_status': 'APPROVED',
        'date_from': '2026-10-01',
        'date_to': '2026-10-31',
        'page': '2',
    }) == ('ASSIGNED', 'APPROVED', '2026-10-01', '2026-10-31', 2)
    assert proxy_api.proxy_filters({'status': 'drop', 'approval_status': 'drop', 'page': '0'}) == ('', '', '', '', 1)
    with pytest.raises(InputError):
        proxy_api.proxy_filters({'date_from': 'yesterday'})


def test_proxy_entry_uses_the_substitution_log_fields():
    entry = proxy_api.proxy_entry({
        'id': 7,
        'absence_date': '2026-10-26',
        'status': 'ASSIGNED',
        'approval_status': 'APPROVED',
        'approval_notes': 'Covered',
        'original_faculty_name': 'Ada',
        'original_employee_id': 'E1',
        'proxy_faculty_name': None,
        'proxy_employee_id': None,
        'start_time': timedelta(hours=9, minutes=5),
        'end_time': timedelta(hours=10),
        'subject_name': 'Maths',
        'class_name': 'FY',
        'division_name': 'A',
        'approved_by_username': 'admin',
    })
    assert entry['date'] == date(2026, 10, 26).strftime('%d %b')
    assert entry['start_time'] == '09:05 AM'
    assert entry['end_time'] == '10:00 AM'
    assert entry['original_employee_id'] == 'E1'
    assert entry['proxy_faculty'] == ''
    assert entry['approved_by'] == 'admin'
    assert entry['approval_notes'] == 'Covered'


def test_proxy_page_uses_the_log_service_and_closes_it(monkeypatch):
    captured = {}

    def fake(page, status, approval, date_from, date_to, close_connection=False):
        captured['args'] = (page, status, approval, date_from, date_to, close_connection)
        return [], {
            'total_records': 0,
            'assigned_count': None,
            'unassigned_count': 0,
            'pending_approval': 0,
            'approved_count': 0,
            'rejected_count': 0,
        }, {'page': page, 'total_pages': 0, 'total': 0, 'has_prev': False, 'has_next': False}

    monkeypatch.setattr(proxy_api, 'load_proxy_log', fake)
    monkeypatch.setattr(proxy_api, 'permission_denied', lambda *args, **kwargs: None)
    app = Flask('proxy-page')
    app.secret_key = 'test'
    with app.test_request_context('/api/proxy?status=ASSIGNED&approval_status=APPROVED&date_from=2026-10-01&date_to=2026-10-31&page=2'):
        response, status = proxy_api._list()
        payload = response.get_json()
    assert status == 200
    assert captured['args'] == (2, 'ASSIGNED', 'APPROVED', '2026-10-01', '2026-10-31', True)
    assert payload['success'] is True
    assert payload['data']['summary']['assigned'] == 0


def test_shift_response_uses_the_shift_service(monkeypatch):
    seen = {}

    def fake(request_id, action, note, user_id):
        seen['call'] = (request_id, action, note, user_id)
        return 'ok'

    monkeypatch.setattr(shift_api, 'respond_change_request', fake)
    monkeypatch.setattr(shift_api, 'permission_denied', lambda *args, **kwargs: None)
    app = Flask('shift-response')
    app.secret_key = 'test'
    with app.test_request_context('/api/shift-requests/4', method='POST', json={'action': 'approve', 'note': 'Noted'}):
        from flask import session
        session['user_id'] = 3
        response, status = shift_api.respond(4)
        payload = response.get_json()
    assert status == 200
    assert seen['call'] == (4, 'approve', 'Noted', 3)
    assert payload['data']['status'] == 'approved'


def test_day_route_preserves_a_shift_until_it_is_cleared(monkeypatch):
    seen = {}

    def fake(data):
        seen['data'] = dict(data)
        return {'success': True}

    monkeypatch.setattr(shift_api, 'set_day_availability', fake)
    monkeypatch.setattr(shift_api, 'permission_denied', lambda *args, **kwargs: None)
    app = Flask('availability-day')
    app.secret_key = 'test'
    with app.test_request_context(
        '/api/availability/day',
        method='POST',
        json={'faculty_id': 4, 'day_of_week': 1, 'is_available': True},
    ):
        shift_api.set_day()
    assert seen['data']['faculty_id'] == 4
    assert 'shift_pattern_id' not in seen['data']
    with app.test_request_context(
        '/api/availability/day',
        method='POST',
        json={'faculty_id': 4, 'day_of_week': 1, 'is_available': False, 'shift_pattern_id': None},
    ):
        shift_api.set_day()
    assert seen['data']['shift_pattern_id'] is None
    assert seen['data']['is_available'] is False


class _Cursor:
    def __init__(self, fail=False):
        self.fail = fail
        self.closed = False

    def execute(self, sql, params=None):
        if self.fail:
            raise RuntimeError('db down')

    def fetchone(self):
        return (9,)

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, fail=False):
        self.cursor_obj = _Cursor(fail)
        self.committed = False
        self.rolled = False
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled = True

    def close(self):
        self.closed = True


def test_bulk_availability_reports_ok_without_leaving_the_connection_open(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(shift_service, 'get_db_connection', lambda: connection)
    monkeypatch.setattr(shift_service, 'flash', lambda *args, **kwargs: None)
    assert shift_service.bulk_set_day_availability([4], None, [1], 1, '') == 'ok'
    assert connection.committed is True
    assert connection.closed is True
    assert connection.cursor_obj.closed is True


def test_bulk_availability_reports_error_and_rolls_back(monkeypatch):
    connection = _Connection(fail=True)
    monkeypatch.setattr(shift_service, 'get_db_connection', lambda: connection)
    monkeypatch.setattr(shift_service, 'flash', lambda *args, **kwargs: None)
    assert shift_service.bulk_set_day_availability([4], None, [1], 1, '') == 'error'
    assert connection.rolled is True
    assert connection.committed is False
    assert connection.closed is True


def test_shift_form_keeps_hours_and_rejects_a_bad_code():
    values = shift_api.shift_form({
        'name': 'Morning',
        'code': 'am',
        'start_time': '09:00',
        'end_time': '13:00',
        'shift_order': 2,
        'description': 'Early',
        'is_active': True,
    })
    assert values == ('Morning', 'AM', '09:00', '13:00', 2, 'Early', 1)
    with pytest.raises(InputError):
        shift_api.shift_form({
            'name': 'Morning',
            'code': 'A M',
            'start_time': '09:00',
            'end_time': '13:00',
            'is_active': True,
        })


def test_pattern_row_includes_the_faculty_count():
    row = shift_api.pattern_row({
        'id': 3,
        'shift_name': 'Morning',
        'shift_code': 'AM',
        'start_time': timedelta(hours=9),
        'end_time': timedelta(hours=13),
        'shift_order': 1,
        'description': 'Early',
        'is_active': 1,
        'faculty_count': 4,
    })
    assert row['faculty_count'] == 4
    assert row['start_time'] == '09:00'
    assert row['is_active'] is True


def test_delete_refuses_a_shift_that_faculty_still_use(monkeypatch):
    connection = _DictionaryConnection()
    monkeypatch.setattr(shift_api, 'permission_denied', lambda *args, **kwargs: None)
    monkeypatch.setattr(shift_api, 'get_db_connection', lambda: connection)
    monkeypatch.setattr(shift_api, 'count_shift_usage', lambda cursor, shift_id: {'count': 2})
    monkeypatch.setattr(shift_api, 'delete_shift_pattern', lambda cursor, shift_id: (_ for _ in ()).throw(AssertionError('deleted')))
    app = Flask('shift-delete')
    app.secret_key = 'test'
    with app.test_request_context('/api/shifts/3/delete', method='POST', json={}):
        from flask import session
        session['user_id'] = 1
        response, status = shift_api.remove_pattern(3)
    assert status == 409
    assert response.get_json()['error']['code'] == 'shift_in_use'
    assert connection.committed is False
    assert connection.closed is True


class _DictionaryConnection:
    def __init__(self):
        self.cursor_obj = _Cursor()
        self.committed = False
        self.closed = False

    def cursor(self, dictionary=False):
        self.dictionary = dictionary
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        self.closed = True
