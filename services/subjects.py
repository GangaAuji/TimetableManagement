"""Subject reads and saves for the academic screen. This module does not read the request."""

import mysql.connector

from config import Config
from data_access.subjects import (
    delete_subject,
    fetch_active_courses,
    fetch_classes_by_display_order,
    fetch_course_for_new_subject,
    fetch_course_for_subject_edit,
    fetch_semester_number,
    fetch_semesters_by_number,
    fetch_subjects,
    insert_subject,
    update_subject,
)


def _connect():
    """Open the same direct connection the academic screens use."""
    return mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB,
    )


def _to_float(value):
    """Turn a Decimal into a float and leave every other value unchanged."""
    try:
        import decimal
        if isinstance(value, decimal.Decimal):
            return float(value)
    except Exception:
        pass
    return value


def _normalize_subject_numbers(theory_practical, credits, theory_credits, practical_credits, marks, theory_marks, practical_marks):
    """Apply the theory or practical mode, then match the stored totals."""
    if theory_practical == 'Theory':
        practical_credits = 0.0
        practical_marks = 0
    elif theory_practical == 'Practical':
        theory_credits = 0.0
        theory_marks = 0
    calculated_credits = round((theory_credits + practical_credits), 1)
    if abs(credits - calculated_credits) > 0.1:
        credits = calculated_credits
    calculated_marks = theory_marks + practical_marks
    if marks != calculated_marks:
        marks = calculated_marks
    return credits, theory_credits, practical_credits, marks, theory_marks, practical_marks


def _require_new_subject_semester(cursor, course_id, semester_id):
    """Reject a new subject whose semester is past the course limit."""
    course_row = fetch_course_for_new_subject(cursor, course_id)
    if not course_row:
        raise Exception('Invalid course selected')
    if not semester_id:
        return
    semester_row = fetch_semester_number(cursor, semester_id)
    if not semester_row:
        raise Exception('Invalid semester selected')
    max_semesters = int(course_row.get('total_semesters') or 0)
    if not max_semesters:
        program = (course_row.get('program') or '').upper()
        if program == 'PG':
            max_semesters = 4
        elif program == 'UG':
            max_semesters = 6
        course_name = (course_row.get('name') or '').lower()
        if 'engineer' in course_name:
            max_semesters = max(max_semesters, 8)
    if int(semester_row['semester_number']) > max_semesters:
        raise Exception(f"Selected semester exceeds allowed semesters for the course (max {max_semesters}).")


def _require_edited_subject_semester(cursor, course_id, semester_id):
    """Reject an edited subject whose semester is past the stored course total."""
    course_row = fetch_course_for_subject_edit(cursor, course_id)
    if not course_row:
        raise Exception('Invalid course selected')
    if not semester_id:
        return
    semester_row = fetch_semester_number(cursor, semester_id)
    if not semester_row:
        raise Exception('Invalid semester selected')
    if int(semester_row['semester_number']) > int(course_row['total_semesters'] or 0):
        raise Exception(
            f"Selected semester exceeds total semesters for the course ({course_row['total_semesters']})."
        )


def list_subjects(class_id, course_id):
    """Return subjects for the filters, plus the course, class, and semester menus."""
    connection = _connect()
    cursor = connection.cursor(dictionary=True)
    try:
        subjects = fetch_subjects(cursor, class_id, course_id)
        for subject in subjects:
            for key in (
                'credits', 'theory_credits', 'practical_credits',
                'marks', 'theory_marks', 'practical_marks',
                'lectures_per_week', 'practical_hours_per_week',
            ):
                if key in subject and subject[key] is not None:
                    subject[key] = _to_float(subject[key])
        return (
            subjects,
            fetch_active_courses(cursor),
            fetch_classes_by_display_order(cursor),
            fetch_semesters_by_number(cursor),
        )
    finally:
        cursor.close()
        connection.close()


def create_subject(name, course_code, course_id, class_id, semester_id, course_type, theory_practical, credits, theory_credits, practical_credits, marks, theory_marks, practical_marks, lectures_per_week, practical_hours_per_week, is_elective, description, syllabus_url):
    """Insert a subject. Return an error string when the save fails."""
    credits, theory_credits, practical_credits, marks, theory_marks, practical_marks = _normalize_subject_numbers(
        theory_practical, credits, theory_credits, practical_credits, marks, theory_marks, practical_marks,
    )
    connection = _connect()
    cursor = connection.cursor(dictionary=True)
    try:
        _require_new_subject_semester(cursor, course_id, semester_id)
        insert_subject(cursor, (
            name, course_code, course_id, class_id, semester_id, course_type, theory_practical,
            credits, theory_credits, practical_credits, marks, theory_marks, practical_marks,
            lectures_per_week, practical_hours_per_week, is_elective, description, syllabus_url,
        ))
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()


def change_subject(subject_id, name, course_code, course_id, class_id, semester_id, course_type, theory_practical, credits, theory_credits, practical_credits, marks, theory_marks, practical_marks, lectures_per_week, practical_hours_per_week, is_elective, description, syllabus_url):
    """Update a subject. Return an error string when the save fails."""
    credits, theory_credits, practical_credits, marks, theory_marks, practical_marks = _normalize_subject_numbers(
        theory_practical, credits, theory_credits, practical_credits, marks, theory_marks, practical_marks,
    )
    connection = _connect()
    cursor = connection.cursor(dictionary=True)
    try:
        _require_edited_subject_semester(cursor, course_id, semester_id)
        update_subject(cursor, (
            name, course_code, course_id, class_id, semester_id, course_type, theory_practical,
            credits, theory_credits, practical_credits, marks, theory_marks, practical_marks,
            lectures_per_week, practical_hours_per_week, is_elective, description, syllabus_url, subject_id,
        ))
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()


def remove_subject(subject_id):
    """Delete a subject. Return an error string when the delete fails."""
    connection = _connect()
    cursor = connection.cursor()
    try:
        delete_subject(cursor, subject_id)
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()
