"""
Student Management Routes
Handles all CRUD operations for students
"""

from flask import Blueprint, render_template, redirect, url_for, session, request, flash, current_app, jsonify
from werkzeug.security import generate_password_hash
from security import has_permission
from database import get_db_connection
import math
from department_access import get_accessible_student_ids

students_bp = Blueprint('students', __name__, url_prefix='/admin/students')


# --- Student Management (CRUD) ---
@students_bp.route('/')
@has_permission('students_view_student')
def manage_students():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    course_filter = request.args.get('course_filter', '', type=str)
    sort_by = request.args.get('sort_by', 's.name', type=str)
    sort_order = request.args.get('sort_order', 'ASC', type=str)
    per_page = 10
    offset = (page - 1) * per_page
    
    connection = get_db_connection()

    
    cursor = connection.cursor(dictionary=True)
    
    # Comprehensive query with all JOINs
    query_base = """FROM students s 
        LEFT JOIN courses c ON s.course_id = c.id 
        LEFT JOIN classes cl ON s.class_id = cl.id 
        LEFT JOIN divisions d ON s.division_id = d.id
    """
    
    count_query = f"SELECT COUNT(s.id) AS total {query_base}"
    data_query = f"""SELECT s.user_id, s.name, s.email, s.phone, s.roll_number, s.admission_id,
                    d.name as division_name, c.name as course_name, 
                    cl.name as class_name,
                    s.division_id, s.course_id, s.class_id
                    {query_base}"""
    
    # Build WHERE clause
    where_conditions = []
    params = []
    
    # Apply department filtering based on user permissions
    user_id = session.get('user_id')
    accessible_student_ids = get_accessible_student_ids(user_id)
    
    if accessible_student_ids is not None:  # None means access to all
        if accessible_student_ids:  # Has specific access
            placeholders = ','.join(['%s'] * len(accessible_student_ids))
            where_conditions.append(f"s.id IN ({placeholders})")
            params.extend(accessible_student_ids)
        else:  # No access
            where_conditions.append("s.id = -1")  # Impossible condition
    
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

    cursor.execute(count_query, tuple(params))
    total = cursor.fetchone()['total']
    total_pages = math.ceil(total / per_page)
    
    # Validate sort column to prevent SQL injection
    allowed_sorts = {
        's.name': 's.name',
        's.email': 's.email',
        's.phone': 's.phone',
        's.roll_number': 's.roll_number',
        's.admission_id': 's.admission_id',
        'division_name': 'd.name',
        'course_name': 'c.name',
        'class_name': 'cl.name'
    }
    sort_column = allowed_sorts.get(sort_by, 's.name')
    sort_direction = 'DESC' if sort_order.upper() == 'DESC' else 'ASC'
    
    data_query += f" ORDER BY {sort_column} {sort_direction} LIMIT %s OFFSET %s"
    cursor.execute(data_query, tuple(params) + (per_page, offset))
    students = cursor.fetchall()
    
    cursor.execute("SELECT id, name FROM courses ORDER BY name"); courses = cursor.fetchall()
    cursor.execute("SELECT id, name FROM classes ORDER BY display_order, name"); classes = cursor.fetchall()
    cursor.execute("SELECT id, name FROM divisions ORDER BY name"); divisions = cursor.fetchall()
    
    # Get total active students count (without filters)
    total_active_query = "SELECT COUNT(s.id) AS total FROM students s"
    if accessible_student_ids is not None:
        if accessible_student_ids:
            placeholders = ','.join(['%s'] * len(accessible_student_ids))
            total_active_query += f" WHERE s.id IN ({placeholders})"
            cursor.execute(total_active_query, tuple(accessible_student_ids))
        else:
            cursor.execute("SELECT 0 AS total")  # No access
    else:
        cursor.execute(total_active_query)
    
    total_active_students = cursor.fetchone()['total']
    
    cursor.close()
    
    return render_template('admin/manage_students.html', students=students, courses=courses, classes=classes, divisions=divisions, page=page, total_pages=total_pages, total=total, total_active_students=total_active_students, search=search, sort_by=sort_by, sort_order=sort_order)

