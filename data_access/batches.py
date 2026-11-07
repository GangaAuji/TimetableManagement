"""Course-batch SQL for the academic screen. Callers pass a cursor."""


def fetch_batches(cursor):
    """Return batches with their course and academic year."""
    cursor.execute("""
            SELECT cb.*, c.name as course_name, c.program, c.duration_years,
                   ay.name as academic_year_name
            FROM course_batches cb
            JOIN courses c ON cb.course_id = c.id
            LEFT JOIN academic_years ay ON cb.academic_year_id = ay.id
            ORDER BY cb.start_year DESC, c.name
        """)
    return cursor.fetchall()


def insert_batch(cursor, course_id, batch_name, academic_year_id, start_year, end_year, total_students, current_semester, is_active):
    """Insert one course batch."""
    cursor.execute("""
            INSERT INTO course_batches 
            (course_id, batch_name, academic_year_id, start_year, end_year, 
             total_students, current_semester, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (course_id, batch_name, academic_year_id, start_year, end_year,
              total_students, current_semester, is_active))


def update_batch(cursor, batch_id, course_id, batch_name, academic_year_id, start_year, end_year, total_students, current_semester, is_active):
    """Update one course batch."""
    cursor.execute("""
            UPDATE course_batches 
            SET course_id = %s, batch_name = %s, academic_year_id = %s,
                start_year = %s, end_year = %s, total_students = %s,
                current_semester = %s, is_active = %s
            WHERE id = %s
        """, (course_id, batch_name, academic_year_id, start_year, end_year,
              total_students, current_semester, is_active, batch_id))


def delete_batch(cursor, batch_id):
    """Delete one course batch."""
    cursor.execute("DELETE FROM course_batches WHERE id = %s", (batch_id,))
