"""Integrations without a database: API keys, the /api/v1 registry and OpenAPI document, webhook signing and
delivery bookkeeping with a fake connection, OIDC token verification, and revision 0013."""

import base64
import importlib.util
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from flask import Flask

from core.schema.baseline import MIGRATIONS_DIR
from core.schema.status import head_revision
from services import api_keys, sso, webhooks
from services.secrets_at_rest import encrypt_text

KEY = Fernet.generate_key().decode('ascii')


def _app(**config):
    app = Flask('integrations-unit')
    app.config.update({'SETTINGS_ENCRYPTION_KEY': KEY, 'TESTING': True, **config})
    return app


# API keys ---------------------------------------------------------------------

class _KeyCursor:
    """Remembers inserted keys by prefix so authenticate() can find them."""

    def __init__(self):
        self.rows = {}
        self.touched = []
        self.last = None

    def execute(self, statement, params=()):
        text = ' '.join(statement.split())
        if text.startswith('INSERT INTO api_keys'):
            name, prefix, key_hash, scopes, created_by, expires_at = params
            self.rows[prefix] = {
                'id': len(self.rows) + 1, 'name': name, 'key_prefix': prefix, 'key_hash': key_hash, 'scopes': scopes,
                'created_by': created_by, 'created_at': None, 'expires_at': expires_at, 'last_used_at': None, 'revoked_at': None,
            }
            self.lastrowid = self.rows[prefix]['id']
            self.last = None
        elif 'WHERE key_prefix = %s' in text:
            self.last = self.rows.get(params[0])
        elif text.startswith('UPDATE api_keys SET last_used_at'):
            self.touched.append(params[0])
        elif text.startswith('UPDATE api_keys SET revoked_at'):
            for row in self.rows.values():
                if row['id'] == params[0]:
                    row['revoked_at'] = datetime.utcnow()
            self.rowcount = 1
        elif 'FROM api_keys WHERE id = %s' in text:
            self.last = next((row for row in self.rows.values() if row['id'] == params[0]), None)
        else:
            self.last = None

    def fetchone(self):
        return dict(self.last) if self.last else None


def test_api_key_round_trip_scopes_and_prefix():
    cursor = _KeyCursor()
    key_id, plaintext = api_keys.create_key(cursor, name='Portal', scopes=['timetable:read', 'bogus', 'catalog:read'], created_by=1)
    assert key_id == 1 and plaintext.startswith('ttk_') and len(plaintext.split('_')) == 3
    prefix, _ = api_keys.split_key(plaintext)
    assert cursor.rows[prefix]['scopes'] == 'catalog:read timetable:read'
    assert plaintext not in json.dumps(cursor.rows, default=str)   # only the hash is stored

    row = api_keys.authenticate(cursor, plaintext)
    assert row and row['id'] == 1 and row['scopes'] == ('catalog:read', 'timetable:read') and cursor.touched == [1]
    assert api_keys.has_scope(row, 'timetable:read') and not api_keys.has_scope(row, 'people:read')


def test_api_key_wrong_secret_revoked_or_expired_is_refused():
    cursor = _KeyCursor()
    _, plaintext = api_keys.create_key(cursor, name='k', scopes=['catalog:read'], created_by=None)
    prefix, _ = api_keys.split_key(plaintext)
    tampered = plaintext[:-1] + ('a' if plaintext[-1] != 'a' else 'b')
    assert api_keys.authenticate(cursor, tampered) is None
    assert api_keys.authenticate(cursor, 'ttk_short') is None and api_keys.split_key(None) is None

    cursor.rows[prefix]['expires_at'] = datetime.utcnow() - timedelta(seconds=1)
    assert api_keys.authenticate(cursor, plaintext) is None
    cursor.rows[prefix]['expires_at'] = None
    assert api_keys.authenticate(cursor, plaintext)
    assert api_keys.revoke_key(cursor, 1)
    assert api_keys.authenticate(cursor, plaintext) is None


def test_api_key_needs_a_name_and_a_known_scope():
    with pytest.raises(api_keys.ApiKeyError) as missing:
        api_keys.create_key(_KeyCursor(), name=' ', scopes=['catalog:read'], created_by=1)
    assert missing.value.code == 'api_key_name_invalid'
    with pytest.raises(api_keys.ApiKeyError) as scopes:
        api_keys.create_key(_KeyCursor(), name='k', scopes=['nope'], created_by=1)
    assert scopes.value.code == 'api_key_scopes_invalid'


# Registry and OpenAPI --------------------------------------------------------

