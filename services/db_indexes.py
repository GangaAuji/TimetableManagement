"""Add the composite indexes the page queries actually filter and sort by.

Runs once in the background after the app starts serving. Existing indexes are left in place.
A missing table is skipped, so jobs tables created later are indexed on the next start.
"""

import logging
import re

from extensions import get_db_connection

logger = logging.getLogger(__name__)

_NAME = re.compile(r'^[A-Za-z0-9_]+$')
# (table, index name, columns in filter order, then sort order)
_INDEXES = (
    ('timetable', 'idx_timetable_class_view', ('course_id', 'class_id', 'division_id', 'is_active', 'day_of_week', 'start_time')),
    ('timetable', 'idx_timetable_faculty_slot', ('faculty_id', 'is_active', 'day_of_week', 'start_time')),
    ('timetable', 'idx_timetable_room_slot', ('room_id', 'is_active', 'day_of_week', 'start_time')),
    ('faculty_allocations', 'idx_allocation_subject_group', ('subject_id', 'class_id', 'division_id')),
    ('students', 'idx_student_group', ('course_id', 'class_id', 'division_id')),
    ('subjects', 'idx_subject_course_class', ('course_id', 'class_id')),
    ('users', 'idx_users_role_name', ('role', 'username')),
    ('registration_invitations', 'idx_invitation_status_expiry', ('status', 'expires_at')),
    ('user_sessions', 'idx_session_active_recent', ('is_active', 'last_activity')),
    ('login_attempts', 'idx_login_failed_recent', ('status', 'attempted_at')),
    ('role_permissions', 'idx_role_permissions_role', ('role_id', 'permission_id')),
    ('user_activity_log', 'idx_activity_user_time', ('user_id', 'created_at')),
    ('processed_reports', 'idx_processed_reports_queue', ('status', 'id')),
    ('processed_reports', 'idx_processed_reports_recent', ('status', 'created_at')),
    ('timetable_jobs', 'idx_timetable_jobs_queue', ('status', 'id')),
)


def ensure_indexes():
    """Create any missing composite indexes. Failures are logged and do not stop the app."""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        for table, name, columns in _INDEXES:
            if not _NAME.match(table) or not _NAME.match(name) or any(not _NAME.match(column) for column in columns):
                continue
            try:
                if not _table_exists(cursor, table) or _index_exists(cursor, table, name):
                    continue
                column_sql = ', '.join(columns)
                statement = f'ALTER TABLE `{table}` ADD INDEX `{name}` ({column_sql})'
                try:
                    cursor.execute(statement + ', ALGORITHM=INPLACE, LOCK=NONE')
                except Exception:
                    connection.rollback()
                    cursor.execute(statement)
                connection.commit()
                logger.info('Added index %s on %s', name, table)
            except Exception:
                connection.rollback()
                logger.exception('Index %s on %s was not added', name, table)
    finally:
        cursor.close()
        connection.close()


def _table_exists(cursor, table):
    cursor.execute(
        """
        SELECT 1 AS present
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        LIMIT 1
        """,
        (table,),
    )
    return cursor.fetchone() is not None


def _index_exists(cursor, table, name):
    cursor.execute(
        """
        SELECT 1 AS present
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND INDEX_NAME = %s
        LIMIT 1
        """,
        (table, name),
    )
    return cursor.fetchone() is not None
