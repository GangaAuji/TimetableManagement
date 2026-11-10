"""0009_worker_claims adds each column only when missing and drops only what exists. No database."""

import importlib.util
from pathlib import Path

import pytest

from core.schema.baseline import MIGRATIONS_DIR
from core.schema.status import head_revision


def _load():
    path = Path(MIGRATIONS_DIR) / 'versions' / '0009_worker_claims.py'
    spec = importlib.util.spec_from_file_location('revision_0009', path)
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
        return _Result((1,) if f"{params['table']}.{params['column']}" in self.present else None)


@pytest.fixture
def revision(monkeypatch):
    module = _load()
    executed = []
    monkeypatch.setattr(module.op, 'execute', lambda statement: executed.append(statement))
    return module, executed


def test_0009_follows_0008():
    assert head_revision() in ('0009_worker_claims', '0010_face_safeguards') or head_revision() > '0010'
    module = _load()
    assert module.down_revision == '0008_attendance_views'


def test_upgrade_adds_only_missing_columns(revision, monkeypatch):
    module, executed = revision
    monkeypatch.setattr(module.op, 'get_bind', lambda: _Connection({'processed_reports.locked_by'}))
    module.upgrade()
    assert [s.split(' ADD COLUMN ')[0].split('`')[1] + '.' + s.split('`')[3] for s in executed] == [
        'processed_reports.heartbeat_at', 'timetable_jobs.locked_by', 'timetable_jobs.heartbeat_at',
    ]
    assert all('ADD COLUMN' in s for s in executed)


def test_downgrade_drops_only_existing_columns(revision, monkeypatch):
    module, executed = revision
    monkeypatch.setattr(module.op, 'get_bind', lambda: _Connection({'timetable_jobs.heartbeat_at', 'timetable_jobs.locked_by'}))
    module.downgrade()
    assert executed == [
        'ALTER TABLE `timetable_jobs` DROP COLUMN `heartbeat_at`',
        'ALTER TABLE `timetable_jobs` DROP COLUMN `locked_by`',
    ]


def test_nothing_runs_when_already_applied(revision, monkeypatch):
    module, executed = revision
    everything = {f'{t}.{c}' for t in module.TABLES for c, _ in module.COLUMNS}
    monkeypatch.setattr(module.op, 'get_bind', lambda: _Connection(everything))
    module.upgrade()
    assert executed == []