def test_every_public_route_declares_a_scope_and_the_document_lists_them():
    from api.v1 import public_api_bp  # noqa: F401 - registers the routes
    from api.v1.registry import operations, openapi_document

    ops = operations()
    assert {op.scope for op in ops} <= set(api_keys.SCOPES) | {None}
    paths = {op.path for op in ops}
    for path in ('/departments', '/courses', '/timetable', '/students', '/attendance/sessions', '/attendance/defaulters'):
        assert path in paths
    document = openapi_document('https://college.test/api/v1', api_keys.SCOPES)
    assert document['openapi'].startswith('3.1') and document['servers'][0]['url'] == 'https://college.test/api/v1'
    assert document['components']['securitySchemes']['ApiKey']['scheme'] == 'bearer'
    timetable = document['paths']['/timetable']['get']
    assert timetable['x-required-scope'] == 'timetable:read'
    assert {param['name'] for param in timetable['parameters']} >= {'course_id', 'class_id', 'limit', 'offset'}


def test_public_api_refuses_without_a_key_and_with_a_malformed_key():
    from app_factory import create_app

    client = create_app().test_client()   # the test config from .env.test; nothing here reaches the database
    assert client.get('/api/v1/openapi.json').status_code == 200          # the document is open
    missing = client.get('/api/v1/courses')
    assert missing.status_code == 401 and missing.get_json()['error']['code'] == 'unauthorized'
    malformed = client.get('/api/v1/courses', headers={'Authorization': 'Bearer nope'})
    assert malformed.status_code == 401 and 'not valid' in malformed.get_json()['error']['message']
    assert client.post('/api/v1/courses', headers={'Authorization': 'Bearer nope'}).status_code == 405
    assert 'Set-Cookie' not in missing.headers                           # no session cookie for machine clients


# Webhooks ---------------------------------------------------------------------

def test_signature_round_trip_and_tolerance():
    body = json.dumps({'event': 'attendance.marked', 'data': {'session_id': 3}}, sort_keys=True)
    now = int(time.time())
    signature = webhooks.sign('whsec_abc', str(now), body)
    assert signature.startswith('sha256=') and webhooks.verify('whsec_abc', str(now), body, signature, now=now)
    assert not webhooks.verify('whsec_abc', str(now), body + ' ', signature, now=now)
    assert not webhooks.verify('whsec_other', str(now), body, signature, now=now)
    assert not webhooks.verify('whsec_abc', str(now - 301), body, webhooks.sign('whsec_abc', str(now - 301), body), now=now)
    assert not webhooks.verify('whsec_abc', 'not-a-number', body, signature, now=now)


def test_parse_events_and_subscription():
    assert webhooks.parse_events('attendance.marked bogus timetable.published') == ('attendance.marked', 'timetable.published')
    assert webhooks.parse_events(['*', 'attendance.marked']) == ('*',)
    assert webhooks.parse_events('') == ()
    assert webhooks.subscribed({'events': '*'}, 'attendance.defaulters')
    assert not webhooks.subscribed({'events': 'attendance.marked'}, 'attendance.defaulters')


def test_url_checks_block_plain_http_and_private_hosts():
    with _app(TESTING=False).app_context():
        with pytest.raises(webhooks.WebhookError) as http:
            webhooks._check_url('http://example.test/hook')
        assert http.value.code == 'webhook_url_invalid'
        with pytest.raises(webhooks.WebhookError) as private:
            webhooks._check_url('https://127.0.0.1/hook')
        assert private.value.code == 'webhook_url_private'
        with pytest.raises(webhooks.WebhookError):
            webhooks._check_url('https://user:pw@example.test/hook')
    with _app(TESTING=False, WEBHOOK_ALLOW_PRIVATE=True, WEBHOOK_ALLOW_HTTP=True).app_context():
        webhooks._check_url('http://127.0.0.1:9000/hook')   # allowed for local development only


class _DeliveryCursor:
    def __init__(self, row, log):
        self.row = row
        self.log = log

    def execute(self, statement, params=()):
        self.log.append((' '.join(statement.split()), params))

    def fetchone(self):
        if self.log and self.log[-1][0].startswith('SELECT d.*'):
            return dict(self.row)
        return None

    def close(self):
        pass


class _DeliveryConnection:
    def __init__(self, row):
        self.row = row
        self.log = []
        self.commits = 0

    def cursor(self, dictionary=False):
        return _DeliveryCursor(self.row, self.log)

    def commit(self):
        self.commits += 1


