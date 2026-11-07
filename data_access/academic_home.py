"""Academic home SQL. Callers pass a cursor."""


def fetch_academic_home(cursor):
    """Return the seven counts, then the current year and semester."""
    cursor.execute("SELECT COUNT(*) as count FROM academic_years")
    academic_years_count = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM semesters")
    semesters_count = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM courses")
    courses_count = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM subjects")
    subjects_count = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM course_batches")
    batches_count = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM faculty_allocations")
    allocations_count = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM departments")
    departments_count = cursor.fetchone()['count']

    cursor.execute("""
            SELECT * FROM academic_years 
            WHERE is_current = TRUE 
            ORDER BY start_date DESC LIMIT 1
        """)
    current_year = cursor.fetchone()

    cursor.execute("""
            SELECT * FROM semesters 
            WHERE is_current = TRUE 
            ORDER BY start_date DESC LIMIT 1
        """)
    current_semester = cursor.fetchone()

    return (
        academic_years_count,
        semesters_count,
        courses_count,
        subjects_count,
        batches_count,
        allocations_count,
        departments_count,
        current_year,
        current_semester,
    )
