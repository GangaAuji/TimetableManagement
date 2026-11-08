"""Revision 0007 statements. No live database."""

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / 'migrations' / 'versions' / '0007_lecture_sessions.py'
_spec = importlib.util.spec_from_file_location('lecture_sessions_revision', _PATH)
_revision = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_revision)

ALL = {'lecture_sessions', 'attendance_excuses', 'attendance.session_id', 'idx_attendance_session', 'fk_attendance_session'}


def test_revision_follows_the_sign_in_lock():
    assert _revision.revision == '0007_lecture_sessions'
    assert _revision.down_revision == '0006_sign_in_lock'


def test_upgrade_creates_only_what_is_missing_in_dependency_order():
    statements = _revision.upgrade_statements(set())
    assert len(statements) == 5
    assert statements[0].lstrip().startswith('CREATE TABLE lecture_sessions')
    assert statements[1].lstrip().startswith('CREATE TABLE attendance_excuses')
    assert 'ADD COLUMN session_id' in statements[2]
    assert 'ADD KEY idx_attendance_session' in statements[3]
    assert 'REFERENCES lecture_sessions (id) ON DELETE RESTRICT' in statements[4]
    assert _revision.upgrade_statements(ALL) == []
    partial = _revision.upgrade_statements({'lecture_sessions', 'attendance_excuses', 'attendance.session_id'})
    assert [s.split()[5] for s in partial] == ['idx_attendance_session', 'fk_attendance_session']


def test_session_table_restricts_slot_deletion_and_is_unique_per_slot_and_date():
    create = _revision.LECTURE_SESSIONS
    assert 'REFERENCES timetable (id) ON DELETE RESTRICT' in create
    assert 'UNIQUE KEY uk_lecture_session (timetable_id, session_date)' in create
    assert "status enum('held','cancelled','not_marked') NOT NULL" in create
    assert "source enum('teacher','mobile','admin','close_day','backfill') NOT NULL" in create
    assert 'session_id int(11) DEFAULT NULL' in _revision.upgrade_statements(set())[2]


def test_downgrade_drops_only_what_exists_in_reverse():
    assert _revision.downgrade_statements(ALL) == [
        'ALTER TABLE attendance DROP FOREIGN KEY fk_attendance_session',
        'ALTER TABLE attendance DROP KEY idx_attendance_session',
        'ALTER TABLE attendance DROP COLUMN session_id',
        'DROP TABLE attendance_excuses',
        'DROP TABLE lecture_sessions',
    ]
    assert _revision.downgrade_statements({'lecture_sessions'}) == ['DROP TABLE lecture_sessions']
    assert _revision.downgrade_statements(set()) == []
