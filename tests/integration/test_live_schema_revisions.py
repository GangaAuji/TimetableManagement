"""0003 to head on a copy of the live schema: upgrade, downgrade to 0002, and upgrade again.

The copy is built from sql/college_timetable_db.live-schema.sql, a structure-only
mysqldump of college_timetable_db taken while it was at 0003_security_schema
(see docs/DATABASE.md). Rows are not involved. The test only uses one scratch
*_test database, which it drops at the end.
"""

from pathlib import Path

import pytest

from core.schema.introspect import compare, read_schema
from core.schema.sqlfile import read_statements
from core.schema.status import head_revision
from tests.integration.live_helpers import (
    drop,
    migrate,
    recreate,
    scratch_name,
    server_connection,
    stamped,
    without_definer,
)

pytestmark = pytest.mark.live_db

LIVE_SCHEMA = Path(__file__).resolve().parents[2] / 'sql' / 'college_timetable_db.live-schema.sql'
LIVE_REVISION = '0003_security_schema'
_HEAD_CHANGES = (
    'rate_limit_counters', 'seed_history', 'failed_window_start', 'locked_until',
    'lecture_sessions', 'attendance_excuses', 'session_id', 'idx_attendance_session', 'fk_attendance_session',
    'attendance_summary', 'student_overall_attendance',
    'locked_by', 'heartbeat_at',
    'face_consents', 'face_recognition_audit',
    'notifications', 'notification_settings',
    'lab_batch_groups', 'lab_batch_members', 'lab_batch_group_id', 'idx_timetable_lab_batch', 'fk_timetable_lab_batch',
    'api_keys', 'webhook_endpoints', 'webhook_deliveries', 'sso_settings', 'sso_identities',
    'organizations', 'institutions', 'institution_memberships', 'resource_shares',
    'institution_id', 'fk_department_institution', 'fk_room_institution', 'sharing',
    'capabilities',
    'faculty_preferences', 'timetable_rules',
    'timetable_versions', 'timetable_version_cohorts', 'version_id', 'fk_timetable_version',
    'bookings',
    'academic_terms', 'calendar',
    'syllabus_units', 'lesson_logs', 'uq_syllabus_unit', 'uq_lesson_session',
    'fk_syllabus_unit_subject', 'fk_lesson_session', 'fk_lesson_unit', 'fk_lesson_recorder',
    'assessment_components', 'assessment_marks', 'course_outcomes', 'program_outcomes', 'co_po_map', 'component_co_map',
    'exams', 'exam_sessions', 'exam_session_cohorts', 'exam_session_rooms', 'exam_seats', 'invigilation_duties',
    'user_second_factors',
    'institution_scope', 'uq_branding_scope', 'fk_branding_institution', 'branding_settings.setting_key',
    'security_settings', 'password_changed_at',
)
_SESSION_OBJECTS = {'lecture_sessions', 'attendance_excuses'}
_DROPPED_VIEWS = {'attendance_summary', 'student_overall_attendance'}
_MID_TABLE_COLUMNS = ('column `users.', 'column `attendance.', 'column `timetable.', 'column `departments.', 'column `rooms.', 'column `faculty.')


def _moved_column(line):
    """0006, 0007, 0012 and 0014 add columns mid-table, which moves later columns."""
    return line.startswith(_MID_TABLE_COLUMNS) and ' position: ' in line


def _unexplained(differences, changes=_HEAD_CHANGES):
    """Lines not caused by the revisions after the baseline."""
    return [line for line in differences if not any(part in line for part in changes) and not _moved_column(line)]


def _rate_limit_collation(schema):
    return schema['tables']['rate_limit_counters']['collation']


@pytest.fixture(scope='module')
def copy():
    if not LIVE_SCHEMA.exists():
        pytest.skip(f'{LIVE_SCHEMA.name} is not in sql/.')
    connection = server_connection()
    cursor = connection.cursor()
    name = scratch_name('live_copy')
    try:
        recreate(cursor, name)
        cursor.execute(f'USE `{name}`')
        for statement in read_statements(LIVE_SCHEMA):
            cursor.execute(without_definer(statement))
        cursor.execute('INSERT INTO alembic_version (version_num) VALUES (%s)', (LIVE_REVISION,))
        cursor.execute('USE information_schema')
        yield cursor, name
    finally:
        drop(cursor, name)
        connection.close()


def test_upgrade_downgrade_upgrade_on_the_live_schema(copy):
    cursor, name = copy
    live = read_schema(cursor, name)
    assert _rate_limit_collation(live) == 'utf8mb4_general_ci'
    assert 'roles.hierarchy_level' in live['columns']

    migrate(name, 'upgrade', 'head')
    assert stamped(cursor, name) == [head_revision()]
    upgraded = read_schema(cursor, name)
    assert _rate_limit_collation(upgraded) == 'utf8mb4_unicode_ci'
    assert 'seed_history' in upgraded['tables']
    assert {'users.failed_window_start', 'users.locked_until', 'attendance.session_id'} <= set(upgraded['columns'])
    assert _SESSION_OBJECTS <= set(upgraded['tables'])
    assert not _DROPPED_VIEWS & set(upgraded['views'])
    assert upgraded['columns']['attendance.session_id']['nullable'] == 'NO'
    differences = compare(live, upgraded)
    assert differences and _unexplained(differences) == []

    migrate(name, 'downgrade', '0007_lecture_sessions')
    with_views = read_schema(cursor, name)
    assert _DROPPED_VIEWS <= set(with_views['views'])
    assert with_views['columns']['attendance.session_id']['nullable'] == 'YES'
    for view in _DROPPED_VIEWS:
        assert with_views['views'][view] == live['views'][view]
    assert _unexplained(compare(with_views, upgraded), _HEAD_CHANGES[6:]) == []
    migrate(name, 'upgrade', 'head')
    assert compare(upgraded, read_schema(cursor, name)) == []

    migrate(name, 'downgrade', '0006_sign_in_lock')
    without_sessions = read_schema(cursor, name)
    assert not _SESSION_OBJECTS & set(without_sessions['tables'])
    assert 'attendance.session_id' not in without_sessions['columns']
    assert all(
        any(part in line for part in _HEAD_CHANGES[4:]) or ' position: ' in line
        for line in compare(without_sessions, upgraded)
    )
    migrate(name, 'upgrade', 'head')
    assert compare(upgraded, read_schema(cursor, name)) == []

    migrate(name, 'downgrade', '0005_seed_history')
    without_lock = read_schema(cursor, name)
    assert not {'users.failed_window_start', 'users.locked_until'} & set(without_lock['columns'])
    assert all(
        any(part in line for part in _HEAD_CHANGES[2:]) or ' position: ' in line
        for line in compare(without_lock, upgraded)
    )
    migrate(name, 'upgrade', 'head')
    assert compare(upgraded, read_schema(cursor, name)) == []

    migrate(name, 'downgrade', '0002_catch_up')
    assert stamped(cursor, name) == ['0002_catch_up']
    down = read_schema(cursor, name)
    assert 'rate_limit_counters' not in down['tables'] and 'seed_history' not in down['tables']
    assert 'users.locked_until' not in down['columns']
    assert down['columns']['roles.hierarchy_level'] == live['columns']['roles.hierarchy_level']
    differences = compare(down, live)
    assert differences and all('rate_limit_counters' in line for line in differences)

    migrate(name, 'upgrade', 'head')
    assert compare(upgraded, read_schema(cursor, name)) == []

    migrate(name, 'downgrade', LIVE_REVISION)
    assert stamped(cursor, name) == [LIVE_REVISION]
    assert compare(live, read_schema(cursor, name)) == []