@students_bp.route('/add', methods=['POST'])
@has_permission('students_add_student')
def add_student():
    # Admin endpoint to add a new student (used by Manage Students modal)
    username = request.form.get('username')
    password = request.form.get('password')
    name = request.form.get('name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    roll_number = request.form.get('roll_number')
    course_id = request.form.get('course_id')
    class_id = request.form.get('class_id')
    division_id = request.form.get('division_id')

    if not username or not password or not name:
        flash('Username, password, and name are required.', 'danger')
        return redirect(url_for('students.manage_students'))

    connection = get_db_connection()


    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id FROM users WHERE username = %s", [username])
        if cursor.fetchone():
            flash('Username already exists.', 'danger')
            return redirect(url_for('students.manage_students'))

        cursor.execute("SELECT id FROM students WHERE email = %s", [email])
        if cursor.fetchone():
            flash('Email already registered for a student.', 'danger')
            return redirect(url_for('students.manage_students'))

        hashed = generate_password_hash(password)
        cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, 'Student')", (username, hashed))
        user_id = cursor.lastrowid
        
        # Generate unique admission_id (e.g., ADM202500001)
        from datetime import datetime
        admission_id = f"ADM{datetime.now().year}{user_id:06d}"
        
        cursor.execute(
            "INSERT INTO students (id, user_id, name, email, phone, roll_number, course_id, class_id, division_id, admission_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (user_id, user_id, name, email, phone, roll_number, course_id, class_id, division_id, admission_id)
        )
        connection.commit()
        flash('Student added successfully.', 'success')
    except Exception as e:
        connection.rollback()
        current_app.logger.error(f"Error adding student: {str(e)}")
        flash('Error adding student. Please try again.', 'danger')
    finally:

        cursor.close()

        connection.close()
    return redirect(url_for('students.manage_students'))


@students_bp.route('/get/<int:student_id>')
@has_permission('students_view_student')
def get_student(student_id):
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    # Join with users table to get username
    cursor.execute("""
        SELECT s.name, s.email, s.phone, s.roll_number, s.course_id, s.class_id, s.division_id, u.username
        FROM students s
        JOIN users u ON s.user_id = u.id
        WHERE s.id = %s
    """, [student_id])
    student = cursor.fetchone()
    cursor.close()
    if student:
        return jsonify({
            'name': student[0], 'email': student[1], 'phone': student[2], 'roll_number': student[3],
            'course_id': student[4], 'class_id': student[5], 'division_id': student[6], 'username': student[7]
        })
    return jsonify({'error': 'Student not found'}), 404

@students_bp.route('/update/<int:student_id>', methods=['POST'])
@has_permission('students_change_student')
def update_student(student_id):
    name = request.form.get('name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    roll_number = request.form.get('roll_number')
    course_id = request.form.get('course_id')
    class_id = request.form.get('class_id')
    division_id = request.form.get('division_id')
    password = request.form.get('password')
    
    connection = get_db_connection()

    
    cursor = connection.cursor(dictionary=True)
    try:
        # Update student details
        cursor.execute("""
            UPDATE students 
            SET name = %s, email = %s, phone = %s, roll_number = %s, 
                course_id = %s, class_id = %s, division_id = %s
            WHERE id = %s
        """, (name, email, phone, roll_number, course_id, class_id, division_id, student_id))
        
        # Update password if provided
        if password:
            hashed = generate_password_hash(password)
            cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed, student_id))
        
        connection.commit()
        flash('Student updated successfully.', 'success')
    except Exception as e:
        connection.rollback()
        current_app.logger.error(f"Error updating student: {str(e)}")
        flash('Error updating student. Please try again.', 'danger')
    finally:

        cursor.close()

        connection.close()
    
    return redirect(url_for('students.manage_students'))
    