def _delivery(attempts=0, active=1):
    with _app().app_context():
        secret_enc = encrypt_text('whsec_test')
    return {
        'id': 11, 'endpoint_id': 2, 'event': 'attendance.marked', 'delivery_key': 'd-1', 'payload_json': '{"event":"attendance.marked"}',
        'attempts': attempts, 'url': 'https://receiver.test/hook', 'secret_enc': secret_enc, 'is_active': active,
    }


def _updates(connection, table):
    return [(statement, params) for statement, params in connection.log if statement.startswith(f'UPDATE {table}')]


def test_process_one_posts_a_signed_body_and_marks_sent():
    calls = []

    def sender(url, body, headers, timeout):
        calls.append((url, body, headers, timeout))
        return 204

    connection = _DeliveryConnection(_delivery())
    with _app(WEBHOOK_TIMEOUT_SECONDS=7).app_context():
        assert webhooks.process_one(connection, 11, sender=sender) == 'sent'
    url, body, headers, timeout = calls[0]
    assert url == 'https://receiver.test/hook' and timeout == 7.0 and headers['X-Timetable-Event'] == 'attendance.marked'
    assert headers['X-Timetable-Delivery'] == 'd-1'
    assert webhooks.verify('whsec_test', headers['X-Timetable-Timestamp'], body, headers['X-Timetable-Signature'])
    statement, params = _updates(connection, 'webhook_deliveries')[0]
    assert "status = 'sent'" in statement and params == (204, 11)
    assert _updates(connection, 'webhook_endpoints')[0][1] == ('sent', 2) and connection.commits == 1


def test_process_one_retries_with_backoff_then_fails_at_the_attempt_limit():
    connection = _DeliveryConnection(_delivery(attempts=0))
    with _app(WEBHOOK_MAX_ATTEMPTS=2).app_context():
        assert webhooks.process_one(connection, 11, sender=lambda *a: 500) == 'retry'
    statement, params = _updates(connection, 'webhook_deliveries')[0]
    assert params[0] == 'queued' and params[1] == 1 and params[2] == 500 and params[3] == 'HTTP 500' and params[4] == 30

    def refused(*args):
        raise ConnectionRefusedError('refused')

    connection = _DeliveryConnection(_delivery(attempts=1))
    with _app(WEBHOOK_MAX_ATTEMPTS=2).app_context():
        assert webhooks.process_one(connection, 11, sender=refused) == 'failed'
    statement, params = _updates(connection, 'webhook_deliveries')[0]
    assert params[0] == 'failed' and params[1] == 2 and params[2] is None and params[3].startswith('ConnectionRefusedError') and params[4] == 60
    assert _updates(connection, 'webhook_endpoints')[0][1] == ('failed', 2)


def test_process_one_fails_a_delivery_for_an_inactive_endpoint_without_posting():
    posted = []
    connection = _DeliveryConnection(_delivery(active=0))
    with _app().app_context():
        assert webhooks.process_one(connection, 11, sender=lambda *a: posted.append(a) or 200) == 'failed'
    assert posted == [] and _updates(connection, 'webhook_deliveries')[0][1][0] == 'failed'


def test_emit_rejects_unknown_events():
    with pytest.raises(ValueError):
        webhooks.emit(None, 'carrier.pigeon', {})


# SSO: token verification ------------------------------------------------------

def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _jwt(private_key, claims, kid='k1', alg='RS256'):
    header = _b64url(json.dumps({'alg': alg, 'kid': kid, 'typ': 'JWT'}).encode())
    payload = _b64url(json.dumps(claims).encode())
    signature = private_key.sign(f'{header}.{payload}'.encode('ascii'), padding.PKCS1v15(), hashes.SHA256())
    return f'{header}.{payload}.{_b64url(signature)}'


def _jwks(private_key, kid='k1'):
    numbers = private_key.public_key().public_numbers()
    return {'keys': [{
        'kty': 'RSA', 'kid': kid, 'alg': 'RS256', 'use': 'sig',
        'n': _b64url(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, 'big')),
        'e': _b64url(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, 'big')),
    }]}


@pytest.fixture(scope='module')
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _claims(now, **extra):
    return {'iss': 'https://idp.test', 'aud': 'client-1', 'sub': 'abc', 'exp': now + 300, 'iat': now, 'nonce': 'n1',
            'email': 'hod@college.test', 'email_verified': True, **extra}


