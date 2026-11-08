"""Invitation registration. No live database and no face model."""

import base64
from datetime import datetime

from services import registration


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []
        self.lastrowid = None

    def execute(self, sql, params=None):
        text = ' '.join(sql.split())
        self.calls.append((text, params))
        if text.startswith('INSERT INTO users '):
            self.lastrowid = 12

    def fetchone(self):
        if not self.rows:
            return None
        return self.rows.pop(0)


class _Connection:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _Logger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(message)

    def exception(self, message, *args):
        self.errors.append(message)


class _App:
    def __init__(self, root):
        self.root_path = root
        self.logger = _Logger()
        self.config = {
            'MOBILE_FACE_EMBEDDING_ENABLED': False,
            'MOBILE_FACE_EMBEDDING_REQUIRE_SUCCESS': False,
            'FACE_TEMPLATE_MIN_QUALITY': 0.55,
        }


def _bind(monkeypatch, rows, root):
    connection = _Connection()
    cursor = _Cursor(rows)
    flashes = []
    monkeypatch.setattr(registration, 'get_db', lambda: (connection, cursor))
    monkeypatch.setattr(registration, 'flash', lambda message, category: flashes.append((message, category)))
    monkeypatch.setattr(registration, 'current_app', _App(root))
    monkeypatch.setattr(registration, 'generate_password_hash', lambda _password: 'hashed')

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 26, 12, 34, 56)

    monkeypatch.setattr(registration, 'datetime', _Clock)
    return connection, cursor, flashes


def _invitation(role='Student', status='pending'):
    return {
        'id': 5,
        'email': 'ada@school',
        'role': role,
        'name': 'Ada',
        'course_id': 2,
        'class_id': 3,
        'division_id': 4,
        'department_id': 8,
        'expires_at': datetime(2099, 1, 1),
        'status': status,
    }


def test_invalid_used_and_expired_links(monkeypatch):
    connection, cursor, flashes = _bind(monkeypatch, [None], '.')
    assert registration.load_invitation('missing') == (None, 'login')
    assert flashes == [('Invalid registration link. Please contact your administrator.', 'danger')]
    assert connection.commits == 0

    used = _invitation(status='used')
    used['expires_at'] = datetime(2020, 1, 1)
    connection, cursor, flashes = _bind(monkeypatch, [used], '.')
    assert registration.load_invitation('used-token') == (None, 'login')
    assert flashes == [('This invitation has already been used.', 'warning')]
    assert cursor.calls[0][0].startswith('SELECT id, email, role, name')
    assert len(cursor.calls) == 1
    assert connection.commits == 0

    connection, cursor, flashes = _bind(monkeypatch, [_invitation()], '.')
    monkeypatch.setattr(registration, 'datetime', datetime)
    expired = _invitation()
    expired['expires_at'] = datetime(2020, 1, 1)
    cursor.rows = [expired]
    assert registration.load_invitation('old-token') == (None, 'login')
    assert cursor.calls[1][0] == "UPDATE registration_invitations SET status = 'expired' WHERE id = %s"
    assert cursor.calls[1][1] == (5,)
    assert connection.commits == 1
    assert flashes == [('This invitation has expired. Please request a new one.', 'danger')]


def test_taken_username_and_student_email_stop_before_insert(monkeypatch):
    connection, cursor, flashes = _bind(monkeypatch, [{'id': 1}], '.')
    assert registration.register_account(_invitation(), 'ada', 'secret', {}) == 'form'
    assert flashes == [('Username already exists. Please choose a different one.', 'danger')]
    assert len(cursor.calls) == 1
    assert connection.rollbacks == 0

    connection, cursor, flashes = _bind(monkeypatch, [None, {'id': 9}], '.')
    assert registration.register_account(_invitation(), 'ada', 'secret', {}) == 'form'
    assert 'FROM students WHERE email' in cursor.calls[1][0]
    assert flashes == [('This email is already registered. Please contact your administrator.', 'danger')]
    assert connection.rollbacks == 0

    connection, cursor, flashes = _bind(monkeypatch, [None, {'id': 9}], '.')
    registration.register_account(_invitation(role='Teacher'), 'ada', 'secret', {})
    assert 'FROM faculty WHERE email' in cursor.calls[1][0]


