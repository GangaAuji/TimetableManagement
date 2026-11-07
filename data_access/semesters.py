"""Semester SQL. Callers pass a cursor; this module does not read the request."""


def fetch_semesters(cursor):
    """Return semesters with their year and class names."""
    cursor.execute("""
            SELECT s.*, ay.name as academic_year_name, c.name as class_name
            FROM semesters s
            JOIN academic_years ay ON s.academic_year_id = ay.id
            LEFT JOIN classes c ON s.class_id = c.id
            ORDER BY s.semester_number
        """)
    return cursor.fetchall()


def fetch_classes(cursor):
    """Return classes in display order."""
    cursor.execute("SELECT * FROM classes ORDER BY display_order, name")
    return cursor.fetchall()


def insert_semester(cursor, academic_year_id, semester_number, semester_name, start_date, end_date, class_id, is_current, min_credits, max_credits):
    """Insert one semester."""
    cursor.execute("""
            INSERT INTO semesters 
            (academic_year_id, semester_number, semester_name, start_date, end_date, 
             class_id, is_current, min_credits, max_credits)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (academic_year_id, semester_number, semester_name, start_date, end_date,
              class_id, is_current, min_credits, max_credits))


def update_semester(cursor, semester_id, academic_year_id, semester_number, semester_name, start_date, end_date, class_id, is_current, min_credits, max_credits):
    """Update one semester."""
    cursor.execute("""
            UPDATE semesters 
            SET academic_year_id = %s, semester_number = %s, semester_name = %s,
                start_date = %s, end_date = %s, class_id = %s, is_current = %s,
                min_credits = %s, max_credits = %s
            WHERE id = %s
        """, (academic_year_id, semester_number, semester_name, start_date, end_date,
              class_id, is_current, min_credits, max_credits, semester_id))


def delete_semester(cursor, semester_id):
    """Delete one semester."""
    cursor.execute("DELETE FROM semesters WHERE id = %s", (semester_id,))
