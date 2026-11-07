"""Admin room SQL. Callers pass a cursor."""


def fetch_rooms(cursor):
    """Return rooms with their department names."""
    cursor.execute("""
        SELECT r.id, r.room_number, r.room_type, r.capacity, r.department_id,
               d.name AS department_name
        FROM rooms r
        LEFT JOIN departments d ON r.department_id = d.id
        ORDER BY r.room_type, r.room_number
    """)
    return cursor.fetchall()


def fetch_room(cursor, room_id):
    """Return one room row."""
    cursor.execute("""
        SELECT id, room_number, room_type, capacity, department_id
        FROM rooms WHERE id = %s
    """, (room_id,))
    return cursor.fetchone()


def fetch_room_number(cursor, room_number):
    """Return a row when the room number is taken."""
    cursor.execute("SELECT 1 FROM rooms WHERE room_number = %s", (room_number,))
    return cursor.fetchone()


def fetch_other_room_number(cursor, room_number, room_id):
    """Return a row when another room already uses this number."""
    cursor.execute("SELECT 1 FROM rooms WHERE room_number = %s AND id != %s", (room_number, room_id))
    return cursor.fetchone()


def insert_room(cursor, room_number, room_type, capacity, department_id):
    """Insert one room."""
    cursor.execute(
        "INSERT INTO rooms (room_number, room_type, capacity, department_id) VALUES (%s, %s, %s, %s)",
        (room_number, room_type, capacity, department_id),
    )


def update_room_row(cursor, room_number, room_type, capacity, department_id, room_id):
    """Update one room."""
    cursor.execute(
        "UPDATE rooms SET room_number = %s, room_type = %s, capacity = %s, department_id = %s WHERE id = %s",
        (room_number, room_type, capacity, department_id, room_id),
    )


def fetch_room_timetable_use(cursor, room_id):
    """Return a row when the room is used by the timetable."""
    cursor.execute("SELECT 1 FROM timetable WHERE room_id = %s LIMIT 1", (room_id,))
    return cursor.fetchone()


def delete_room_row(cursor, room_id):
    """Delete one room."""
    cursor.execute("DELETE FROM rooms WHERE id = %s", (room_id,))


def fetch_room_schedule(cursor, room_id):
    """Return the slots assigned to a room."""
    cursor.execute("""
            SELECT t.day_of_week, t.start_time, t.end_time,
                   s.name AS subject_name,
                   c.name AS class_name,
                   d.name AS division_name,
                   f.name AS faculty_name
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            JOIN divisions d ON t.division_id = d.id
            LEFT JOIN faculty f ON t.faculty_id = f.id
            WHERE t.room_id = %s
            ORDER BY FIELD(t.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'),
                     t.start_time
        """, (room_id,))
    return cursor.fetchall()


def fetch_room_utilization(cursor):
    """Return timetable rows that have a room."""
    cursor.execute(
        """
                SELECT 
                    COALESCE(r.room_number, '') AS room_number,
                    t.day_of_week,
                    t.start_time,
                    t.end_time,
                    co.name AS course_name,
                    cl.name AS class_name,
                    dv.name AS division_name,
                    s.name AS subject_name,
                    COALESCE(f.name, '') AS faculty_name
                FROM timetable t
                LEFT JOIN rooms r ON t.room_id = r.id
                JOIN subjects s ON s.id = t.subject_id
                JOIN courses co ON co.id = t.course_id
                JOIN classes cl ON cl.id = t.class_id
                JOIN divisions dv ON dv.id = t.division_id
                LEFT JOIN faculty f ON f.user_id = t.faculty_id
                WHERE t.room_id IS NOT NULL
                ORDER BY r.room_number, FIELD(t.day_of_week,'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'), t.start_time
                """
    )
    return cursor.fetchall()