def test_supplied_face_template_still_fails_before_quality_is_read(monkeypatch):
    connection, cursor, flashes = _bind(monkeypatch, [None, None], '.')
    template = '[' + ','.join(['1'] + ['0'] * 191) + ']'
    outcome = registration.register_account(
        _invitation(), 'ada', 'secret', {'face_template_json': template},
    )
    assert outcome == 'form'
    assert connection.rollbacks == 1
    assert connection.commits == 0
    assert flashes == [('An error occurred during registration. Please try again.', 'danger')]
    assert 'quality_score' in registration.current_app.logger.errors[0]
    assert not any(call[0].startswith('INSERT') for call in cursor.calls)


def test_missing_capture_does_not_roll_back(monkeypatch):
    connection, _cursor, flashes = _bind(monkeypatch, [None, None], '.')
    registration.current_app.config['MOBILE_FACE_EMBEDDING_REQUIRE_SUCCESS'] = True
    assert registration.register_account(_invitation(), 'ada', 'secret', {}) == 'form'
    assert flashes == [('Face template is required for recognition. Please retry capture.', 'danger')]
    assert connection.rollbacks == 0

    connection, _cursor, flashes = _bind(monkeypatch, [None, None], '.')
    assert registration.register_account(_invitation(), 'ada', 'secret', {}) == 'form'
    assert flashes == [('Face capture is required. Please open camera and capture your face image.', 'danger')]
    assert connection.rollbacks == 0


def test_student_registration_writes_the_capture_and_uses_the_user_id(monkeypatch, tmp_path):
    connection, cursor, flashes = _bind(monkeypatch, [None, None, {'ok': 1}], str(tmp_path))
    captured = base64.b64encode(b'abc').decode('ascii')
    outcome = registration.register_account(
        _invitation(),
        'ada',
        'secret',
        {'face_capture_data': f'data:image/jpeg;base64,{captured}'},
    )
    assert outcome == 'login'
    photo = 'uploads/profiles/12_20261026123456_captured.jpg'
    saved = tmp_path / 'static' / 'uploads' / 'profiles' / '12_20261026123456_captured.jpg'
    assert saved.read_bytes() == b'abc'
    statements = [call[0].split(' ', 1)[0] for call in cursor.calls]
    assert statements == ['SELECT', 'SELECT', 'INSERT', 'UPDATE', 'INSERT', 'SELECT', 'INSERT', 'UPDATE']
    assert cursor.calls[2][1] == ('ada', 'hashed', 'Student')
    assert cursor.calls[4][1][0] == 12
    assert cursor.calls[4][1][2] == 'STU202610260012'
    assert 'INSERT INTO faculty' not in cursor.calls[4][0]
    assert cursor.calls[6][1][1] is None
    assert cursor.calls[6][1][2] == photo
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert flashes == [('Registration successful! You can now log in as Student.', 'success')]


def test_teacher_registration_stores_the_faculty_row_id(monkeypatch, tmp_path):
    connection, cursor, flashes = _bind(monkeypatch, [None, None, None], str(tmp_path))
    captured = base64.b64encode(b'abc').decode('ascii')
    registration.register_account(
        _invitation(role='Faculty'),
        'ada',
        'secret',
        {'face_capture_data': f'data:image/jpeg;base64,{captured}'},
    )
    assert 'INSERT INTO faculty' in cursor.calls[4][0]
    assert cursor.calls[4][1] == (12, 12, 'Ada', 'ada@school', 8, 'EMP2026000012')
    assert not any('mobile_face_templates' in call[0] and call[0].startswith('INSERT') for call in cursor.calls)
    assert connection.commits == 1
    assert flashes[0][0] == 'Registration successful! You can now log in as Faculty.'
