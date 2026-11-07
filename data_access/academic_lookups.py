"""Dropdown lookup SQL for the academic screens. Callers pass a cursor."""


def fetch_courses_by_department(cursor, department_id):
    """Return active courses in one department."""
    cursor.execute("""
            SELECT id, name, code, program 
            FROM courses 
            WHERE department_id = %s AND is_active = TRUE 
            ORDER BY name
        """, (department_id,))
    return cursor.fetchall()


def fetch_subjects_by_course(cursor, course_id):
    """Return subjects in one course."""
    cursor.execute("""
            SELECT id, name, course_code, credits, course_type 
            FROM subjects 
            WHERE course_id = %s 
            ORDER BY name
        """, (course_id,))
    return cursor.fetchall()


def fetch_faculty_by_department(cursor, department_id):
    """Return active faculty in one department."""
    cursor.execute("""
            SELECT id, name, email, designation 
            FROM faculty 
            WHERE department_id = %s AND is_active = TRUE 
            ORDER BY name
        """, (department_id,))
    return cursor.fetchall()


def fetch_semesters_by_year(cursor, academic_year_id):
    """Return semesters in one academic year."""
    cursor.execute("""
            SELECT id, semester_number, semester_name, is_current 
            FROM semesters 
            WHERE academic_year_id = %s 
            ORDER BY semester_number
        """, (academic_year_id,))
    return cursor.fetchall()


def fetch_batches_by_course(cursor, course_id):
    """Return active batches in one course."""
    cursor.execute("""
            SELECT id, batch_name, start_year, end_year, current_semester 
            FROM course_batches 
            WHERE course_id = %s AND is_active = TRUE 
            ORDER BY start_year DESC
        """, (course_id,))
    return cursor.fetchall()
