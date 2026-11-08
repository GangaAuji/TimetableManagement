"""Student portal SQL. Callers pass a cursor.

Attendance figures are not here: services.attendance_calc computes them. This
module only reads the student's profile and the slots they attend.
"""

# The student's slots, matching attendance_calc.roster.in_roster: same course
# and class; the student's division or a whole-class slot; an elective only
# when the student chose it for the slot's semester and year. Active slots only.
STUDENT_SLOT_FILTER = """
    t.course_id = %(course_id)s AND t.class_id = %(class_id)s
    AND (t.division_id IS NULL OR t.division_id = %(division_id)s)
    AND COALESCE(t.is_active, 1) = 1
    AND (
        COALESCE(sub.is_elective, 0) = 0
        OR EXISTS (
            SELECT 1 FROM student_subject_selections sss
            WHERE sss.student_id = %(student_id)s AND sss.subject_id = t.subject_id
              AND (sss.status IS NULL OR sss.status <> 'Withdrawn')
              AND (t.semester_id IS NULL OR sss.semester_id = t.semester_id)
              AND (t.academic_year_id IS NULL OR sss.academic_year_id = t.academic_year_id)
        )
    )
"""


def _slot_params(student):
    return {
        'student_id': student['id'],
        'course_id': student['course_id'],
        'class_id': student['class_id'],
        'division_id': student.get('division_id'),
    }


def fetch_student_profile(cursor, user_id):
    """Return the student row used by the dashboard."""
    cursor.execute("""
            SELECT s.id, s.course_id, s.class_id, s.division_id, 
                   c.name as course_name, cl.name as class_name, d.name as division_name
            FROM students s
            LEFT JOIN courses c ON s.course_id = c.id
            LEFT JOIN classes cl ON s.class_id = cl.id
            LEFT JOIN divisions d ON s.division_id = d.id
            WHERE s.user_id = %s
        """, [user_id])
    return cursor.fetchone()


def fetch_today_classes(cursor, student, today):
    """Return today's classes for one student: their division's and whole-class slots, chosen electives only."""
    cursor.execute(f"""
                SELECT 
                    t.id,
                    t.start_time, 
                    t.end_time, 
                    sub.name as subject_name, 
                    f.name as faculty_name,
                    r.room_number
                FROM timetable t 
                JOIN subjects sub ON t.subject_id = sub.id 
                JOIN faculty f ON t.faculty_id = f.user_id
                LEFT JOIN rooms r ON t.room_id = r.id
                WHERE {STUDENT_SLOT_FILTER}
                AND t.day_of_week = %(today)s
                ORDER BY t.start_time
            """, {**_slot_params(student), 'today': today})
    return cursor.fetchall()


def count_weekly_classes(cursor, student):
    """Return the weekly class count row."""
    cursor.execute(f"""
            SELECT COUNT(*) as count
            FROM timetable t
            JOIN subjects sub ON t.subject_id = sub.id
            WHERE {STUDENT_SLOT_FILTER}
        """, _slot_params(student))
    return cursor.fetchone()


def fetch_student_section(cursor, user_id):
    """Return the student's id and section ids for the timetable page."""
    cursor.execute(
        "SELECT id, course_id, class_id, division_id FROM students WHERE user_id = %s",
        [user_id],
    )
    return cursor.fetchone()


def fetch_student_timetable(cursor, student):
    """Return the weekly timetable for one student."""
    cursor.execute(f"""
            SELECT 
                t.day_of_week, 
                t.start_time, 
                t.end_time, 
                sub.name as subject_name, 
                f.name as faculty_name,
                r.room_number
            FROM timetable t 
            JOIN subjects sub ON t.subject_id = sub.id 
            LEFT JOIN faculty f ON t.faculty_id = f.user_id
            LEFT JOIN rooms r ON t.room_id = r.id
            WHERE {STUDENT_SLOT_FILTER}
            ORDER BY 
                FIELD(t.day_of_week, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'), 
                t.start_time
        """, _slot_params(student))
    return cursor.fetchall()


def fetch_student_id(cursor, user_id):
    """Return the student id row."""
    cursor.execute("SELECT id FROM students WHERE user_id = %s", [user_id])
    return cursor.fetchone()
