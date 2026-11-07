"""Admin student list and changes."""

from datetime import datetime

from flask import current_app, flash
from werkzeug.security import generate_password_hash

from core.pagination import page_bounds
from data_access.admin_students import (
    deactivate_student_users,
    deactivate_students,
    fetch_classes,
    fetch_courses,
    fetch_divisions,
    fetch_student,
    fetch_student_email,
    fetch_student_user_ids,
    fetch_username,
    insert_invited_student,
    insert_invited_user,
    insert_student_profile,
    insert_student_user,
    run_one,
    run_query,
    update_student_profile,
    update_user_password,
)
from extensions import get_db_connection
from security.permissions import get_accessible_student_ids

_QUERY_BASE = """FROM students s 
        LEFT JOIN users u ON s.user_id = u.id
        LEFT JOIN courses c ON s.course_id = c.id 
        LEFT JOIN classes cl ON s.class_id = cl.id 
        LEFT JOIN divisions d ON s.division_id = d.id
    """

_ALLOWED_SORTS = {
    's.name': 's.name',
    's.email': 's.email',
    's.phone': 's.phone',
    's.roll_number': 's.roll_number',
    's.admission_id': 's.admission_id',
    'division_name': 'd.name',
    'course_name': 'c.name',
    'class_name': 'cl.name'
}


def _cursor():
    connection = get_db_connection()
    return connection, connection.cursor(dictionary=True)


def _admission_id(user_id):
    return f"ADM{datetime.now().year}{user_id:06d}"


def list_students(page, search, course_filter, sort_by, sort_order, user_id, per_page=10):
    """Return the student list. The connection stays open."""
    connection, cursor = _cursor()
    count_query = f"SELECT COUNT(s.id) AS total {_QUERY_BASE}"
    data_query = f"""SELECT s.user_id, s.name, s.email, s.phone, s.roll_number, s.admission_id,
                    d.name as division_name, c.name as course_name, 
                    cl.name as class_name,
                    s.division_id, s.course_id, s.class_id
                    {_QUERY_BASE}"""
    where_conditions = [
        "u.role = 'Student'",
        "COALESCE(u.status, 'active') = 'active'",
        "COALESCE(s.is_active, 1) = 1",
    ]
    params = []
    accessible_student_ids = get_accessible_student_ids(user_id)
    if accessible_student_ids is not None:
        if accessible_student_ids:
            placeholders = ','.join(['%s'] * len(accessible_student_ids))
            where_conditions.append(f"s.id IN ({placeholders})")
            params.extend(accessible_student_ids)
        else:
            where_conditions.append("s.id = -1")
    if search:
        search_term = f"%{search}%"
        where_conditions.append("(s.name LIKE %s OR s.email LIKE %s OR s.admission_id LIKE %s OR s.roll_number LIKE %s)")
        params.extend([search_term, search_term, search_term, search_term])
    if course_filter:
        where_conditions.append("s.course_id = %s")
        params.append(course_filter)
    if where_conditions:
        where_clause = " WHERE " + " AND ".join(where_conditions)
        count_query += where_clause
        data_query += where_clause
    total = run_one(cursor, count_query, tuple(params))['total']
    offset, total_pages = page_bounds(page, per_page, total)
    sort_column = _ALLOWED_SORTS.get(sort_by, 's.name')
    sort_direction = 'DESC' if sort_order.upper() == 'DESC' else 'ASC'
    data_query += f" ORDER BY {sort_column} {sort_direction} LIMIT %s OFFSET %s"
    students = run_query(cursor, data_query, tuple(params) + (per_page, offset))
    courses = fetch_courses(cursor)
    classes = fetch_classes(cursor)
    divisions = fetch_divisions(cursor)
    total_active_query = """
        SELECT COUNT(s.id) AS total
        FROM students s
        LEFT JOIN users u ON s.user_id = u.id
        WHERE u.role = 'Student'
          AND COALESCE(u.status, 'active') = 'active'
          AND COALESCE(s.is_active, 1) = 1
    """
    if accessible_student_ids is not None:
        if accessible_student_ids:
            placeholders = ','.join(['%s'] * len(accessible_student_ids))
            total_active_query += f" AND s.id IN ({placeholders})"
            total_active_students = run_one(cursor, total_active_query, tuple(accessible_student_ids))['total']
        else:
            total_active_students = run_one(cursor, "SELECT 0 AS total")['total']
    else:
        total_active_students = run_one(cursor, total_active_query)['total']
    cursor.close()
    return {
        'students': students,
        'courses': courses,
        'classes': classes,
        'divisions': divisions,
        'total_pages': total_pages,
        'total': total,
        'total_active_students': total_active_students,
    }


