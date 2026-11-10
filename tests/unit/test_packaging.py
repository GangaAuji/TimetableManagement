"""License signatures and support-bundle redaction. No database connection."""

import json
from datetime import date, timedelta

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from flask import Flask

from core.license import evaluate, growth_block, refuse_student, sign_document
from core.support_bundle import build_report, redact_env, scrub


def _keys():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    import base64
    return private, base64.b64encode(public).decode('ascii')


def _config(public, **extra):
    config = {'LICENSE_REQUIRED': True, 'LICENSE_PUBLIC_KEY': public, 'LICENSE_FILE': ''}
    config.update(extra)
    return config


class _Cursor:
    def execute(self, *_args, **_kwargs):
        raise AssertionError('license check queried the database while it is not required')


def test_an_optional_license_does_not_query_or_block():
    assert refuse_student(_Cursor(), {'LICENSE_REQUIRED': False}) is None
    status = evaluate({'LICENSE_REQUIRED': False, 'LICENSE_FILE': 'missing-license.json'})
    assert status['state'] == 'not_required'
    assert status['problem'] is None
    assert growth_block({'LICENSE_REQUIRED': False}, 'students', 100000) is None


def test_a_required_license_must_be_signed_and_current(tmp_path):
    private, public = _keys()
    document = sign_document(
        {
            'customer': 'North College',
            'edition': 'campus',
            'expires': (date.today() + timedelta(days=30)).isoformat(),
            'max_students': 10,
            'max_institutions': 1,
            'capabilities': ['security_policy'],
        },
        private,
    )
    path = tmp_path / 'license.json'
    path.write_text(json.dumps(document), encoding='utf-8')
    config = _config(public, LICENSE_FILE=str(path))
    status = evaluate(config)
    assert status['state'] == 'ok'
    assert status['customer'] == 'North College'
    assert status['problem'] is None
    assert growth_block(config, 'students', 10)[0] == 'license_students'
    assert growth_block(config, 'students', 9) is None

    tampered = dict(document)
    tampered['customer'] = 'Someone else'
    path.write_text(json.dumps(tampered), encoding='utf-8')
    assert evaluate(config)['state'] == 'invalid'

    missing = _config(public, LICENSE_FILE=str(tmp_path / 'absent.json'))
    assert 'required' in evaluate(missing)['problem']


def test_expiry_allows_one_grace_day(tmp_path):
    private, public = _keys()
    today = date(2026, 6, 15)
    path = tmp_path / 'license.json'

    def write(expires):
        path.write_text(json.dumps(sign_document({
            'customer': 'North College', 'edition': 'campus', 'expires': expires,
            'max_students': None, 'max_institutions': None, 'capabilities': [],
        }, private)), encoding='utf-8')

    config = _config(public, LICENSE_FILE=str(path))
    write((today - timedelta(days=1)).isoformat())
    assert evaluate(config, today=today)['state'] == 'ok'
    write((today - timedelta(days=2)).isoformat())
    assert evaluate(config, today=today)['state'] == 'expired'


def test_support_report_drops_secret_values(tmp_path):
    secret = 'database-password-value'
    log = tmp_path / 'app.log'
    log.write_text(f'connected with {secret}\n', encoding='utf-8')
    env = redact_env({
        'MYSQL_HOST': '127.0.0.1',
        'MYSQL_PASSWORD': secret,
        'SECRET_KEY': 'flask-secret-value',
        'FACE_TEMPLATE_KEY': 'face-key-value',
    })
    assert env['MYSQL_HOST'] == '127.0.0.1'
    assert env['MYSQL_PASSWORD'] == ''
    assert env['SECRET_KEY'] == ''
    assert secret not in ''.join(env.values())
    assert scrub(log.read_text(encoding='utf-8'), [secret]) == 'connected with [redacted]\n'

    app = Flask('packaging-unit')
    app.config.update(
        LICENSE_REQUIRED=False,
        LICENSE_FILE='',
        LOG_FILE=str(log),
        MYSQL_HOST='127.0.0.1',
        MYSQL_PASSWORD=secret,
        SECRET_KEY='flask-secret-value',
        FLASK_ENV='testing',
    )
    with app.app_context():
        report = build_report(app, 'ok')
    encoded = json.dumps(report)
    assert secret not in encoded
    assert 'flask-secret-value' not in encoded
    assert report['database'] == 'ok'
    assert report['license']['state'] == 'not_required'
