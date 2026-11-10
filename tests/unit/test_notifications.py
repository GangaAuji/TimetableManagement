"""Notifications: secrets at rest, the sender, retry bookkeeping with a fake connection, and revision 0011. No live database."""

import importlib.util
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from flask import Flask

from core.schema.baseline import MIGRATIONS_DIR
from core.schema.status import head_revision
from services import notifications, secrets_at_rest

KEY = Fernet.generate_key().decode('ascii')


def _app(**config):
    app = Flask('notifications-unit')
    app.config.update(config)
    return app


# secrets_at_rest

def test_secrets_use_the_settings_key_then_the_face_key_then_secret_key():
    with _app(SETTINGS_ENCRYPTION_KEY=KEY, FACE_TEMPLATE_KEY='x', SECRET_KEY='s').app_context():
        assert secrets_at_rest.key_source() == 'SETTINGS_ENCRYPTION_KEY'
        token = secrets_at_rest.encrypt_text('hunter2')
        assert token.startswith('enc:v1:') and 'hunter2' not in token
        assert secrets_at_rest.decrypt_text(token) == 'hunter2'
    with _app(FACE_TEMPLATE_KEY=KEY).app_context():
        assert secrets_at_rest.key_source() == 'FACE_TEMPLATE_KEY'
        assert secrets_at_rest.decrypt_text(token) == 'hunter2'   # same key, other setting
    with _app(SECRET_KEY='only-the-flask-secret').app_context():
        assert secrets_at_rest.key_source() == 'SECRET_KEY'
        derived = secrets_at_rest.encrypt_text('pw')
        assert secrets_at_rest.decrypt_text(derived) == 'pw'
        assert secrets_at_rest.decrypt_text(token) is None         # a different key: unreadable, not an error
    with _app().app_context():
        assert secrets_at_rest.key_source() is None
        with pytest.raises(RuntimeError):
            secrets_at_rest.encrypt_text('pw')
        assert secrets_at_rest.decrypt_text(token) is None
    assert secrets_at_rest.decrypt_text('') is None and secrets_at_rest.decrypt_text('plain') is None


def test_an_invalid_key_is_reported_not_swallowed_on_encrypt():
    with _app(SETTINGS_ENCRYPTION_KEY='not-a-fernet-key').app_context():
        with pytest.raises(RuntimeError):
            secrets_at_rest.encrypt_text('pw')
        assert secrets_at_rest.decrypt_text('enc:v1:abc') is None


# smtp_account and send

def test_smtp_account_prefers_the_tenant_settings_then_the_server_env():
    tenant = {'smtp_host': 'mail.college.test', 'smtp_port': 2525, 'smtp_user': 'tt', 'smtp_from': 'tt@college.test', 'smtp_starttls': False}
    with _app(SMTP_HOST='smtp.server.test', SMTP_PORT=587, SMTP_FROM='ops@server.test').app_context():
        account = notifications.smtp_account(settings=tenant)
        assert (account['source'], account['host'], account['port'], account['starttls']) == ('tenant', 'mail.college.test', 2525, False)
        account = notifications.smtp_account(settings={'smtp_host': None})
        assert (account['source'], account['host'], account['from']) == ('server', 'smtp.server.test', 'ops@server.test')
    with _app(SMTP_HOST=None).app_context():
        assert notifications.smtp_account(settings={}) is None


def test_send_without_an_account_raises_notifications_off():
    with pytest.raises(notifications.NotificationsOff):
        notifications.send(None, to='a@b.test', subject='s', body='b')