def add_student(username, password, name, email, phone, roll_number, course_id, class_id, division_id):
    """Create a student. Duplicate checks close both without rolling back."""
    connection, cursor = _cursor()
    try:
        if fetch_username(cursor, username):
            flash('Username already exists.', 'danger')
            return 'duplicate'
        if fetch_student_email(cursor, email):
            flash('Email already registered for a student.', 'danger')
            return 'duplicate'
        user_id = insert_student_user(cursor, username, generate_password_hash(password))
        insert_student_profile(cursor, (
            user_id, user_id, name, email, phone, roll_number, course_id, class_id, division_id,
            _admission_id(user_id),
        ))
        connection.commit()
        flash('Student added successfully.', 'success')
        return 'ok'
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error adding student: {str(exc)}")
        flash('Error adding student. Please try again.', 'danger')
        return 'error'
    finally:
        cursor.close()
        connection.close()


def find_student(student_id):
    """Return one student. The connection stays open."""
    connection, cursor = _cursor()
    student = fetch_student(cursor, student_id)
    cursor.close()
    return student


def change_student(student_id, name, email, phone, roll_number, course_id, class_id, division_id, password):
    """Update a student. Both the cursor and connection are closed."""
    connection, cursor = _cursor()
    try:
        update_student_profile(cursor, (
            name, email, phone, roll_number, course_id, class_id, division_id, student_id,
        ))
        if password:
            update_user_password(cursor, generate_password_hash(password), student_id)
        connection.commit()
        flash('Student updated successfully.', 'success')
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error updating student: {str(exc)}")
        flash('Error updating student. Please try again.', 'danger')
    finally:
        cursor.close()
        connection.close()


def deactivate_selected_students(ids_to_delete):
    """Soft-delete students and their users. Both the cursor and connection are closed."""
    connection, cursor = _cursor()
    try:
        user_ids = [row['user_id'] for row in fetch_student_user_ids(cursor, ids_to_delete)]
        deactivate_students(cursor, ids_to_delete)
        if user_ids:
            deactivate_student_users(cursor, user_ids)
        connection.commit()
        flash(f'{len(ids_to_delete)} students deactivated successfully.', 'success')
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error deleting students: {str(exc)}")
        flash('Error deleting students. Please try again.', 'danger')
    finally:
        cursor.close()
        connection.close()


def _create_invited_student(cursor, name, email, username, password, course_id, class_id, division_id):
    if fetch_username(cursor, username):
        return 'username'
    if fetch_student_email(cursor, email):
        return 'email'
    user_id = insert_invited_user(cursor, username, generate_password_hash(password), email)
    insert_invited_student(cursor, (
        user_id, user_id, name, email, course_id, class_id, division_id, _admission_id(user_id),
    ))
    return 'ok'


