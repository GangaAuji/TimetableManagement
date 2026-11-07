"""Pagination and admin proxy SQL. Callers pass a cursor where noted."""


def fetch_absence_lectures(cursor, faculty_id, day_of_week):
    """Return the lectures an absent faculty member has on one weekday."""
    cursor.execute(
        "SELECT id, subject_id, start_time, end_time FROM timetable WHERE faculty_id = %s AND day_of_week = %s",
        (faculty_id, day_of_week),
    )
    return cursor.fetchall()


def fetch_proxy_candidates(cursor, subject_id, absent_faculty_id):
    """Return other faculty allocated to the same subject."""
    cursor.execute(
        "SELECT faculty_id FROM faculty_allocations WHERE subject_id = %s AND faculty_id != %s",
        (subject_id, absent_faculty_id),
    )
    return cursor.fetchall()


def insert_proxy_log(cursor, values):
    """Record one approved proxy assignment."""
    cursor.execute(
        """
            INSERT INTO proxy_log (original_faculty_id, proxy_faculty_id, timetable_id, absence_date, status, approval_status, approval_date, approved_by)
            VALUES (%s, %s, %s, %s, %s, 'APPROVED', NOW(), %s)
            """,
        values,
    )
