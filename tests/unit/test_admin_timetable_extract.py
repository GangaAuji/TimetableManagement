"""Admin timetable extract. No live database and no timetable generation."""

from services import admin_timetable


class _Logger:
    def debug(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None

    def exception(self, *args, **kwargs):
        return None

    def warning(self, message, *args, **kwargs):
        if args:
            message % args


class _App:
    logger = _Logger()


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []
        self.closed = False
        self.rowcount = 1

    def execute(self, sql, params=None):
        copied = None if params is None else list(params) if not isinstance(params, tuple) else params
        self.calls.append((' '.join(sql.split()), copied))

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
    def __init__(self, rows):
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


class _Form(dict):
    def getlist(self, key):
        value = self.get(key, [])
        return value if isinstance(value, list) else [value]


def _bind(monkeypatch, connection):
    flashes = []
    monkeypatch.setattr(admin_timetable, 'get_db_connection', lambda: connection)
    monkeypatch.setattr(admin_timetable, 'current_app', _App())
    monkeypatch.setattr(admin_timetable, 'flash', lambda *args: flashes.append(args))
    return flashes


def test_generate_page_closes_the_cursor_only(monkeypatch):
    connection = _Connection([[], [], []])
    _bind(monkeypatch, connection)
    page = admin_timetable.prepare_generate_page('GET', _Form(), 1)
    assert page['generation_result'] is None
    assert 'ORDER BY' not in connection.cursor_obj.calls[0][0]
    assert connection.cursor_obj.closed is True
    assert connection.actions == []


def test_bad_lecture_minutes_leaves_the_cursor_open(monkeypatch):
    connection = _Connection([[], [], [], {'program': 'UG'}])
    _bind(monkeypatch, connection)
    try:
        admin_timetable.prepare_generate_page('POST', _Form({'course': '1', 'lecture_minutes': 'bad'}), 1)
    except ValueError:
        pass
    else:
        raise AssertionError('expected ValueError')
    assert connection.cursor_obj.closed is False
    assert connection.actions == []


def test_delete_session_uses_a_list_parameter(monkeypatch):
    connection = _Connection([[], [], []])
    flashes = _bind(monkeypatch, connection)
    admin_timetable.manage_timetable(
        'POST',
        _Form({'action': 'delete', 'timetable_id': '7'}),
        {'course': '', 'class': '', 'division': ''},
    )
    sql, params = connection.cursor_obj.calls[-1]
    assert sql.startswith('UPDATE timetable SET is_active = 0')
    assert params == [7]
    assert flashes[-1][0] == 'Session removed.'
    assert connection.actions == ['commit']
    assert connection.cursor_obj.closed is True


def test_assign_room_keeps_the_dictionary_unpack(monkeypatch):
    connection = _Connection([
        [],
        [],
        [],
        {
            'day_of_week': 'Monday',
            'start_time': '09:00',
            'end_time': '10:00',
            'theory_practical': 'Practical',
            'student_count': 40,
        },
        {'room_type': 'Classroom', 'capacity': 20},
    ])
    flashes = _bind(monkeypatch, connection)
    admin_timetable.manage_timetable(
        'POST',
        _Form({'action': 'assign_room', 'timetable_id': '4', 'room_id': '2'}),
        {'course': '', 'class': '', 'division': ''},
    )
    assert connection.actions == ['rollback']
    assert flashes[-1] == ('Failed to assign room', 'danger')
    assert connection.cursor_obj.closed is True
