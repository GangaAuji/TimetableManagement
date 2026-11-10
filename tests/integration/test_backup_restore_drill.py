"""The restore drill: dump the test database the way deploy/backup.sh does, restore it like deploy/restore.sh, compare.

Needs the mysqldump and mysql client programs. They are looked up in
MYSQLDUMP / MYSQL_CLIENT, then the XAMPP folder, then PATH; without them the
test is skipped. The restored copy is a scratch *_test database dropped at
the end. The password travels in a temporary defaults file, never on the
command line.
"""

import gzip
import os
import shutil
import subprocess
import tempfile

import pytest

from core.schema.introspect import compare, read_schema
from tests.integration.live_helpers import credentials, database_connection, drop, scratch_name, server_connection

pytestmark = pytest.mark.live_db

_XAMPP = r'C:\xampp\mysql\bin'


def _program(name, env_name):
    configured = os.environ.get(env_name)
    if configured and os.path.isfile(configured):
        return configured
    xampp = os.path.join(_XAMPP, f'{name}.exe')
    if os.path.isfile(xampp):
        return xampp
    return shutil.which(name)


@pytest.fixture(scope='module')
def programs():
    dump, client = _program('mysqldump', 'MYSQLDUMP'), _program('mysql', 'MYSQL_CLIENT')
    if not dump or not client:
        pytest.skip('mysqldump and mysql client programs are needed for the restore drill.')
    return dump, client


@pytest.fixture
def defaults_file():
    host, user, password = credentials()
    handle, path = tempfile.mkstemp(prefix='drill-', suffix='.cnf')
    with os.fdopen(handle, 'w', encoding='utf-8') as out:
        out.write(f'[client]\nhost={host}\nuser={user}\npassword={password}\n')
    try:
        yield path
    finally:
        os.remove(path)


def _row_counts(connection):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        counts = {}
        for name in tables:
            cursor.execute(f'SELECT COUNT(*) FROM `{name}`')
            counts[name] = cursor.fetchone()[0]
        connection.rollback()
        return counts
    finally:
        cursor.close()


def test_dump_and_restore_reproduce_schema_and_rows(test_database, programs, defaults_file, tmp_path):
    mysqldump, mysql = programs
    source = test_database.name
    restored = scratch_name('restore_drill')
    dump_path = tmp_path / f'{source}.sql.gz'

    dumped = subprocess.run(
        [mysqldump, f'--defaults-extra-file={defaults_file}', '--single-transaction', '--quick', '--routines',
         '--triggers', '--events', '--default-character-set=utf8mb4', source],
        capture_output=True, timeout=600,
    )
    assert dumped.returncode == 0, dumped.stderr.decode('utf-8', 'replace')[:500]
    with gzip.open(dump_path, 'wb') as out:
        out.write(dumped.stdout)
    assert dump_path.stat().st_size > 1000

    server = server_connection()
    cursor = server.cursor()
    try:
        drop(cursor, restored)
        cursor.execute(f'CREATE DATABASE `{restored}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
        with gzip.open(dump_path, 'rb') as dump:
            loaded = subprocess.run(
                [mysql, f'--defaults-extra-file={defaults_file}', restored],
                input=dump.read(), capture_output=True, timeout=600,
            )
        assert loaded.returncode == 0, loaded.stderr.decode('utf-8', 'replace')[:500]

        original = database_connection(source)
        copy = database_connection(restored)
        try:
            schema_a = read_schema(original.cursor(), source)
            schema_b = read_schema(copy.cursor(), restored)
            assert compare(schema_a, schema_b) == []
            counts_a, counts_b = _row_counts(original), _row_counts(copy)
            assert counts_b == counts_a
            assert counts_a['roles'] > 0 and counts_a['alembic_version'] == 1
        finally:
            original.close()
            copy.close()
    finally:
        drop(cursor, restored)
        cursor.close()
        server.close()
