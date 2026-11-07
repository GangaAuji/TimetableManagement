"""Faculty-allocation SQL for the academic screen. Callers pass a cursor."""


def fetch_allocations(cursor, class_id, faculty_id, course_id):
    """Return allocations, optionally limited by class, faculty row, and course."""
    where_conditions = []
    query_params = []
    if class_id:
        where_conditions.append("fa.class_id = %s")
        query_params.append(class_id)
    if faculty_id:
        where_conditions.append("f.id = %s")
        query_params.append(faculty_id)
    if course_id:
        where_conditions.append("s.course_id = %s")
        query_params.append(course_id)
    where_clause = ""
    if where_conditions:
        where_clause = "WHERE " + " AND ".join(where_conditions)
    # faculty_allocations.faculty_id references faculty.user_id
    cursor.execute(f"""
            SELECT fa.*, 
                   f.id as faculty_table_id,
                   f.name as faculty_name, f.department_id as faculty_dept_id,
                   s.name as subject_name, s.course_code,
                   c.name as course_name, c.program,
                   cl.name as class_name, cl.display_order as class_order,
                   d.name as division_name,
                   sem.semester_name,
                   cb.batch_name
            FROM faculty_allocations fa
            JOIN faculty f ON fa.faculty_id = f.user_id
            JOIN subjects s ON fa.subject_id = s.id
            JOIN courses c ON s.course_id = c.id
            LEFT JOIN classes cl ON fa.class_id = cl.id
            LEFT JOIN divisions d ON fa.division_id = d.id
            LEFT JOIN semesters sem ON fa.semester_id = sem.id
            LEFT JOIN course_batches cb ON fa.course_batch_id = cb.id
            {where_clause}
            ORDER BY cl.display_order, c.name, f.name, s.name
        """, tuple(query_params))
    return cursor.fetchall()


def fetch_active_faculty(cursor):
    """Return active faculty ordered by name."""
    cursor.execute("SELECT * FROM faculty WHERE is_active = TRUE ORDER BY name")
    return cursor.fetchall()


def fetch_subjects_by_name(cursor):
    """Return subjects ordered by name."""
    cursor.execute("SELECT * FROM subjects ORDER BY name")
    return cursor.fetchall()


def fetch_divisions(cursor):
    """Return divisions ordered by name."""
    cursor.execute("SELECT * FROM divisions ORDER BY name")
    return cursor.fetchall()


def fetch_active_batches(cursor):
    """Return active course batches ordered by name."""
    cursor.execute("SELECT * FROM course_batches WHERE is_active = TRUE ORDER BY batch_name")
    return cursor.fetchall()


def fetch_faculty_user_id(cursor, faculty_id):
    """Return the user id row for a faculty record."""
    cursor.execute("SELECT user_id FROM faculty WHERE id = %s", (faculty_id,))
    return cursor.fetchone()


def insert_allocation(cursor, values):
    """Insert one allocation. The first value is faculty.user_id."""
    cursor.execute("""
            INSERT INTO faculty_allocations 
            (faculty_id, subject_id, class_id, division_id, semester_id, course_batch_id,
             allocated_hours, workload_percentage, is_primary, allocation_type, 
             start_date, end_date, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, values)


def update_allocation(cursor, values):
    """Update one allocation. The id is the last value."""
    cursor.execute("""
            UPDATE faculty_allocations 
            SET faculty_id = %s, subject_id = %s, class_id = %s, division_id = %s,
                semester_id = %s, course_batch_id = %s, allocated_hours = %s,
                workload_percentage = %s, is_primary = %s, allocation_type = %s,
                start_date = %s, end_date = %s, notes = %s
            WHERE id = %s
        """, values)


def delete_allocation(cursor, allocation_id):
    """Delete one allocation."""
    cursor.execute("DELETE FROM faculty_allocations WHERE id = %s", (allocation_id,))
