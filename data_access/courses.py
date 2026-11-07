"""Course SQL for the academic screen. Callers pass a cursor."""


def count_active_courses(cursor):
    """Return the number of active courses."""
    cursor.execute("SELECT COUNT(*) AS count FROM courses WHERE is_active = TRUE")
    return cursor.fetchone()['count']


def fetch_courses(cursor):
    """Return courses with department, subject, and batch counts."""
    cursor.execute("""
            SELECT c.*, d.name as department_name,
                   COUNT(DISTINCT s.id) as subject_count,
                   COUNT(DISTINCT cb.id) as batch_count
            FROM courses c
            JOIN departments d ON c.department_id = d.id
            LEFT JOIN subjects s ON c.id = s.course_id
            LEFT JOIN course_batches cb ON c.id = cb.course_id
            GROUP BY c.id
            ORDER BY c.program, c.name
        """)
    return cursor.fetchall()


def fetch_active_departments(cursor):
    """Return active departments ordered by name."""
    cursor.execute("SELECT * FROM departments WHERE is_active = TRUE ORDER BY name")
    return cursor.fetchall()


def insert_course(cursor, name, code, program, department_id, duration_years, total_semesters, description, is_active):
    """Insert one course."""
    cursor.execute("""
            INSERT INTO courses 
            (name, code, program, department_id, duration_years, total_semesters, description, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (name, code, program, department_id, duration_years, total_semesters, description, is_active))


def update_course(cursor, course_id, name, code, program, department_id, duration_years, total_semesters, description, is_active):
    """Update one course."""
    cursor.execute("""
            UPDATE courses 
            SET name = %s, code = %s, program = %s, department_id = %s,
                duration_years = %s, total_semesters = %s, description = %s, is_active = %s
            WHERE id = %s
        """, (name, code, program, department_id, duration_years, total_semesters, description, is_active, course_id))


def delete_course(cursor, course_id):
    """Delete one course."""
    cursor.execute("DELETE FROM courses WHERE id = %s", (course_id,))
