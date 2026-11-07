"""Upload paths and the single-commit wrapper. No live database."""

from io import BytesIO

import pytest
from flask import Flask
from werkzeug.datastructures import FileStorage

from core.db import transaction
from utils.uploads import save_uploaded_file


class _Connection:
    def __init__(self):
        self.actions = []

    def commit(self):
        self.actions.append('commit')

    def rollback(self):
        self.actions.append('rollback')


def _upload(name):
    return FileStorage(stream=BytesIO(b'abc'), filename=name)


def test_save_uploaded_file_keeps_the_branding_name(tmp_path):
    app = Flask('app', root_path=str(tmp_path))
    with app.app_context():
        relative = save_uploaded_file(
            _upload('Logo.PNG'),
            'uploads/branding',
            allowed_extensions={'png', 'jpg', 'jpeg', 'gif', 'svg'},
            name_prefix='site_logo',
            timestamp='20260101120000',
        )
    stored = tmp_path / 'static' / 'uploads' / 'branding' / 'site_logo_20260101120000_Logo.PNG'
    assert relative == 'uploads/branding/site_logo_20260101120000_Logo.PNG'
    assert stored.read_bytes() == b'abc'


def test_save_uploaded_file_rejects_a_disallowed_extension(tmp_path):
    app = Flask('app', root_path=str(tmp_path))
    with app.app_context():
        with pytest.raises(ValueError, match='unsupported upload'):
            save_uploaded_file(
                _upload('notes.exe'),
                'uploads/profiles',
                allowed_extensions={'png', 'jpg', 'jpeg', 'gif'},
                name_prefix='4',
                timestamp='20260101120000',
            )
    assert not (tmp_path / 'static').exists()


def test_transaction_commits_when_the_block_finishes():
    connection = _Connection()
    with transaction(connection):
        connection.actions.append('work')
    assert connection.actions == ['work', 'commit']


def test_transaction_rolls_back_without_committing_when_the_block_raises():
    connection = _Connection()
    with pytest.raises(RuntimeError, match='fail'):
        with transaction(connection):
            raise RuntimeError('fail')
    assert connection.actions == ['rollback']


def test_transaction_ignores_a_missing_connection():
    with transaction(None):
        pass