@students_bp.route('/bulk_delete', methods=['POST'])
@has_permission('students_delete_student')
def bulk_delete_students():
    ids_to_delete = request.form.getlist('student_ids')
    if not ids_to_delete:
        flash('No students selected for deletion.', 'warning')
        return redirect(url_for('students.manage_students'))
    
    connection = get_db_connection()

    
    cursor = connection.cursor(dictionary=True)
    try:
        # Get user_ids for the students to be deleted
        format_strings = ','.join(['%s'] * len(ids_to_delete))
        cursor.execute(f"SELECT user_id FROM students WHERE id IN ({format_strings})", tuple(ids_to_delete))
        user_ids = [row['user_id'] for row in cursor.fetchall()]
        
        # Delete students first (FK constraint)
        cursor.execute(f"DELETE FROM students WHERE id IN ({format_strings})", tuple(ids_to_delete))
        
        # Delete corresponding user accounts
        if user_ids:
            user_format_strings = ','.join(['%s'] * len(user_ids))
            cursor.execute(f"DELETE FROM users WHERE id IN ({user_format_strings})", tuple(user_ids))
        
        connection.commit()
        flash(f'{len(ids_to_delete)} students deleted successfully.', 'success')
    except Exception as e:
        connection.rollback()
        current_app.logger.error(f"Error deleting students: {str(e)}")
        flash('Error deleting students. Please try again.', 'danger')
    finally:

        cursor.close()

        connection.close()
    return redirect(url_for('students.manage_students'))