def invite_students(files, form):
    """Import students. A caught error falls through to the form. Early redirects close both."""
    import pandas as pd
    import io

    success_count = 0
    error_count = 0
    errors = []
    connection, cursor = _cursor()
    try:
        if 'file' in files and files['file'].filename:
            uploaded = files['file']
            filename = uploaded.filename.lower()
            if filename.endswith('.csv'):
                frame = pd.read_csv(io.StringIO(uploaded.stream.read().decode('utf-8')))
            elif filename.endswith(('.xlsx', '.xls')):
                frame = pd.read_excel(uploaded)
            else:
                flash('Invalid file format. Please upload CSV or Excel file.', 'danger')
                return 'invite'
            required_cols = ['name', 'email', 'username', 'course_id']
            if not all(col in frame.columns for col in required_cols):
                flash(f'CSV must contain columns: {", ".join(required_cols)}', 'danger')
                return 'invite'
            default_password = form.get('default_password', 'Student@123')
            for idx, row in frame.iterrows():
                try:
                    name = str(row['name']).strip()
                    email = str(row['email']).strip()
                    username = str(row['username']).strip()
                    course_id = int(row['course_id']) if pd.notna(row.get('course_id')) else None
                    if not course_id:
                        errors.append(f"Row {idx+2}: course_id is required")
                        error_count += 1
                        continue
                    class_id = int(row['class_id']) if pd.notna(row.get('class_id')) else None
                    division_id = int(row['division_id']) if pd.notna(row.get('division_id')) else None
                    password = row.get('password', default_password) if pd.notna(row.get('password')) else default_password
                    result = _create_invited_student(
                        cursor, name, email, username, password, course_id, class_id, division_id,
                    )
                    if result == 'username':
                        errors.append(f"Row {idx+2}: Username '{username}' already exists")
                        error_count += 1
                        continue
                    if result == 'email':
                        errors.append(f"Row {idx+2}: Email '{email}' already registered")
                        error_count += 1
                        continue
                    success_count += 1
                except Exception as exc:
                    errors.append(f"Row {idx+2}: {str(exc)}")
                    error_count += 1
                    continue
            connection.commit()
        else:
            students_data = form.get('students_data', '')
            default_password = form.get('default_password', 'Student@123')
            default_course = form.get('default_course_id')
            default_class = form.get('default_class_id')
            default_division = form.get('default_division_id')
            if not students_data:
                flash('Please provide student data', 'warning')
                return 'invite'
            if not default_course:
                flash('Please select a default course (course_id is required)', 'danger')
                return 'invite'
            lines = students_data.strip().split('\n')
            for idx, line in enumerate(lines):
                if not line.strip():
                    continue
                try:
                    parts = [part.strip() for part in line.split(',')]
                    if len(parts) < 3:
                        errors.append(f"Line {idx+1}: Invalid format. Expected: name, email, username")
                        error_count += 1
                        continue
                    name, email, username = parts[0], parts[1], parts[2]
                    result = _create_invited_student(
                        cursor, name, email, username, default_password, default_course, default_class, default_division,
                    )
                    if result == 'username':
                        errors.append(f"Line {idx+1}: Username '{username}' already exists")
                        error_count += 1
                        continue
                    if result == 'email':
                        errors.append(f"Line {idx+1}: Email '{email}' already registered")
                        error_count += 1
                        continue
                    success_count += 1
                except Exception as exc:
                    errors.append(f"Line {idx+1}: {str(exc)}")
                    error_count += 1
                    continue
            connection.commit()
        if success_count > 0:
            flash(f'Successfully invited {success_count} student(s)', 'success')
        if error_count > 0:
            flash(f'{error_count} error(s) occurred. Check details below.', 'warning')
            for error in errors[:10]:
                flash(error, 'danger')
        return 'manage'
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Bulk invitation error: {str(exc)}")
        flash(f'Error processing bulk invitation: {str(exc)}', 'danger')
        return 'form'
    finally:
        cursor.close()
        connection.close()


def invite_form_choices():
    """Return course, class, and division choices. The connection stays open."""
    connection, cursor = _cursor()
    choices = {
        'courses': fetch_courses(cursor),
        'classes': fetch_classes(cursor),
        'divisions': fetch_divisions(cursor),
    }
    cursor.close()
    return choices
