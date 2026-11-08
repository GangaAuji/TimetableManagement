"""`flask attendance backfill-sessions`: held sessions for marked lectures, links, anomalies, and a dry run that writes nothing.

The backfill exists for a database at 0007, where marks may still lack a
session; 0008 makes `attendance.session_id` NOT NULL. This module therefore
steps the test database down to 0007 first and back to head at the end, and
checks that 0008 refuses while unlinked marks exist and runs once they are
linked.
"""

from datetime import datetime, timedelta

import pytest

from core.schema.status import head_revision
from services.lecture_sessions import backfill_sessions
from tests.factories import LECTURE_DATE
from tests.integration.live_helpers import migrate

pytestmark = pytest.mark.live_db

TUESDAY = LECTURE_DATE + timedelta(days=1)
EARLIER_MONDAY = LECTURE_DATE - timedelta(days=7)
BEFORE_NOT_NULL = '0007_lecture_sessions'


@pytest.fixture(scope='module', autouse=True)
def at_0007(test_database):
    """The test database at 0007 for this module; head again afterwards."""
    test_database.connection.rollback()   # release metadata locks so ALTER TABLE can run
    migrate(test_database.name, 'downgrade', BEFORE_NOT_NULL)
    yield
    test_database.connection.rollback()
    migrate(test_database.name, 'upgrade', 'head')


def _revision(factory):
    return factory.query('SELECT version_num FROM alembic_version')[0]['version_num']


def _mark(factory, setup, student, when, status='Present', marked_by=None, marked_at=None):
    """An attendance row the way the app wrote it before 0007: no session."""
    return factory.insert(
        'attendance', student_id=student['student_id'], timetable_id=setup['timetable_id'], attendance_date=when,
        status=status, marked_by=marked_by or setup['teacher']['faculty_id'],
        marked_at=marked_at or datetime(when.year, when.month, when.day, 9, 15),
    )


def _sessions(factory, timetable_id):
    return factory.query(
        'SELECT id, session_date, status, source, marked_by, marked_at, taught_by FROM lecture_sessions '
        'WHERE timetable_id = %s ORDER BY session_date', (timetable_id,),
    )


def _unlinked(factory, timetable_id):
    return factory.query('SELECT id FROM attendance WHERE timetable_id = %s AND session_id IS NULL', (timetable_id,))


@pytest.fixture
def history(factory):
    setup = factory.academic()
    first = factory.user('Student', setup=setup)
    second = factory.user('Student', setup=setup)
    _mark(factory, setup, first, EARLIER_MONDAY, marked_at=datetime(2026, 11, 2, 9, 20))
    _mark(factory, setup, second, EARLIER_MONDAY, status='Absent', marked_at=datetime(2026, 11, 2, 9, 10))
    _mark(factory, setup, first, LECTURE_DATE)
    _mark(factory, setup, second, LECTURE_DATE, status='Late')
    return setup, first, second


def test_dry_run_reports_and_changes_nothing(db, factory, history):
    setup, _, _ = history
    report = backfill_sessions(db, dry_run=True)
    assert report.dry_run is True
    assert report.sessions >= 2 and report.rows >= 4
    assert _sessions(factory, setup['timetable_id']) == []
    assert len(_unlinked(factory, setup['timetable_id'])) == 4
    assert factory.query("SELECT 1 FROM audit_logs WHERE action = 'attendance_backfill_sessions'") == []
    assert any('Sessions to create' in line for line in report.lines())


def test_apply_creates_held_sessions_links_marks_and_is_idempotent(db, factory, history):
    setup, _, _ = history
    report = backfill_sessions(db)
    assert report.sessions >= 2 and report.rows >= 4
    rows = _sessions(factory, setup['timetable_id'])
    assert [(r['session_date'], r['status'], r['source']) for r in rows] == [
        (EARLIER_MONDAY, 'held', 'backfill'), (LECTURE_DATE, 'held', 'backfill'),
    ]
    assert rows[0]['marked_at'] == datetime(2026, 11, 2, 9, 10)      # the earliest mark
    assert rows[0]['marked_by'] == setup['teacher']['faculty_id'] and rows[0]['taught_by'] == setup['teacher']['id']
    assert _unlinked(factory, setup['timetable_id']) == []
    linked = factory.query(
        'SELECT a.attendance_date, ls.session_date FROM attendance a JOIN lecture_sessions ls ON ls.id = a.session_id '
        'WHERE a.timetable_id = %s', (setup['timetable_id'],),
    )
    assert all(row['attendance_date'] == row['session_date'] for row in linked) and len(linked) == 4
    [entry] = factory.query("SELECT new_values FROM audit_logs WHERE action = 'attendance_backfill_sessions'")
    assert '"dry_run": false' in entry['new_values']
    again = backfill_sessions(db)
    assert again.sessions == 0 and again.rows == 0
    assert len(_sessions(factory, setup['timetable_id'])) == 2