@students_bp.route('/bulk-invite', methods=['GET', 'POST'])
@has_permission('students_bulk_invite')
def bulk_invite_students():
    """Bulk student invitation via CSV/Excel upload or form"""
    if request.method == 'POST':
        import pandas as pd
        import io
        from werkzeug.security import generate_password_hash
        
        success_count = 0
        error_count = 0
        errors = []
        
        connection = get_db_connection()

        
        cursor = connection.cursor(dictionary=True)
        try:
            # Check if file was uploaded
            if 'file' in request.files and request.files['file'].filename:
                file = request.files['file']
                filename = file.filename.lower()
                
                # Read file based on extension
                if filename.endswith('.csv'):
                    df = pd.read_csv(io.StringIO(file.stream.read().decode('utf-8')))
                elif filename.endswith(('.xlsx', '.xls')):
                    df = pd.read_excel(file)
                else:
                    flash('Invalid file format. Please upload CSV or Excel file.', 'danger')
                    return redirect(url_for('students.bulk_invite_students'))
                
                # Expected columns: name, email, username, course_id (required)
                required_cols = ['name', 'email', 'username', 'course_id']
                if not all(col in df.columns for col in required_cols):
                    flash(f'CSV must contain columns: {", ".join(required_cols)}', 'danger')
                    return redirect(url_for('students.bulk_invite_students'))
                
                # Generate default password or use column if provided
                default_password = request.form.get('default_password', 'Student@123')
                
                for idx, row in df.iterrows():
                    try:
                        name = str(row['name']).strip()
                        email = str(row['email']).strip()
                        username = str(row['username']).strip()
                        
                        # course_id is required (NOT NULL in database)
                        course_id = int(row['course_id']) if pd.notna(row.get('course_id')) else None
                        if not course_id:
                            errors.append(f"Row {idx+2}: course_id is required")
                            error_count += 1
                            continue
                        
                        # Optional fields
                        class_id = int(row['class_id']) if pd.notna(row.get('class_id')) else None
                        division_id = int(row['division_id']) if pd.notna(row.get('division_id')) else None
                        password = row.get('password', default_password) if pd.notna(row.get('password')) else default_password
                        
                        # Check if username exists
                        cursor.execute("SELECT id FROM users WHERE username = %s", [username])
                        if cursor.fetchone():
                            errors.append(f"Row {idx+2}: Username '{username}' already exists")
                            error_count += 1
                            continue
                        
                        # Check if email exists
                        cursor.execute("SELECT id FROM students WHERE email = %s", [email])
                        if cursor.fetchone():
                            errors.append(f"Row {idx+2}: Email '{email}' already registered")
                            error_count += 1
                            continue
                        
                        # Create user account
                        hashed = generate_password_hash(password)
                        cursor.execute(
                            "INSERT INTO users (username, password, role, email, status) VALUES (%s, %s, 'Student', %s, 'active')",
                            (username, hashed, email)
                        )
                        user_id = cursor.lastrowid
                        
                        # Generate unique admission_id
                        from datetime import datetime
                        admission_id = f"ADM{datetime.now().year}{user_id:06d}"
                        
                        # Create student record (id must match user_id)
                        cursor.execute(
                            "INSERT INTO students (id, user_id, name, email, course_id, class_id, division_id, admission_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                            (user_id, user_id, name, email, course_id, class_id, division_id, admission_id)
                        )
                        
                        success_count += 1
                        
                    except Exception as e:
                        errors.append(f"Row {idx+2}: {str(e)}")
                        error_count += 1
                        continue
                
                connection.commit()
                
            else:
                # Form-based bulk invitation (manual entry)
                students_data = request.form.get('students_data', '')
                default_password = request.form.get('default_password', 'Student@123')
                default_course = request.form.get('default_course_id')
                default_class = request.form.get('default_class_id')
                default_division = request.form.get('default_division_id')
                
                if not students_data:
                    flash('Please provide student data', 'warning')
                    return redirect(url_for('students.bulk_invite_students'))
                
                if not default_course:
                    flash('Please select a default course (course_id is required)', 'danger')
                    return redirect(url_for('students.bulk_invite_students'))
                
                # Parse students data (format: name, email, username per line)
                lines = students_data.strip().split('\n')
                for idx, line in enumerate(lines):
                    if not line.strip():
                        continue
                    
                    try:
                        parts = [p.strip() for p in line.split(',')]
                        if len(parts) < 3:
                            errors.append(f"Line {idx+1}: Invalid format. Expected: name, email, username")
                            error_count += 1
                            continue
                        
                        name, email, username = parts[0], parts[1], parts[2]
                        
                        # Check username
                        cursor.execute("SELECT id FROM users WHERE username = %s", [username])
                        if cursor.fetchone():
                            errors.append(f"Line {idx+1}: Username '{username}' already exists")
                            error_count += 1
                            continue
                        
                        # Check email
                        cursor.execute("SELECT id FROM students WHERE email = %s", [email])
                        if cursor.fetchone():
                            errors.append(f"Line {idx+1}: Email '{email}' already registered")
                            error_count += 1
                            continue
                        
                        # Create user
                        hashed = generate_password_hash(default_password)
                        cursor.execute(
                            "INSERT INTO users (username, password, role, email, status) VALUES (%s, %s, 'Student', %s, 'active')",
                            (username, hashed, email)
                        )
                        user_id = cursor.lastrowid
                        
                        # Generate unique admission_id
                        from datetime import datetime
                        admission_id = f"ADM{datetime.now().year}{user_id:06d}"
                        
                        # Create student (id must match user_id)
                        cursor.execute(
                            "INSERT INTO students (id, user_id, name, email, course_id, class_id, division_id, admission_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                            (user_id, user_id, name, email, default_course, default_class, default_division, admission_id)
                        )
                        
                        success_count += 1
                        
                    except Exception as e:
                        errors.append(f"Line {idx+1}: {str(e)}")
                        error_count += 1
                        continue
                
                connection.commit()
            
            # Show results
            if success_count > 0:
                flash(f'Successfully invited {success_count} student(s)', 'success')
            if error_count > 0:
                flash(f'{error_count} error(s) occurred. Check details below.', 'warning')
                for error in errors[:10]:  # Show first 10 errors
                    flash(error, 'danger')
            
            return redirect(url_for('students.manage_students'))
            
        except Exception as e:
            connection.rollback()
            current_app.logger.error(f"Bulk invitation error: {str(e)}")
            flash(f'Error processing bulk invitation: {str(e)}', 'danger')
        finally:

            cursor.close()

            connection.close()
    
    # GET request - show form
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM courses ORDER BY name")
    courses = cursor.fetchall()
    cursor.execute("SELECT id, name FROM classes ORDER BY display_order, name")
    classes = cursor.fetchall()
    cursor.execute("SELECT id, name FROM divisions ORDER BY name")
    divisions = cursor.fetchall()
    cursor.close()
    
    return render_template('admin/bulk_invite_students.html', 
                         courses=courses, classes=classes, divisions=divisions)
