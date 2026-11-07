"""Institution holiday saves. No live database."""

from datetime import date

from services import institution_holidays as holiday_service


class _Cursor:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.calls = []
        self.close_count = 0

    def execute(self, sql, params=None):
        self.calls.append((' '.join(sql.split()), params))

    def fetchall(self):
        return list(self.rows)

    def close(self):
        self.close_count += 1


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


def _bind(monkeypatch, connection, taken=False):
    flashes = []
    monkeypatch.setattr(holiday_service, 'get_db_connection', lambda: connection)
    monkeypatch.setattr(holiday_service, 'flash', lambda message, category: flashes.append((message, category)))
    monkeypatch.setattr(holiday_service, 'recurring_holiday_taken', lambda *args: taken)

    class _Logger:
        def error(self, message):
            flashes.append(('log', message))

    class _App:
        logger = _Logger()

    monkeypatch.setattr(holiday_service, 'current_app', _App())
    return flashes


def test_holiday_list_formats_dates_and_leaves_the_connection_open(monkeypatch):
    connection = _Connection([{
        'id': 1,
        'holiday_date': date(2026, 10, 2),
        'day_of_week': None,
        'name': 'Gandhi Jayanti',
        'applies_to_program': 'Both',
        'is_recurring': 0,
    }])
    _bind(monkeypatch, connection)
    items = holiday_service.list_holidays()
    assert items == [{
        'id': 1,
        'holiday_date': '2026-10-02',
        'day_of_week': '',
        'name': 'Gandhi Jayanti',
        'applies_to_program': 'Both',
        'is_recurring': False,
    }]
    assert 'ORDER BY is_recurring DESC' in connection.cursor_obj.calls[0][0]
    assert connection.cursor_obj.close_count == 1
    assert connection.actions == []


def test_duplicate_weekly_holiday_closes_the_cursor_before_the_final_close(monkeypatch):
    connection = _Connection()
    flashes = _bind(monkeypatch, connection, taken=True)
    holiday_service.add_holiday('Sunday', 'UG', 'weekly', '', 'Sunday')
    assert flashes == [('A recurring holiday for this day and program already exists.', 'warning')]
    assert connection.cursor_obj.calls == []
    assert connection.cursor_obj.close_count == 2
    assert connection.actions == ['close']


def test_missing_date_does_not_open_a_connection(monkeypatch):
    opened = []
    flashes = []
    monkeypatch.setattr(holiday_service, 'get_db_connection', lambda: opened.append(True))
    monkeypatch.setattr(holiday_service, 'flash', lambda message, category: flashes.append((message, category)))
    holiday_service.add_holiday('Founders day', 'Both', 'date', '  ', None)
    assert opened == []
    assert flashes == [('Please select a holiday date.', 'danger')]


def test_dated_holiday_insert_uses_a_tuple(monkeypatch):
    connection = _Connection()
    flashes = _bind(monkeypatch, connection)
    holiday_service.add_holiday(' Founders day ', 'PG', 'date', '2026-11-01', '')
    assert connection.cursor_obj.calls[0][1] == ('2026-11-01', 'Founders day', 'PG')
    assert 'VALUES (%s, NULL, %s, %s, 0)' in connection.cursor_obj.calls[0][0]
    assert flashes == [('Holiday added.', 'success')]
    assert connection.actions == ['commit', 'close']