def test_backfill_never_invents_unmarked_lectures(db, factory, history):
    setup, _, _ = history
    backfill_sessions(db)
    dates = {row['session_date'] for row in _sessions(factory, setup['timetable_id'])}
    assert dates == {EARLIER_MONDAY, LECTURE_DATE}       # the Monday in between (no marks) has no row


def test_anomalies_are_reported_not_fixed(db, factory):
    setup = factory.academic()
    student = factory.user('Student', setup=setup)
    stranger = factory.user('Student', setup=factory.academic())
    other_teacher = factory.user('Teacher', setup=setup)
    _mark(factory, setup, student, TUESDAY)                                        # weekday mismatch
    _mark(factory, setup, stranger, LECTURE_DATE)                                  # outside the roster
    _mark(factory, setup, student, LECTURE_DATE, marked_by=other_teacher['faculty_id'])   # marker is not the teacher
    factory.insert('institution_holidays', holiday_date=LECTURE_DATE, name='Backfill holiday', applies_to_program='Both', is_recurring=0)
    factory.execute('UPDATE timetable SET is_active = 0 WHERE id = %s', (setup['timetable_id'],))
    report = backfill_sessions(db, dry_run=True)
    kinds = {kind for kind, items in report.anomalies.items() if any(i['timetable_id'] == setup['timetable_id'] for i in items)}
    assert kinds == {'weekday_mismatch', 'retired_slot', 'marker_not_teacher', 'holiday', 'outside_roster'}
    outside = [i for i in report.anomalies['outside_roster'] if i['timetable_id'] == setup['timetable_id']]
    assert str(stranger['student_id']) in outside[0]['detail']
    assert _sessions(factory, setup['timetable_id']) == []
    backfill_sessions(db)
    rows = _sessions(factory, setup['timetable_id'])
    assert [(r['session_date'], r['status']) for r in rows] == [(LECTURE_DATE, 'held'), (TUESDAY, 'held')]
    assert _unlinked(factory, setup['timetable_id']) == []
    [entry] = factory.query("SELECT new_values FROM audit_logs WHERE action = 'attendance_backfill_sessions'")
    assert 'weekday_mismatch' in entry['new_values']


def test_marks_on_a_cancelled_session_are_left_for_review(db, factory):
    setup = factory.academic()
    student = factory.user('Student', setup=setup)
    _mark(factory, setup, student, LECTURE_DATE)
    factory.insert(
        'lecture_sessions', timetable_id=setup['timetable_id'], session_date=LECTURE_DATE, status='cancelled',
        source='admin', cancel_reason='institution',
    )
    report = backfill_sessions(db)
    cancelled = [i for i in report.anomalies['cancelled_session'] if i['timetable_id'] == setup['timetable_id']]
    assert len(cancelled) == 1 and report.skipped_rows >= 1
    assert len(_unlinked(factory, setup['timetable_id'])) == 1
    assert [r['status'] for r in _sessions(factory, setup['timetable_id'])] == ['cancelled']


def test_0008_refuses_unlinked_marks_and_runs_once_they_are_linked(db, factory, history, test_database):
    setup, _, _ = history
    assert _revision(factory) == BEFORE_NOT_NULL
    db.rollback()
    with pytest.raises(SystemExit):              # Flask-Migrate turns the revision's RuntimeError into exit 1
        migrate(test_database.name, 'upgrade', 'head')
    assert _revision(factory) == BEFORE_NOT_NULL
    assert factory.query("SELECT 1 FROM information_schema.VIEWS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance_summary'")
    backfill_sessions(db)
    assert _unlinked(factory, setup['timetable_id']) == []
    db.rollback()
    migrate(test_database.name, 'upgrade', 'head')
    try:
        assert _revision(factory) == head_revision()
        [column] = factory.query(
            "SELECT IS_NULLABLE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'session_id'"
        )
        assert column['IS_NULLABLE'] == 'NO'
        assert factory.query("SELECT TABLE_NAME FROM information_schema.VIEWS WHERE TABLE_SCHEMA = DATABASE() "
                             "AND TABLE_NAME IN ('attendance_summary', 'student_overall_attendance')") == []
        assert len(_sessions(factory, setup['timetable_id'])) == 2   # the backfilled rows survive
    finally:
        db.rollback()
        migrate(test_database.name, 'downgrade', BEFORE_NOT_NULL)
    assert _revision(factory) == BEFORE_NOT_NULL


def test_backfill_cli_runs_on_a_database_at_0007(app, db, factory, history):
    setup, _, _ = history
    assert _revision(factory) == BEFORE_NOT_NULL
    result = app.test_cli_runner().invoke(args=['attendance', 'backfill-sessions', '--dry-run'])
    assert result.exit_code == 0, result.output
    assert 'Sessions to create:' in result.output and 'Dry run: nothing was written.' in result.output
    assert _sessions(factory, setup['timetable_id']) == []
    result = app.test_cli_runner().invoke(args=['attendance', 'backfill-sessions'])
    assert result.exit_code == 0, result.output
    assert 'Sessions created:' in result.output
    assert len(_sessions(factory, setup['timetable_id'])) == 2
