"""Subject SQL for the academic screen. Callers pass a cursor."""


def fetch_subjects(cursor, class_id, course_id):
    """Return subjects, optionally limited to one class and one course."""
    where_conditions = []
    query_params = []
    if class_id:
        where_conditions.append("s.class_id = %s")
        query_params.append(class_id)
    if course_id:
        where_conditions.append("s.course_id = %s")
        query_params.append(course_id)
    where_clause = ""
    if where_conditions:
        where_clause = "WHERE " + " AND ".join(where_conditions)
    # Join faculty on user_id (FK target), not id
    cursor.execute(f"""
            SELECT s.*, c.name as course_name, c.program,
                   cl.name as class_name, cl.display_order as class_order,
                   sem.semester_name,
                   GROUP_CONCAT(DISTINCT CONCAT(f.name, ' (', 
                       CASE WHEN fa.is_primary THEN 'Primary' ELSE 'Secondary' END, ')') 
                       SEPARATOR ', ') as faculty_names
            FROM subjects s
            JOIN courses c ON s.course_id = c.id
            LEFT JOIN classes cl ON s.class_id = cl.id
            LEFT JOIN semesters sem ON s.semester_id = sem.id
            LEFT JOIN faculty_allocations fa ON s.id = fa.subject_id
            LEFT JOIN faculty f ON fa.faculty_id = f.user_id
            {where_clause}
            GROUP BY s.id
            ORDER BY cl.display_order, c.name, s.name
        """, tuple(query_params))
    return cursor.fetchall()


def fetch_active_courses(cursor):
    """Return active courses ordered by name."""
    cursor.execute("SELECT * FROM courses WHERE is_active = TRUE ORDER BY name")
    return cursor.fetchall()


def fetch_classes_by_display_order(cursor):
    """Return classes in display order."""
    cursor.execute("SELECT * FROM classes ORDER BY display_order")
    return cursor.fetchall()


def fetch_semesters_by_number(cursor):
    """Return semesters in semester-number order."""
    cursor.execute("SELECT * FROM semesters ORDER BY semester_number")
    return cursor.fetchall()


def fetch_course_for_new_subject(cursor, course_id):
    """Return the course fields used when adding a subject."""
    cursor.execute("SELECT name, program, total_semesters FROM courses WHERE id = %s", (course_id,))
    return cursor.fetchone()


def fetch_course_for_subject_edit(cursor, course_id):
    """Return the course fields used when editing a subject."""
    cursor.execute("SELECT program, total_semesters FROM courses WHERE id = %s", (course_id,))
    return cursor.fetchone()


def fetch_semester_number(cursor, semester_id):
    """Return the semester number row."""
    cursor.execute("SELECT semester_number FROM semesters WHERE id = %s", (semester_id,))
    return cursor.fetchone()


def insert_subject(cursor, values):
    """Insert one subject."""
    cursor.execute("""
            INSERT INTO subjects 
            (name, course_code, course_id, class_id, semester_id, course_type, theory_practical,
             credits, theory_credits, practical_credits, marks, theory_marks, practical_marks,
             lectures_per_week, practical_hours_per_week, is_elective, description, syllabus_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, values)


def update_subject(cursor, values):
    """Update one subject. The id is the last value."""
    cursor.execute("""
            UPDATE subjects 
            SET name = %s, course_code = %s, course_id = %s, class_id = %s, semester_id = %s,
                course_type = %s, theory_practical = %s, credits = %s, theory_credits = %s,
                practical_credits = %s, marks = %s, theory_marks = %s, practical_marks = %s,
                lectures_per_week = %s, practical_hours_per_week = %s, is_elective = %s,
                description = %s, syllabus_url = %s
            WHERE id = %s
        """, values)


def delete_subject(cursor, subject_id):
    """Delete one subject."""
    cursor.execute("DELETE FROM subjects WHERE id = %s", (subject_id,))
