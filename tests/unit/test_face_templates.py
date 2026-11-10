"""Face template codec, the passive-check rules that need no database, and revision 0010. No live database."""

import importlib.util
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from flask import Flask

from core.schema.baseline import MIGRATIONS_DIR
from core.schema.status import head_revision
from services.face import safeguards, templates

KEY_A = Fernet.generate_key().decode('ascii')
KEY_B = Fernet.generate_key().decode('ascii')


def _app(**config):
    app = Flask('face-unit')
    app.config.update(config)
    return app


def test_without_a_key_templates_are_plaintext_and_both_forms_decode():
    with _app(FACE_TEMPLATE_KEY=None).app_context():
        assert templates.encode_template([1, 0.5]) == '[1.0,0.5]'
        assert templates.decode_template('[1.0,0.5]') == [1.0, 0.5]
        assert templates.decode_template(b'[2]') == [2.0]
        assert templates.decode_template('enc:v1:abc') is None      # encrypted, no key
        assert templates.decode_template('not json') is None
        assert templates.decode_template('{"a": 1}') is None
        assert templates.decode_template(None) is None
        assert templates.key_problem() and 'not set' in templates.key_problem()
    assert templates.decode_template('[3]') == [3.0]               # no app context at all


def test_with_a_key_templates_are_encrypted_and_round_trip():
    with _app(FACE_TEMPLATE_KEY=KEY_A).app_context():
        stored = templates.encode_template([0.25, -1])
        assert templates.is_encrypted(stored) and '0.25' not in stored
        assert templates.decode_template(stored) == [0.25, -1.0]
        assert templates.needs_rewrite('[1]') is True
        assert templates.needs_rewrite(stored) is False
        assert templates.key_problem() is None
    with _app(FACE_TEMPLATE_KEY='short').app_context():
        assert 'not a valid Fernet key' in templates.key_problem()
        with pytest.raises(RuntimeError):
            templates.encode_template([1])


def test_rotation_reads_the_previous_key_and_rewrites_to_the_current_one():
    with _app(FACE_TEMPLATE_KEY=KEY_A).app_context():
        old = templates.encode_template([7])
    with _app(FACE_TEMPLATE_KEY=KEY_B).app_context():
        assert templates.decode_template(old) is None
        assert templates.needs_rewrite(old) is True
    with _app(FACE_TEMPLATE_KEY=KEY_B, FACE_TEMPLATE_KEY_PREVIOUS=KEY_A).app_context():
        assert templates.decode_template(old) == [7.0]
        assert templates.needs_rewrite(old) is True
        new = templates.encode_template(templates.decode_template(old))
        assert templates.needs_rewrite(new) is False
    with _app(FACE_TEMPLATE_KEY=KEY_B).app_context():
        assert templates.decode_template(new) == [7.0]


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.updates = []

    def execute(self, statement, params=None):
        if statement.startswith('SELECT'):
            last_id, limit = params
            self._batch = [row for row in self.rows if row['id'] > last_id][:limit]
        else:
            self.updates.append(params)
            for row in self.rows:
                if row['id'] == params[1]:
                    row['embedding_json'] = params[0]

    def fetchall(self):
        return self._batch


def test_reencrypt_all_rewrites_plaintext_and_foreign_key_rows_only():
    with _app(FACE_TEMPLATE_KEY=KEY_A).app_context():
        current = templates.encode_template([1])
    with _app(FACE_TEMPLATE_KEY=KEY_B).app_context():
        foreign = templates.encode_template([2])
    rows = [
        {'id': 1, 'embedding_json': '[3]'}, {'id': 2, 'embedding_json': current},
        {'id': 3, 'embedding_json': foreign}, {'id': 4, 'embedding_json': 'broken'},
    ]
    cursor = _Cursor(rows)
    with _app(FACE_TEMPLATE_KEY=KEY_A, FACE_TEMPLATE_KEY_PREVIOUS=KEY_B).app_context():
        counts = templates.reencrypt_all(cursor, batch=2)
        assert counts == {'rewritten': 2, 'already': 1, 'unreadable': 1}
        assert [params[1] for params in cursor.updates] == [1, 3]
        assert [templates.decode_template(row['embedding_json']) for row in rows] == [[3.0], [1.0], [2.0], None]
        assert all(templates.is_encrypted(row['embedding_json']) for row in rows[:3])
    with _app(FACE_TEMPLATE_KEY=None).app_context():
        with pytest.raises(RuntimeError):
            templates.reencrypt_all(cursor)


def test_frame_hash_accepts_a_digest_or_hashes_anything_else():
    digest = 'a' * 64
    assert safeguards.frame_hash_of(digest.upper()) == digest
    assert safeguards.frame_hash_of('frame-1') == safeguards.frame_hash_of(' frame-1 ')
    assert len(safeguards.frame_hash_of('frame-1')) == 64
    assert safeguards.frame_hash_of('') is None and safeguards.frame_hash_of(None) is None


def test_session_code_check_without_a_code_depends_on_the_flag():
    with _app(FACE_REQUIRE_SESSION_CODE=False).app_context():
        assert safeguards.check_session_code(None, 1, '2026-01-05', '') == (True, 'ok')
    with _app(FACE_REQUIRE_SESSION_CODE=True).app_context():
        assert safeguards.check_session_code(None, 1, '2026-01-05', None) == (False, safeguards.SESSION_CODE_REQUIRED)


# Revision 0010

def _load_0010():
    path = Path(MIGRATIONS_DIR) / 'versions' / '0010_face_safeguards.py'
    spec = importlib.util.spec_from_file_location('revision_0010', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Result:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row


class _Connection:
    def __init__(self, present):
        self.present = set(present)

    def execute(self, statement, params):
        return _Result((1,) if params['table'] in self.present else None)


def test_0010_follows_0009_and_creates_only_missing_tables(monkeypatch):
    assert head_revision() >= '0010_face_safeguards'
    module = _load_0010()
    assert module.down_revision == '0009_worker_claims'
    executed = []
    monkeypatch.setattr(module.op, 'execute', lambda statement: executed.append(statement))

    monkeypatch.setattr(module.op, 'get_bind', lambda: _Connection({'face_consents'}))
    module.upgrade()
    assert len(executed) == 1 and 'CREATE TABLE face_recognition_audit' in executed[0]

    executed.clear()
    monkeypatch.setattr(module.op, 'get_bind', lambda: _Connection({'face_consents', 'face_recognition_audit'}))
    module.upgrade()
    assert executed == []
    module.downgrade()
    assert executed == ['DROP TABLE `face_recognition_audit`', 'DROP TABLE `face_consents`']