def test_verify_id_token_accepts_a_valid_token(rsa_key):
    now = int(time.time())
    claims = sso.verify_id_token(_jwt(rsa_key, _claims(now)), _jwks(rsa_key), issuer='https://idp.test', audience='client-1', nonce='n1', now=now)
    assert claims['sub'] == 'abc' and claims['email'] == 'hod@college.test'
    sso.verify_id_token(_jwt(rsa_key, _claims(now, iss='https://idp.test/')), _jwks(rsa_key), issuer='https://idp.test', audience='client-1', now=now)


@pytest.mark.parametrize('breakage', ['signature', 'issuer', 'audience', 'expired', 'nonce', 'alg', 'kid', 'no_sub'])
def test_verify_id_token_refuses_every_tampering(rsa_key, breakage):
    now = int(time.time())
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = _claims(now)
    keys = _jwks(rsa_key)
    token = _jwt(rsa_key, claims)
    if breakage == 'signature':
        token = _jwt(other, claims)
    elif breakage == 'issuer':
        token = _jwt(rsa_key, _claims(now, iss='https://evil.test'))
    elif breakage == 'audience':
        token = _jwt(rsa_key, _claims(now, aud='someone-else'))
    elif breakage == 'expired':
        token = _jwt(rsa_key, _claims(now, exp=now - 120))
    elif breakage == 'nonce':
        token = _jwt(rsa_key, _claims(now, nonce='other'))
    elif breakage == 'alg':
        token = _jwt(rsa_key, claims, alg='none')
    elif breakage == 'kid':
        token = _jwt(rsa_key, claims, kid='unknown')
    elif breakage == 'no_sub':
        claims.pop('sub')
        token = _jwt(rsa_key, claims)
    with pytest.raises(sso.SsoError) as failure:
        sso.verify_id_token(token, keys, issuer='https://idp.test', audience='client-1', nonce='n1', now=now)
    assert failure.value.code == 'sso_token_invalid'


def test_sso_settings_validation():
    class Cursor:
        def __init__(self):
            self.saved = None

        def execute(self, statement, params=()):
            self.statement = ' '.join(statement.split())
            self.params = params

        def fetchone(self):
            if 'information_schema' in self.statement:
                return {'n': 1}
            return None

    with _app().app_context():
        cursor = Cursor()
        with pytest.raises(sso.SsoError) as incomplete:
            sso.save_settings(cursor, {'enabled': True, 'provider': 'google'}, 1)
        assert incomplete.value.code == 'sso_incomplete'
        with pytest.raises(sso.SsoError) as issuer:
            sso.save_settings(cursor, {'issuer': 'http://plain.test'}, 1)
        assert issuer.value.code == 'sso_issuer_invalid'
        sso.save_settings(cursor, {'provider': 'google', 'issuer': '', 'allowed_domains': 'College.test, other.test'}, 1)
        assert cursor.statement.startswith('INSERT INTO sso_settings')
        assert 'https://accounts.google.com' in cursor.params and 'college.test other.test' in cursor.params
    assert sso._email_allowed('a@college.test', 'college.test other.test') and not sso._email_allowed('a@evil.test', 'college.test')
    assert sso._email_allowed('a@anywhere.test', None)


# Revision 0013 ----------------------------------------------------------------

def _load_0013():
    path = Path(MIGRATIONS_DIR) / 'versions' / '0013_integrations.py'
    spec = importlib.util.spec_from_file_location('revision_0013', path)
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


def test_0013_follows_0012_and_creates_only_missing_tables(monkeypatch):
    module = _load_0013()
    assert module.down_revision == '0012_lab_batches'
    executed = []
    monkeypatch.setattr(module.op, 'execute', lambda statement: executed.append(statement))

    monkeypatch.setattr(module.op, 'get_bind', lambda: _Bind({'api_keys', 'webhook_endpoints'}))
    module.upgrade()
    assert [statement.split('(')[0].strip() for statement in executed] == [
        'CREATE TABLE webhook_deliveries', 'CREATE TABLE sso_settings', 'CREATE TABLE sso_identities',
    ]
    for column in ('locked_by', 'heartbeat_at', 'progress', 'available_at', 'delivery_key'):
        assert column in module.WEBHOOK_DELIVERIES
    assert 'key_hash' in module.API_KEYS and 'secret_enc' in module.WEBHOOK_ENDPOINTS and 'client_secret_enc' in module.SSO_SETTINGS

    executed.clear()
    monkeypatch.setattr(module.op, 'get_bind', lambda: _Bind({name for name, _ in module.TABLES}))
    module.upgrade()
    assert executed == []
    module.downgrade()
    assert executed == [f'DROP TABLE `{name}`' for name, _ in reversed(module.TABLES)]
