"""Revision 0008 statements. No live database."""

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / 'migrations' / 'versions' / '0008_attendance_views.py'
_spec = importlib.util.spec_from_file_location('attendance_views_revision', _PATH)
_revision = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_revision)

VIEWS = {'attendance_summary', 'student_overall_attendance'}


def test_revision_follows_lecture_sessions():
    assert _revision.revision == '0008_attendance_views'
    assert _revision.down_revision == '0007_lecture_sessions'


def test_upgrade_refuses_while_any_mark_has_no_session():
    with pytest.raises(RuntimeError) as refused:
        _revision.upgrade_statements(3, True, VIEWS)
    message = str(refused.value)
    assert message.startswith('3 attendance row(s) have no session_id')
    assert 'flask attendance backfill-sessions --dry-run' in message and 'cancelled lectures' in message


def test_upgrade_changes_only_what_needs_it():
    assert _revision.upgrade_statements(0, True, VIEWS | {'faculty_summary'}) == [
        'ALTER TABLE attendance MODIFY session_id int(11) NOT NULL',
        'DROP VIEW IF EXISTS `attendance_summary`',
        'DROP VIEW IF EXISTS `student_overall_attendance`',
    ]
    assert _revision.upgrade_statements(0, False, {'attendance_summary'}) == ['DROP VIEW IF EXISTS `attendance_summary`']
    assert _revision.upgrade_statements(0, False, set()) == []


def test_downgrade_recreates_the_missing_views_from_the_baseline_text():
    statements = _revision.downgrade_statements(False, set())
    assert statements[0] == 'ALTER TABLE attendance MODIFY session_id int(11) DEFAULT NULL'
    assert 'SET NAMES utf8mb4' in statements[:5]
    created = [s for s in statements if s.upper().startswith('CREATE')]
    assert [s.split('VIEW `')[1].split('`')[0] for s in created] == ['attendance_summary', 'student_overall_attendance']
    assert all('SQL SECURITY INVOKER' in s and 'DEFINER' not in s for s in created)
    assert statements[-1] == 'SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION'
    only_one = _revision.downgrade_statements(True, {'attendance_summary'})
    assert [s for s in only_one if s.upper().startswith('CREATE')][0].count('student_overall_attendance') == 1
    assert 'ALTER TABLE' not in ' '.join(only_one)
    assert _revision.downgrade_statements(True, VIEWS) == []
