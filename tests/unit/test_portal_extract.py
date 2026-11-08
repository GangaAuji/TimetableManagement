"""Student, proxy, and device extracts. No live database."""

from services import mobile_devices
from services import student_portal
from services import teacher_portal


class _Cursor:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.calls = []
        self.closed = False
        self.lastrowid = 1
        self.rowcount = 1

    def execute(self, sql, params=None):
        self.calls.append((' '.join(sql.split()), params))

    def fetchone(self):
        if not self.rows:
            return None
        return self.rows.pop(0)

    def fetchall(self):
        if not self.rows:
            return []
        value = self.rows.pop(0)
        return value if isinstance(value, list) else [value]

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, rows=None):
        self.cursor_obj = _Cursor(rows)
        self.actions = []

    def cursor(self, dictionary=False):
        return self.cursor_obj

    def commit(self):
        self.actions.append('commit')

    def rollback(self):
        self.actions.append('rollback')

    def close(self):
        self.actions.append('close')


def _bind(monkeypatch, module, connection):
    flashes = []
    monkeypatch.setattr(module, 'get_db_connection', lambda: connection)
    if hasattr(module, 'flash'):
        monkeypatch.setattr(module, 'flash', lambda *args: flashes.append(args))
    return flashes


def test_missing_student_closes_the_connection(monkeypatch):
    connection = _Connection([None])
    _bind(monkeypatch, student_portal, connection)
    assert student_portal.load_student_dashboard(4) == {'error': 'Student profile not found.'}
    assert connection.cursor_obj.closed is True
    assert connection.actions == ['close']


def test_proxy_request_is_stored_as_pending(monkeypatch):
    connection = _Connection([
        {'user_id': 9},
        {'user_id': 12},
        {'day_of_week': 'Monday', 'subject_id': 3, 'start_time': None, 'end_time': None},
    ])
    flashes = _bind(monkeypatch, teacher_portal, connection)
    assert teacher_portal.submit_proxy_request(4, 8, 5, '2026-10-26') == 'ok'
    sql, params = connection.cursor_obj.calls[-1]
    assert sql.endswith("VALUES (%s, %s, %s, %s, %s)")
    assert params[-1] == 'PENDING'
    assert params[0] == 9
    assert flashes[-1][0] == 'Proxy request submitted for approval.'
    assert connection.actions == ['commit', 'close']


from datetime import date as real_date


def _attendance_today(monkeypatch, module):
    class _Today(real_date):
        @classmethod
        def today(cls):
            return real_date(2026, 10, 26)

    monkeypatch.setattr(module, 'date', _Today)


def test_attendance_save_marks_with_the_faculty_table_id(monkeypatch):
    from services import teacher_attendance
    lecture = {'course_id': 1, 'class_id': 2, 'division_id': 3, 'day_of_week': 'Monday'}
    connection = _Connection([{'id': 15}, lecture, [{'id': 4}]])
    flashes = _bind(monkeypatch, teacher_attendance, connection)
    _attendance_today(monkeypatch, teacher_attendance)
    form = {'attendance_date': '2026-10-26', 'status_4': 'Present', 'remarks_4': 'ok'}
    assert teacher_attendance.save_teacher_attendance(9, 8, form) == 1
    sql, params = connection.cursor_obj.calls[-1]
    assert 'marked_by' in sql
    assert 'ON DUPLICATE KEY UPDATE' in sql
    assert params[5] == 15
    assert params[0] == 4
    # The lecture is recorded as held in the same transaction, before the marks.
    session_sql, session_params = connection.cursor_obj.calls[-2]
    assert session_sql.startswith('INSERT INTO lecture_sessions') and "'held'" in session_sql
    assert session_params[:2] == (8, real_date(2026, 10, 26)) and session_params[3] == 15
    assert params[2] == connection.cursor_obj.lastrowid
    assert connection.actions == ['commit', 'close']
    assert flashes == []


def test_attendance_error_rolls_back_and_leaves_the_connection_open(monkeypatch):
    from services import teacher_attendance
    lecture = {'course_id': 1, 'class_id': 2, 'division_id': 3, 'day_of_week': 'Monday'}
    connection = _Connection([{'id': 15}, lecture, [{'id': 4}]])

    def _execute(sql, params=None):
        text = ' '.join(sql.split())
        connection.cursor_obj.calls.append((text, params))
        if 'INSERT INTO attendance' in text:
            raise RuntimeError('attendance locked')

    connection.cursor_obj.execute = _execute
    _bind(monkeypatch, teacher_attendance, connection)
    _attendance_today(monkeypatch, teacher_attendance)
    try:
        teacher_attendance.save_teacher_attendance(9, 8, {'attendance_date': '2026-10-26', 'status_4': 'Present'})
    except RuntimeError as exc:
        assert str(exc) == 'attendance locked'
    else:
        raise AssertionError('expected the attendance write to fail')
    assert connection.actions == ['rollback']


def test_device_toggle_flips_an_active_device(monkeypatch):
    connection = _Connection([{'is_active': 1}])
    _bind(monkeypatch, mobile_devices, connection)
    assert mobile_devices.toggle_mobile_device(3) == 'ok'
    assert connection.cursor_obj.calls[1][1] == (0, 3)
    assert connection.actions == ['commit', 'close']


def test_invitation_list_leaves_the_connection_open(monkeypatch):
    from services import invitations
    connection = _Connection([
        {'total': 0},
        [],
        [],
        [],
        [],
        [],
        {'pending': None, 'used': 2, 'expired': None, 'total': 2},
    ])
    _bind(monkeypatch, invitations, connection)
    page = invitations.list_invitations(1, '', '')
    assert page['stats'] == {'pending': 0, 'used': 2, 'expired': 0, 'total': 2}
    assert connection.cursor_obj.closed is True
    assert connection.actions == []
    count_sql = connection.cursor_obj.calls[0][0]
    assert count_sql.startswith('SELECT COUNT(ri.id) AS total')
    assert connection.cursor_obj.calls[0][1] == ()
