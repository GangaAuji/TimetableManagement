"""Admin timetable SQL. Callers pass a cursor."""


def fetch_courses(cursor, ordered=False):
    """Return courses. The generate page does not sort them."""
    if ordered:
        cursor.execute("SELECT id, name FROM courses ORDER BY name")
    else:
        cursor.execute("SELECT id, name FROM courses")
    return cursor.fetchall()


def fetch_classes(cursor, ordered=False):
    """Return classes. The generate page does not sort them."""
    if ordered:
        cursor.execute("SELECT id, name FROM classes ORDER BY name")
    else:
        cursor.execute("SELECT id, name FROM classes")
    return cursor.fetchall()


def fetch_divisions(cursor, ordered=False):
    """Return divisions. The generate page does not sort them."""
    if ordered:
        cursor.execute("SELECT id, name FROM divisions ORDER BY name")
    else:
        cursor.execute("SELECT id, name FROM divisions")
    return cursor.fetchall()


def fetch_course_program(cursor, course_id):
    """Return the program row for one course."""
    cursor.execute("SELECT program FROM courses WHERE id = %s", (course_id,))
    return cursor.fetchone()


def fetch_allocated_faculty(cursor, class_id, division_id, subject_id):
    """Return one faculty allocation for a class subject."""
    cursor.execute(
        """
                    SELECT fa.faculty_id FROM faculty_allocations fa
                    WHERE fa.class_id = %s AND fa.division_id = %s 
                      AND fa.subject_id = %s
                    LIMIT 1
                    """,
        (class_id, division_id, subject_id)
    )
    return cursor.fetchone()


def fetch_class_overlap(cursor, course_id, class_id, division_id, day, start_time, end_time):
    """Return a row when the class already has a session at this time."""
    cursor.execute(
        """
                SELECT 1 FROM timetable
                WHERE course_id = %s AND class_id = %s AND division_id = %s AND day_of_week = %s
                                    AND COALESCE(is_active, 1) = 1
                  AND NOT (end_time <= %s OR start_time >= %s)
                LIMIT 1
                """,
        (course_id, class_id, division_id, day, start_time, end_time),
    )
    return cursor.fetchone()


def fetch_faculty_overlap(cursor, faculty_id, day, start_time, end_time):
    """Return a row when the faculty user is already teaching at this time."""
    cursor.execute(
        """
                    SELECT 1 FROM timetable
                    WHERE faculty_id = %s AND day_of_week = %s
                                            AND COALESCE(is_active, 1) = 1
                      AND NOT (end_time <= %s OR start_time >= %s)
                    LIMIT 1
                    """,
        (faculty_id, day, start_time, end_time),
    )
    return cursor.fetchone()


def insert_timetable_session(cursor, values):
    """Insert one timetable session."""
    cursor.execute(
        """
                INSERT INTO timetable (course_id, class_id, division_id, subject_id, faculty_id, day_of_week, start_time, end_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
        values,
    )


def deactivate_timetable_session(cursor, timetable_id):
    """Hide one active timetable session. The id is passed as a list."""
    cursor.execute(
        "UPDATE timetable SET is_active = 0 WHERE id = %s AND COALESCE(is_active, 1) = 1",
        [timetable_id],
    )


def delete_timetable_session(cursor, timetable_id):
    """Delete one timetable session. The id is passed as a list."""
    cursor.execute("DELETE FROM timetable WHERE id = %s", [timetable_id])


def fetch_session_for_room(cursor, timetable_id):
    """Return the session row used while assigning a room."""
    cursor.execute("""
                SELECT t.day_of_week, t.start_time, t.end_time, s.theory_practical,
                       (SELECT COUNT(*) FROM students WHERE course_id = t.course_id AND class_id = t.class_id AND division_id = t.division_id) as student_count
                FROM timetable t
                JOIN subjects s ON t.subject_id = s.id
                WHERE t.id = %s AND COALESCE(t.is_active, 1) = 1
            """, (timetable_id,))
    return cursor.fetchone()


def fetch_room_type(cursor, room_id):
    """Return a room type and capacity row."""
    cursor.execute("SELECT room_type, capacity FROM rooms WHERE id = %s", (room_id,))
    return cursor.fetchone()


def fetch_room_conflicts(cursor, room_id, day, timetable_id, start_time, end_time):
    """Return sessions that already use this room at this time."""
    cursor.execute("""
                SELECT t.id, c.name AS class_name, d.name AS division_name, s.name AS subject_name, t.start_time, t.end_time
                FROM timetable t
                JOIN classes c ON t.class_id = c.id
                JOIN divisions d ON t.division_id = d.id
                JOIN subjects s ON t.subject_id = s.id
                                WHERE t.room_id = %s
                                    AND COALESCE(t.is_active, 1) = 1
                  AND t.day_of_week = %s
                  AND t.id != %s
                  AND NOT (t.end_time <= %s OR t.start_time >= %s)
            """, (room_id, day, timetable_id, start_time, end_time))
    return cursor.fetchall()


def assign_timetable_room(cursor, room_id, timetable_id):
    """Store a room on one active session."""
    cursor.execute(
        "UPDATE timetable SET room_id = %s WHERE id = %s AND COALESCE(is_active, 1) = 1",
        (room_id, timetable_id),
    )


def fetch_timetable_with_rooms(cursor, course_id, class_id, division_id):
    """Return timetable rows including the room number."""
    cursor.execute(
        """
                SELECT t.id, t.day_of_week, t.start_time, t.end_time,
                       s.id AS subject_id, s.name AS subject_name,
                       t.faculty_id AS faculty_user_id, COALESCE(f.name,'') AS faculty_name,
                       r.room_number
                FROM timetable t
                JOIN subjects s ON s.id = t.subject_id
                LEFT JOIN faculty f ON f.user_id = t.faculty_id
                LEFT JOIN rooms r ON t.room_id = r.id
                                WHERE t.course_id = %s AND t.class_id = %s AND t.division_id = %s
                                    AND COALESCE(t.is_active, 1) = 1
                ORDER BY FIELD(t.day_of_week,'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'), t.start_time
                """,
        (course_id, class_id, division_id),
    )
    return cursor.fetchall()


def fetch_timetable_without_rooms(cursor, course_id, class_id, division_id):
    """Return timetable rows when the room column is unavailable."""
    cursor.execute(
        """
                SELECT t.id, t.day_of_week, t.start_time, t.end_time,
                       s.id AS subject_id, s.name AS subject_name,
                       t.faculty_id AS faculty_user_id, COALESCE(f.name,'') AS faculty_name
                FROM timetable t
                JOIN subjects s ON s.id = t.subject_id
                LEFT JOIN faculty f ON f.user_id = t.faculty_id
                                WHERE t.course_id = %s AND t.class_id = %s AND t.division_id = %s
                                    AND COALESCE(t.is_active, 1) = 1
                ORDER BY FIELD(t.day_of_week,'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'), t.start_time
                """,
        (course_id, class_id, division_id),
    )
    return cursor.fetchall()


def fetch_rooms(cursor):
    """Return rooms for the assignment list."""
    cursor.execute("SELECT id, room_number, room_type, capacity FROM rooms ORDER BY room_type, room_number")
    return cursor.fetchall()


def fetch_subject_choices(cursor, course_id, class_id):
    """Return subjects that can be added to this class."""
    cursor.execute(
        """
            SELECT id, name FROM subjects
            WHERE course_id = %s AND (class_id IS NULL OR class_id = %s)
            ORDER BY name
            """,
        (course_id, class_id),
    )
    return cursor.fetchall()
