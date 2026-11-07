"""Department SQL for the academic screen. Callers pass a cursor."""


def fetch_department_choices(cursor):
    """Return department ids and names for admin dropdowns."""
    cursor.execute("SELECT id, name FROM departments ORDER BY name")
    return cursor.fetchall()


def fetch_departments(cursor):
    """Return departments with a course count, ordered by name."""
    cursor.execute("""
            SELECT d.*, COUNT(c.id) as course_count
            FROM departments d
            LEFT JOIN courses c ON d.id = c.department_id
            GROUP BY d.id
            ORDER BY d.name
        """)
    return cursor.fetchall()


def insert_department(cursor, name, code, description, head_of_department, is_active):
    """Insert one department."""
    cursor.execute("""
            INSERT INTO departments (name, code, description, head_of_department, is_active)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, code, description, head_of_department, is_active))


def update_department(cursor, department_id, name, code, description, head_of_department, is_active):
    """Update one department."""
    cursor.execute("""
            UPDATE departments 
            SET name = %s, code = %s, description = %s, 
                head_of_department = %s, is_active = %s
            WHERE id = %s
        """, (name, code, description, head_of_department, is_active, department_id))


def delete_department(cursor, department_id):
    """Delete one department."""
    cursor.execute("DELETE FROM departments WHERE id = %s", (department_id,))
