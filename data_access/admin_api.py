"""Admin JSON lookup SQL. Callers pass a cursor."""


def fetch_classes(cursor):
    """Return every class."""
    cursor.execute("SELECT id, name FROM classes ORDER BY display_order, name")
    return cursor.fetchall()


def fetch_divisions(cursor):
    """Return every division."""
    cursor.execute("SELECT id, name FROM divisions ORDER BY name")
    return cursor.fetchall()


def fetch_faculty_for_subject(cursor, subject_id):
    """Return active faculty allocated to a subject. faculty_id is a user id."""
    cursor.execute("""
            SELECT f.user_id, f.name, fa.is_primary
            FROM faculty_allocations fa
            JOIN faculty f ON fa.faculty_id = f.user_id
            WHERE fa.subject_id = %s AND f.is_active = 1
            ORDER BY fa.is_primary DESC, f.name
        """, (subject_id,))
    return cursor.fetchall()


def fetch_eligible_subjects(cursor, course_id, class_id, division_id):
    """Return subjects that have a matching allocation."""
    cursor.execute(
        """
            SELECT DISTINCT
                s.id,
                s.name,
                s.course_code,
                s.theory_practical,
                COALESCE(s.lectures_per_week, 0) AS lectures_per_week,
                COALESCE(s.practical_hours_per_week, 0) AS practical_hours_per_week
            FROM subjects s
            JOIN faculty_allocations fa ON fa.subject_id = s.id
            WHERE s.course_id = %s
              AND (fa.class_id IS NULL OR fa.class_id = %s)
              AND (fa.division_id IS NULL OR fa.division_id = %s)
            ORDER BY s.name
            """,
        (course_id, class_id, division_id),
    )
    return cursor.fetchall()


def fetch_allocation_faculty(cursor, subject_ids, class_id, division_id):
    """Return faculty names for the eligible subjects."""
    placeholder = ','.join(['%s'] * len(subject_ids))
    cursor.execute(
        f"""
                SELECT fa.subject_id, f.name AS faculty_name, COALESCE(fa.is_primary, 1) AS is_primary
                FROM faculty_allocations fa
                JOIN faculty f ON f.user_id = fa.faculty_id
                WHERE fa.subject_id IN ({placeholder})
                  AND (fa.class_id IS NULL OR fa.class_id = %s)
                  AND (fa.division_id IS NULL OR fa.division_id = %s)
                ORDER BY fa.subject_id, is_primary DESC, f.name
                """,
        (*subject_ids, class_id, division_id),
    )
    return cursor.fetchall()


def fetch_course_subjects(cursor, course_id, class_id):
    """Return subjects for a course and class."""
    cursor.execute(
        """
            SELECT s.id, s.name, s.course_code
            FROM subjects s
            WHERE s.course_id = %s
              AND (s.class_id IS NULL OR s.class_id = %s)
            ORDER BY s.name
            """,
        (course_id, class_id),
    )
    return cursor.fetchall()


def fetch_coverage_subjects(cursor, course_id, class_id):
    """Return subject hour requirements."""
    cursor.execute(
        """
            SELECT s.id, s.name, 
                   COALESCE(s.lectures_per_week,0) AS lpw, 
                   COALESCE(s.practical_hours_per_week,0) AS phw
            FROM subjects s
            WHERE s.course_id = %s AND (s.class_id IS NULL OR s.class_id = %s)
            ORDER BY s.name
            """,
        (course_id, class_id),
    )
    return cursor.fetchall()


def fetch_scheduled_counts(cursor, course_id, class_id, division_id, subject_ids):
    """Return scheduled timetable counts for the given subjects."""
    placeholder = ','.join(['%s'] * len(subject_ids))
    cursor.execute(
        f"""
                SELECT subject_id, COUNT(*) AS cnt
                FROM timetable
                WHERE course_id = %s AND class_id = %s AND division_id = %s 
                  AND subject_id IN ({placeholder})
                GROUP BY subject_id
                """,
        (int(course_id), int(class_id), int(division_id), *subject_ids),
    )
    return cursor.fetchall()


def fetch_quality_samples(cursor):
    """Return quality-candidate counts."""
    cursor.execute(
        """
                SELECT
                    COUNT(*) AS total_samples,
                    SUM(CASE WHEN is_selected = 1 THEN 1 ELSE 0 END) AS accepted_samples,
                    SUM(CASE WHEN is_selected = 0 THEN 1 ELSE 0 END) AS rejected_samples
                FROM timetable_quality_candidates
                """
    )
    return cursor.fetchone()


def fetch_latest_quality_run(cursor):
    """Return the latest quality run."""
    cursor.execute(
        """
                SELECT created_at, quality_score
                FROM timetable_quality_runs
                ORDER BY created_at DESC
                LIMIT 1
                """
    )
    return cursor.fetchone()
