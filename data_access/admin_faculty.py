"""Admin faculty SQL. Callers pass a cursor."""


def fetch_departments(cursor):
    """Return departments ordered by name."""
    cursor.execute("SELECT id, name FROM departments ORDER BY name")
    return cursor.fetchall()


def fetch_faculty_totals(cursor, query, params=None):
    """Return one faculty count."""
    if params is None:
        cursor.execute(query)
    else:
        cursor.execute(query, params)
    return cursor.fetchone()['total']


def fetch_username(cursor, username):
    """Return a user id when the username exists. The value is a list."""
    cursor.execute("SELECT id FROM users WHERE username = %s", [username])
    return cursor.fetchone()


def fetch_faculty_email(cursor, email):
    """Return a faculty id when the email exists. The value is a list."""
    cursor.execute("SELECT id FROM faculty WHERE email = %s", [email])
    return cursor.fetchone()


def insert_teacher_user(cursor, username, hashed_password):
    """Insert a teacher login."""
    cursor.execute(
        "INSERT INTO users (username, password, role) VALUES (%s, %s, 'Teacher')",
        (username, hashed_password),
    )
    return cursor.lastrowid


def insert_faculty_profile(cursor, values):
    """Insert one faculty profile. The faculty id matches the user id."""
    cursor.execute(
        """INSERT INTO faculty (id, user_id, name, email, department_id, employee_id, phone, designation, is_active) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        values,
    )


def fetch_faculty_form(cursor, faculty_id):
    """Return one faculty form row. The id is a list."""
    cursor.execute("""
        SELECT f.name, f.email, f.department_id, u.username, f.phone, 
               f.employee_id, f.designation, f.is_active
        FROM faculty f 
        LEFT JOIN users u ON f.user_id = u.id 
        WHERE f.id = %s
    """, [faculty_id])
    return cursor.fetchone()


def update_faculty_profile(cursor, values):
    """Update one faculty profile."""
    cursor.execute(
        """UPDATE faculty 
               SET name=%s, email=%s, department_id=%s, phone=%s, designation=%s, is_active=%s 
               WHERE id=%s""",
        values,
    )


def fetch_faculty_user_id(cursor, faculty_id):
    """Return the user id for a faculty table id. The id is a list."""
    cursor.execute("SELECT user_id FROM faculty WHERE id = %s", [faculty_id])
    return cursor.fetchone()


def update_user_password(cursor, hashed_password, user_id):
    """Store a password on a user row."""
    cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_password, user_id))


def fetch_faculty_user_ids(cursor, faculty_ids):
    """Return user ids for the selected faculty rows."""
    format_strings = ','.join(['%s'] * len(faculty_ids))
    cursor.execute(
        f"SELECT user_id FROM faculty WHERE id IN ({format_strings})",
        tuple(faculty_ids),
    )
    return cursor.fetchall()


def deactivate_faculty(cursor, faculty_ids):
    """Soft-delete the selected faculty rows."""
    format_strings = ','.join(['%s'] * len(faculty_ids))
    cursor.execute(
        f"UPDATE faculty SET is_active = 0 WHERE id IN ({format_strings})",
        tuple(faculty_ids),
    )


def deactivate_faculty_users(cursor, user_ids):
    """Soft-delete linked users, leaving Super Admin untouched."""
    user_format_strings = ','.join(['%s'] * len(user_ids))
    cursor.execute(
        f"UPDATE users SET status = 'inactive' WHERE id IN ({user_format_strings}) AND role != 'Super Admin'",
        tuple(user_ids),
    )


def fetch_faculty_name(cursor, faculty_id):
    """Return a faculty name and email. The id is a list."""
    cursor.execute("SELECT name, email FROM faculty WHERE id = %s", [faculty_id])
    return cursor.fetchone()


def fetch_timetable_with_rooms(cursor, faculty_user_id):
    """Return a faculty user's timetable, including the room. The id is a list."""
    cursor.execute(
        """
            SELECT t.id, t.day_of_week, t.start_time, t.end_time, s.name AS subject_name, c.name AS class_name, d.name AS division_name, r.room_number
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            JOIN divisions d ON t.division_id = d.id
            LEFT JOIN rooms r ON t.room_id = r.id
            WHERE t.faculty_id = %s
            ORDER BY FIELD(t.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'), t.start_time
            """,
        [faculty_user_id],
    )
    return cursor.fetchall()


def fetch_timetable_without_rooms(cursor, faculty_user_id):
    """Return a faculty user's timetable without the room. The id is a list."""
    cursor.execute(
        """
            SELECT t.id, t.day_of_week, t.start_time, t.end_time, s.name AS subject_name, c.name AS class_name, d.name AS division_name
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            JOIN divisions d ON t.division_id = d.id
            WHERE t.faculty_id = %s
            ORDER BY FIELD(t.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'), t.start_time
            """,
        [faculty_user_id],
    )
    return cursor.fetchall()


def fetch_download_with_rooms(cursor, faculty_user_id):
    """Return download rows including the room. The id is a list."""
    cursor.execute(
        """
            SELECT t.day_of_week, t.start_time, t.end_time, s.name AS subject_name, c.name AS class_name, d.name AS division_name, r.room_number
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            JOIN divisions d ON t.division_id = d.id
            LEFT JOIN rooms r ON t.room_id = r.id
            WHERE t.faculty_id = %s
            ORDER BY FIELD(t.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'), t.start_time
            """,
        [faculty_user_id],
    )
    return cursor.fetchall()


def fetch_download_without_rooms(cursor, faculty_user_id):
    """Return download rows without the room. The id is a list."""
    cursor.execute(
        """
            SELECT t.day_of_week, t.start_time, t.end_time, s.name AS subject_name, c.name AS class_name, d.name AS division_name
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            JOIN divisions d ON t.division_id = d.id
            WHERE t.faculty_id = %s
            ORDER BY FIELD(t.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'), t.start_time
            """,
        [faculty_user_id],
    )
    return cursor.fetchall()


def fetch_faculty_name_user(cursor, faculty_id):
    """Return a faculty name and user id. The id is a list."""
    cursor.execute("SELECT name, user_id FROM faculty WHERE id = %s", [faculty_id])
    return cursor.fetchone()


def delete_faculty_availability(cursor, faculty_user_id):
    """Remove availability rows for one faculty user. The id is a list."""
    cursor.execute("DELETE FROM faculty_availability WHERE faculty_id = %s", [faculty_user_id])


def insert_availability_slot(cursor, values):
    """Insert one availability slot that may name a shift."""
    cursor.execute(
        """
                            INSERT INTO faculty_availability 
                            (faculty_id, day_of_week, shift_pattern_id, is_available, start_time, end_time, notes)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """,
        values,
    )


def insert_unavailable_day(cursor, faculty_user_id, day_num):
    """Insert an unavailable day with no times."""
    cursor.execute(
        """
                            INSERT INTO faculty_availability 
                            (faculty_id, day_of_week, is_available, start_time, end_time, notes)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
        (faculty_user_id, day_num, 0, None, None, ''),
    )


def fetch_availability_slots(cursor, faculty_user_id):
    """Return stored availability slots. The id is a list."""
    cursor.execute("""
        SELECT day_of_week, is_available, start_time, end_time, notes, shift_pattern_id
        FROM faculty_availability
        WHERE faculty_id = %s
        ORDER BY day_of_week, start_time
    """, [faculty_user_id])
    return cursor.fetchall()


def fetch_active_shift_patterns(cursor):
    """Return active shift patterns."""
    cursor.execute("SELECT id, shift_name, start_time, end_time FROM shift_patterns WHERE is_active = TRUE ORDER BY shift_order")
    return cursor.fetchall()


def fetch_availability_with_shifts(cursor, faculty_user_id):
    """Return availability joined to shift patterns. The id is a list."""
    cursor.execute(
        """SELECT fa.day_of_week, fa.is_available, fa.shift_pattern_id, fa.notes,
                  fa.start_time, fa.end_time,
                  sp.shift_name, sp.start_time as sp_start, sp.end_time as sp_end
           FROM faculty_availability fa
           LEFT JOIN shift_patterns sp ON fa.shift_pattern_id = sp.id
           WHERE fa.faculty_id = %s
           ORDER BY fa.day_of_week, fa.start_time""",
        [faculty_user_id],
    )
    return cursor.fetchall()


def fetch_absences(cursor, faculty_id):
    """Return absences for a faculty table id. The id is a list."""
    cursor.execute(
        "SELECT id, absence_date, reason, status FROM faculty_absences WHERE faculty_id = %s ORDER BY absence_date DESC",
        [faculty_id],
    )
    return cursor.fetchall()


def insert_processed_absence(cursor, faculty_id, absence_date, reason):
    """Insert an admin absence with status PROCESSED."""
    cursor.execute(
        "INSERT INTO faculty_absences (faculty_id, absence_date, reason, status) VALUES (%s, %s, %s, 'PROCESSED')",
        (faculty_id, absence_date, reason),
    )


def fetch_absence_status(cursor, absence_id, faculty_id):
    """Return an absence status row."""
    cursor.execute(
        "SELECT status FROM faculty_absences WHERE id = %s AND faculty_id = %s",
        (absence_id, faculty_id),
    )
    return cursor.fetchone()


def delete_absence(cursor, absence_id, faculty_id):
    """Delete one absence."""
    cursor.execute("DELETE FROM faculty_absences WHERE id = %s AND faculty_id = %s", (absence_id, faculty_id))


def fetch_absence_for_approval(cursor, absence_id, faculty_id):
    """Return an absence date and status."""
    cursor.execute(
        "SELECT absence_date, status FROM faculty_absences WHERE id = %s AND faculty_id = %s",
        (absence_id, faculty_id),
    )
    return cursor.fetchone()


def mark_absence_processed(cursor, absence_id, faculty_id):
    """Mark an absence processed."""
    cursor.execute(
        "UPDATE faculty_absences SET status = 'PROCESSED' WHERE id = %s AND faculty_id = %s",
        (absence_id, faculty_id),
    )


def reject_absence(cursor, absence_id, faculty_id):
    """Reject an absence that is not already processed."""
    cursor.execute(
        "UPDATE faculty_absences SET status = 'REJECTED' WHERE id = %s AND faculty_id = %s AND status != 'PROCESSED'",
        (absence_id, faculty_id),
    )


def fetch_faculty_proxy_rows(cursor, faculty_id):
    """Return proxy rows matched on the faculty table id."""
    cursor.execute(
        """
        SELECT p.id, p.absence_date, p.status, p.approval_status, t.day_of_week, t.start_time, t.end_time, 
               s.id AS subject_id, s.name AS subject_name,
               ofc.id AS original_id, ofc.name AS original_name, 
               pfc.id AS proxy_id, pfc.name AS proxy_name
        FROM proxy_log p
        JOIN timetable t ON p.timetable_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        JOIN faculty ofc ON ofc.user_id = p.original_faculty_id
        LEFT JOIN faculty pfc ON pfc.user_id = p.proxy_faculty_id
        WHERE ofc.id = %s OR pfc.id = %s
        ORDER BY p.absence_date DESC, t.start_time
        """,
        (faculty_id, faculty_id),
    )
    return cursor.fetchall()


def fetch_owned_proxy(cursor, proxy_id, faculty_user_id):
    """Return a proxy row owned by this faculty user."""
    cursor.execute(
        """
        SELECT p.timetable_id, p.proxy_faculty_id, p.approval_status, t.day_of_week, t.start_time, t.end_time, t.subject_id
        FROM proxy_log p
        JOIN timetable t ON p.timetable_id = t.id
        WHERE p.id = %s AND (p.original_faculty_id = %s OR p.proxy_faculty_id = %s)
        """,
        (proxy_id, faculty_user_id, faculty_user_id),
    )
    return cursor.fetchone()


def fetch_proxy_candidates(cursor, subject_id, faculty_user_id):
    """Return other faculty allocated to a subject."""
    cursor.execute(
        "SELECT faculty_id FROM faculty_allocations WHERE subject_id = %s AND faculty_id != %s",
        (subject_id, faculty_user_id),
    )
    return cursor.fetchall()


def approve_proxy_log(cursor, final_status, proxy_faculty_id, approved_by, proxy_id):
    """Approve a proxy row."""
    cursor.execute(
        """
        UPDATE proxy_log 
        SET approval_status = 'APPROVED', 
            status = %s, 
            proxy_faculty_id = %s,
            approval_date = NOW(),
            approved_by = %s
        WHERE id = %s
        """,
        (final_status, proxy_faculty_id, approved_by, proxy_id),
    )


def reject_proxy_log(cursor, approved_by, proxy_id, faculty_user_id):
    """Reject a proxy row owned by this faculty user."""
    cursor.execute(
        """
        UPDATE proxy_log 
        SET approval_status = 'REJECTED',
            status = 'REJECTED',
            approval_date = NOW(),
            approved_by = %s
        WHERE id = %s AND (original_faculty_id = %s OR proxy_faculty_id = %s)
        """,
        (approved_by, proxy_id, faculty_user_id, faculty_user_id),
    )