def test_send_builds_the_message_and_talks_smtp(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(('connect', host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            calls.append(('quit',))

        def starttls(self):
            calls.append(('starttls',))

        def login(self, user, password):
            calls.append(('login', user, password))

        def send_message(self, message):
            calls.append(('send', message['From'], message['To'], message['Subject'], message['Reply-To']))

    monkeypatch.setattr(notifications.smtplib, 'SMTP', FakeSMTP)
    account = {'host': 'h', 'port': 25, 'user': 'u', 'password': 'p', 'from': 'f@x.test', 'starttls': True, 'reply_to': 'r@x.test'}
    notifications.send(account, to='t@x.test', subject='Hello', body='Body')
    assert calls == [('connect', 'h', 25), ('starttls',), ('login', 'u', 'p'), ('send', 'f@x.test', 't@x.test', 'Hello', 'r@x.test'), ('quit',)]


# process_one with a fake connection

class _Cursor:
    def __init__(self, row, log):
        self.row = row
        self.log = log

    def execute(self, statement, params=()):
        self.log.append((' '.join(statement.split()), params))

    def fetchone(self):
        if self.log and self.log[-1][0].startswith('SELECT * FROM'):
            return dict(self.row)
        if self.log and 'information_schema' in self.log[-1][0]:
            return None   # no notification_settings table: server SMTP_* only
        return None

    def fetchall(self):
        return []

    def close(self):
        pass


class _Connection:
    def __init__(self, row):
        self.log = []
        self.row = row
        self.commits = 0

    def cursor(self, dictionary=False):
        return _Cursor(self.row, self.log)

    def commit(self):
        self.commits += 1


def _row(attempts=0):
    return {'id': 7, 'recipient_email': 'to@x.test', 'subject': 'S', 'body': 'B', 'attempts': attempts}


def _updates(connection):
    return [(statement, params) for statement, params in connection.log if statement.startswith('UPDATE')]


def test_process_one_marks_sent_on_success():
    sent = []
    connection = _Connection(_row())
    with _app(SMTP_HOST='smtp.test').app_context():
        outcome = notifications.process_one(connection, 7, sender=lambda account, **kw: sent.append((account['host'], kw['to'])))
    assert outcome == 'sent' and sent == [('smtp.test', 'to@x.test')]
    statement, params = _updates(connection)[0]
    assert "status = 'sent'" in statement and params == (7,) and connection.commits == 1


def test_process_one_requeues_with_backoff_then_fails_after_max_attempts():
    def boom(account, **kw):
        raise ConnectionRefusedError('refused')

    connection = _Connection(_row(attempts=0))
    with _app(SMTP_HOST='smtp.test', NOTIFICATION_MAX_ATTEMPTS=2, NOTIFICATION_RETRY_SECONDS=60).app_context():
        assert notifications.process_one(connection, 7, sender=boom) == 'retry'
    statement, params = _updates(connection)[0]
    assert params[0] == 'queued' and params[1] == 1 and params[2].startswith('ConnectionRefusedError') and params[3] == 60

    connection = _Connection(_row(attempts=1))
    with _app(SMTP_HOST='smtp.test', NOTIFICATION_MAX_ATTEMPTS=2, NOTIFICATION_RETRY_SECONDS=60).app_context():
        assert notifications.process_one(connection, 7, sender=boom) == 'failed'
    statement, params = _updates(connection)[0]
    assert params[0] == 'failed' and params[1] == 2 and params[3] == 120   # backoff grows with the attempt


def test_process_one_defers_without_burning_an_attempt_when_nothing_can_send():
    connection = _Connection(_row())
    with _app(SMTP_HOST=None).app_context():
        assert notifications.process_one(connection, 7, sender=notifications.send) == 'deferred'
    statement, params = _updates(connection)[0]
    assert "status = 'queued'" in statement and 'attempts' not in statement and 'No SMTP account' in params[0]


def test_enqueue_rejects_unknown_kinds():
    with pytest.raises(ValueError):
        notifications.enqueue(None, kind='carrier-pigeon', subject='s', body='b', recipient_email='a@b.test')


# Revision 0011

def _load_0011():
    path = Path(MIGRATIONS_DIR) / 'versions' / '0011_notifications.py'
    spec = importlib.util.spec_from_file_location('revision_0011', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Result:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row


class _Bind:
    def __init__(self, present):
        self.present = set(present)

    def execute(self, statement, params):
        return _Result((1,) if params['table'] in self.present else None)


def test_0011_follows_0010_and_creates_only_missing_tables(monkeypatch):
    assert head_revision() >= '0011_notifications'
    module = _load_0011()
    assert module.down_revision == '0010_face_safeguards'
    executed = []
    monkeypatch.setattr(module.op, 'execute', lambda statement: executed.append(statement))

    monkeypatch.setattr(module.op, 'get_bind', lambda: _Bind({'notifications'}))
    module.upgrade()
    assert len(executed) == 1 and 'CREATE TABLE notification_settings' in executed[0]
    assert 'smtp_password_enc' in executed[0] and 'smtp_password ' not in executed[0]

    executed.clear()
    monkeypatch.setattr(module.op, 'get_bind', lambda: _Bind({'notifications', 'notification_settings'}))
    module.upgrade()
    assert executed == []
    module.downgrade()
    assert executed == ['DROP TABLE `notification_settings`', 'DROP TABLE `notifications`']
    for column in ('dedupe_key', 'locked_by', 'heartbeat_at', 'progress', 'available_at'):
        assert column in module.NOTIFICATIONS
