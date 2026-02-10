from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
import mysql.connector
from config import Config
from security import has_permission
from routes.admin_utils import admin_required

academic_bp = Blueprint('academic', __name__, url_prefix='/admin/academic')

def get_db_connection():
    """Get database connection"""
    return mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB
    )

# ============================================================================
# MAIN DASHBOARD
# ============================================================================

@academic_bp.route('/manage_academics')
@admin_required
def manage_academics():
    """Academic Management Dashboard"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get statistics
        cursor.execute("SELECT COUNT(*) as count FROM academic_years")
        academic_years_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM semesters")
        semesters_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM courses")
        courses_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM subjects")
        subjects_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM course_batches")
        batches_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM faculty_allocations")
        allocations_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM departments")
        departments_count = cursor.fetchone()['count']
        
        # Get current academic year
        cursor.execute("""
            SELECT * FROM academic_years 
            WHERE is_current = TRUE 
            ORDER BY start_date DESC LIMIT 1
        """)
        current_year = cursor.fetchone()
        
        # Get current semester
        cursor.execute("""
            SELECT * FROM semesters 
            WHERE is_current = TRUE 
            ORDER BY start_date DESC LIMIT 1
        """)
        current_semester = cursor.fetchone()
        
        return render_template('admin/academic.html',
                             academic_years_count=academic_years_count,
                             semesters_count=semesters_count,
                             courses_count=courses_count,
                             subjects_count=subjects_count,
                             batches_count=batches_count,
                             allocations_count=allocations_count,
                             departments_count=departments_count,
                             current_year=current_year,
                             current_semester=current_semester)
    
    finally:
        cursor.close()
        connection.close()

# ============================================================================
# ACADEMIC YEARS MANAGEMENT
# ============================================================================

@academic_bp.route('/academic-years')
@has_permission('academicyears_view')
def manage_academic_years():
    """Display Academic Years Management Page"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT * FROM academic_years 
            ORDER BY start_date DESC
        """)
        academic_years = cursor.fetchall()
        
        return render_template('admin/manage_academic_years.html',
                             academic_years=academic_years)
    
    finally:
        cursor.close()
        connection.close()

@academic_bp.route('/academic-years/add', methods=['POST'])
@has_permission('academicyears_add')
def add_academic_year():
    """Add new academic year"""
    name = request.form.get('name')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    is_current = 1 if request.form.get('is_current') else 0
    description = request.form.get('description', '')
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # If marking as current, unmark others
        if is_current:
            cursor.execute("UPDATE academic_years SET is_current = 0")
        
        cursor.execute("""
            INSERT INTO academic_years (name, start_date, end_date, is_current, description)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, start_date, end_date, is_current, description))
        
        connection.commit()
        flash(f'Academic Year {name} added successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error adding academic year: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_academic_years'))

@academic_bp.route('/academic-years/edit/<int:id>', methods=['POST'])
@has_permission('academicyears_change')
def edit_academic_year(id):
    """Edit academic year"""
    name = request.form.get('name')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    is_current = 1 if request.form.get('is_current') else 0
    description = request.form.get('description', '')
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # If marking as current, unmark others
        if is_current:
            cursor.execute("UPDATE academic_years SET is_current = 0 WHERE id != %s", (id,))
        
        cursor.execute("""
            UPDATE academic_years 
            SET name = %s, start_date = %s, end_date = %s, is_current = %s, description = %s
            WHERE id = %s
        """, (name, start_date, end_date, is_current, description, id))
        
        connection.commit()
        flash(f'Academic Year {name} updated successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error updating academic year: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_academic_years'))

@academic_bp.route('/academic-years/delete/<int:id>', methods=['POST'])
@has_permission('academicyears_delete')
def delete_academic_year(id):
    """Delete academic year"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        cursor.execute("DELETE FROM academic_years WHERE id = %s", (id,))
        connection.commit()
        flash('Academic Year deleted successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error deleting academic year: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_academic_years'))

# ============================================================================
# SEMESTERS MANAGEMENT
# ============================================================================

@academic_bp.route('/semesters')
@has_permission('semesters_view')
def manage_semesters():
    """Display Semesters Management Page"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT s.*, ay.name as academic_year_name, c.name as class_name
            FROM semesters s
            JOIN academic_years ay ON s.academic_year_id = ay.id
            LEFT JOIN classes c ON s.class_id = c.id
            ORDER BY s.semester_number
        """)
        semesters = cursor.fetchall()
        # Normalize date and Decimal fields for JSON serialization in template
        try:
            import decimal as _decimal
            from datetime import date, datetime
            for s in semesters:
                # Convert Decimal credits to float
                for key in ('min_credits','max_credits'):
                    if key in s and isinstance(s[key], _decimal.Decimal):
                        s[key] = float(s[key])
                # Convert dates to ISO strings
                for key in ('start_date','end_date'):
                    v = s.get(key)
                    if isinstance(v, (date, datetime)):
                        s[key] = v.isoformat()
        except Exception:
            pass
        # Ensure Decimal fields are JSON-serializable in templates
        try:
            import decimal as _decimal
            for s in semesters:
                for key in ('min_credits','max_credits'):
                    if key in s and isinstance(s[key], _decimal.Decimal):
                        s[key] = float(s[key])
        except Exception:
            pass
        
        cursor.execute("SELECT * FROM academic_years ORDER BY start_date DESC")
        academic_years = cursor.fetchall()
        
        cursor.execute("SELECT * FROM classes ORDER BY display_order, name")
        classes = cursor.fetchall()
        
        return render_template('admin/manage_semesters.html',
                             semesters=semesters,
                             academic_years=academic_years,
                             classes=classes)
    
    finally:
        cursor.close()
        connection.close()

@academic_bp.route('/semesters/add', methods=['POST'])
@has_permission('semesters_add')
def add_semester():
    """Add new semester"""
    academic_year_id = request.form.get('academic_year_id')
    semester_number = request.form.get('semester_number')
    semester_name = request.form.get('semester_name')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    class_id = request.form.get('class_id')
    is_current = 1 if request.form.get('is_current') else 0
    min_credits = request.form.get('min_credits', 18.0)
    max_credits = request.form.get('max_credits', 30.0)
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Allow multiple active semesters per academic year (no global reset)
        
        cursor.execute("""
            INSERT INTO semesters 
            (academic_year_id, semester_number, semester_name, start_date, end_date, 
             class_id, is_current, min_credits, max_credits)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (academic_year_id, semester_number, semester_name, start_date, end_date,
              class_id, is_current, min_credits, max_credits))
        
        connection.commit()
        flash(f'Semester {semester_name} added successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error adding semester: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_semesters'))

@academic_bp.route('/semesters/edit/<int:id>', methods=['POST'])
@has_permission('semesters_change')
def edit_semester(id):
    """Edit semester"""
    academic_year_id = request.form.get('academic_year_id')
    semester_number = request.form.get('semester_number')
    semester_name = request.form.get('semester_name')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    class_id = request.form.get('class_id')
    is_current = 1 if request.form.get('is_current') else 0
    min_credits = request.form.get('min_credits')
    max_credits = request.form.get('max_credits')
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Allow multiple active semesters per academic year (no uniqueness enforcement)
        
        cursor.execute("""
            UPDATE semesters 
            SET academic_year_id = %s, semester_number = %s, semester_name = %s,
                start_date = %s, end_date = %s, class_id = %s, is_current = %s,
                min_credits = %s, max_credits = %s
            WHERE id = %s
        """, (academic_year_id, semester_number, semester_name, start_date, end_date,
              class_id, is_current, min_credits, max_credits, id))
        
        connection.commit()
        flash(f'Semester {semester_name} updated successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error updating semester: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_semesters'))

@academic_bp.route('/semesters/delete/<int:id>', methods=['POST'])
@has_permission('semesters_delete')
def delete_semester(id):
    """Delete semester"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        cursor.execute("DELETE FROM semesters WHERE id = %s", (id,))
        connection.commit()
        flash('Semester deleted successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error deleting semester: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_semesters'))

# ============================================================================
# DEPARTMENTS MANAGEMENT
# ============================================================================

@academic_bp.route('/departments')
@has_permission('departments_view')
def manage_departments():
    """Display Departments Management Page"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT d.*, COUNT(c.id) as course_count
            FROM departments d
            LEFT JOIN courses c ON d.id = c.department_id
            GROUP BY d.id
            ORDER BY d.name
        """)
        departments = cursor.fetchall()
        
        return render_template('admin/manage_departments.html',
                             departments=departments)
    
    finally:
        cursor.close()
        connection.close()

@academic_bp.route('/departments/add', methods=['POST'])
@has_permission('departments_add')
def add_department():
    """Add new department"""
    name = request.form.get('name')
    code = request.form.get('code')
    description = request.form.get('description', '')
    head_of_department = request.form.get('head_of_department', '')
    is_active = 1 if request.form.get('is_active') else 0
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO departments (name, code, description, head_of_department, is_active)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, code, description, head_of_department, is_active))
        
        connection.commit()
        flash(f'Department {name} added successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error adding department: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_departments'))

@academic_bp.route('/departments/edit/<int:id>', methods=['POST'])
@has_permission('departments_change')
def edit_department(id):
    """Edit department"""
    name = request.form.get('name')
    code = request.form.get('code')
    description = request.form.get('description', '')
    head_of_department = request.form.get('head_of_department', '')
    is_active = 1 if request.form.get('is_active') else 0
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        cursor.execute("""
            UPDATE departments 
            SET name = %s, code = %s, description = %s, 
                head_of_department = %s, is_active = %s
            WHERE id = %s
        """, (name, code, description, head_of_department, is_active, id))
        
        connection.commit()
        flash(f'Department {name} updated successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error updating department: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_departments'))

@academic_bp.route('/departments/delete/<int:id>', methods=['POST'])
@has_permission('departments_delete')
def delete_department(id):
    """Delete department"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        cursor.execute("DELETE FROM departments WHERE id = %s", (id,))
        connection.commit()
        flash('Department deleted successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error deleting department: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_departments'))

# ============================================================================
# COURSES MANAGEMENT
# ============================================================================

@academic_bp.route('/courses')
@has_permission('courses_view_course')
def manage_courses():
    """Display Courses Management Page"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT COUNT(*) AS count FROM courses WHERE is_active = TRUE")
        course_count = cursor.fetchone()['count']
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
        courses = cursor.fetchall()
        
        cursor.execute("SELECT * FROM departments WHERE is_active = TRUE ORDER BY name")
        departments = cursor.fetchall()
        
        return render_template('admin/manage_courses.html',
                             courses=courses,
                             departments=departments,course_count=course_count)
    
    finally:
        cursor.close()
        connection.close()

@academic_bp.route('/courses/add', methods=['POST'])
@has_permission('courses_add_course')
def add_course():
    """Add new course"""
    name = request.form.get('name')
    code = request.form.get('code')
    program = request.form.get('program')
    department_id = request.form.get('department_id')
    duration_years = request.form.get('duration_years', 3)
    total_semesters = request.form.get('total_semesters', 6)
    description = request.form.get('description', '')
    is_active = 1 if request.form.get('is_active') else 0
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO courses 
            (name, code, program, department_id, duration_years, total_semesters, description, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (name, code, program, department_id, duration_years, total_semesters, description, is_active))
        
        connection.commit()
        flash(f'Course {name} added successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error adding course: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_courses'))

@academic_bp.route('/courses/edit/<int:id>', methods=['POST'])
@has_permission('courses_change_course')
def edit_course(id):
    """Edit course"""
    name = request.form.get('name')
    code = request.form.get('code')
    program = request.form.get('program')
    department_id = request.form.get('department_id')
    duration_years = request.form.get('duration_years')
    total_semesters = request.form.get('total_semesters')
    description = request.form.get('description', '')
    is_active = 1 if request.form.get('is_active') else 0
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        cursor.execute("""
            UPDATE courses 
            SET name = %s, code = %s, program = %s, department_id = %s,
                duration_years = %s, total_semesters = %s, description = %s, is_active = %s
            WHERE id = %s
        """, (name, code, program, department_id, duration_years, total_semesters, description, is_active, id))
        
        connection.commit()
        flash(f'Course {name} updated successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error updating course: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_courses'))

@academic_bp.route('/courses/delete/<int:id>', methods=['POST'])
@has_permission('courses_delete_course')
def delete_course(id):
    """Delete course"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        cursor.execute("DELETE FROM courses WHERE id = %s", (id,))
        connection.commit()
        flash('Course deleted successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error deleting course: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_courses'))

# ============================================================================
# SUBJECTS MANAGEMENT
# ============================================================================

@academic_bp.route('/subjects')
@has_permission('subjects_view_subject')
def manage_subjects():
    """Display Subjects Management Page with class-based filtering"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Get filter parameters
    filter_class_id = request.args.get('class_id', type=int)
    filter_course_id = request.args.get('course_id', type=int)
    
    try:
        # Build dynamic WHERE clause for filters
        where_conditions = []
        query_params = []
        
        if filter_class_id:
            where_conditions.append("s.class_id = %s")
            query_params.append(filter_class_id)
        
        if filter_course_id:
            where_conditions.append("s.course_id = %s")
            query_params.append(filter_course_id)
        
        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)
        
        # FIXED: Join faculty on user_id (FK target), not id
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
        subjects = cursor.fetchall()
        # Convert Decimal fields to float for JSON serialization in templates
        def _to_float(x):
            try:
                import decimal
                if isinstance(x, decimal.Decimal):
                    return float(x)
            except Exception:
                pass
            return x
        for s in subjects:
            for key in (
                'credits','theory_credits','practical_credits',
                'marks','theory_marks','practical_marks',
                'lectures_per_week','practical_hours_per_week'
            ):
                if key in s and s[key] is not None:
                    s[key] = _to_float(s[key])
        
        cursor.execute("SELECT * FROM courses WHERE is_active = TRUE ORDER BY name")
        courses = cursor.fetchall()
        
        cursor.execute("SELECT * FROM classes ORDER BY display_order")
        classes = cursor.fetchall()
        
        cursor.execute("SELECT * FROM semesters ORDER BY semester_number")
        semesters = cursor.fetchall()
        
        return render_template('admin/manage_subjects.html',
                             subjects=subjects,
                             courses=courses,
                             classes=classes,
                             semesters=semesters,
                             filter_class_id=filter_class_id,
                             filter_course_id=filter_course_id)
    
    finally:
        cursor.close()
        connection.close()

@academic_bp.route('/subjects/add', methods=['POST'])
@has_permission('subjects_add_subject')
def add_subject():
    """Add new subject"""
    name = request.form.get('name')
    course_code = request.form.get('course_code')
    course_id = request.form.get('course_id')
    class_id = request.form.get('class_id') or None
    semester_id = request.form.get('semester_id') or None
    course_type = request.form.get('course_type', 'Core')
    theory_practical = request.form.get('theory_practical', 'Theory')
    credits = float(request.form.get('credits', 3.0))
    theory_credits = float(request.form.get('theory_credits', 0))
    practical_credits = float(request.form.get('practical_credits', 0))
    marks = int(request.form.get('marks', 100))
    theory_marks = int(request.form.get('theory_marks', 0))
    practical_marks = int(request.form.get('practical_marks', 0))
    lectures_per_week = int(request.form.get('lectures_per_week', 3))
    practical_hours_per_week = int(request.form.get('practical_hours_per_week', 0))
    is_elective = 1 if request.form.get('is_elective') else 0
    description = request.form.get('description', '')
    syllabus_url = request.form.get('syllabus_url', '')
    
    # Normalize credits/marks and validate semester selection against course structure
    # Enforce mode-specific credits/marks
    if theory_practical == 'Theory':
        practical_credits = 0.0
        practical_marks = 0
    elif theory_practical == 'Practical':
        theory_credits = 0.0
        theory_marks = 0
    # Auto-correct total credits/marks to satisfy DB CHECK constraints
    calculated_credits = round((theory_credits + practical_credits), 1)
    if abs(credits - calculated_credits) > 0.1:
        credits = calculated_credits
    calculated_marks = theory_marks + practical_marks
    if marks != calculated_marks:
        marks = calculated_marks

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Validate semester compatibility with the selected course (with sensible defaults)
        cursor.execute("SELECT name, program, total_semesters FROM courses WHERE id = %s", (course_id,))
        course_row = cursor.fetchone()
        if not course_row:
            raise Exception('Invalid course selected')

        if semester_id:
            cursor.execute("SELECT semester_number FROM semesters WHERE id = %s", (semester_id,))
            sem_row = cursor.fetchone()
            if not sem_row:
                raise Exception('Invalid semester selected')
            max_sem = int(course_row.get('total_semesters') or 0)
            if not max_sem:
                prog = (course_row.get('program') or '').upper()
                if prog == 'PG':
                    max_sem = 4
                elif prog == 'UG':
                    max_sem = 6
                name_lower = (course_row.get('name') or '').lower()
                if 'engineer' in name_lower:
                    max_sem = max(max_sem, 8)
            if int(sem_row['semester_number']) > max_sem:
                raise Exception(f"Selected semester exceeds allowed semesters for the course (max {max_sem}).")

        cursor.execute("""
            INSERT INTO subjects 
            (name, course_code, course_id, class_id, semester_id, course_type, theory_practical,
             credits, theory_credits, practical_credits, marks, theory_marks, practical_marks,
             lectures_per_week, practical_hours_per_week, is_elective, description, syllabus_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (name, course_code, course_id, class_id, semester_id, course_type, theory_practical,
              credits, theory_credits, practical_credits, marks, theory_marks, practical_marks,
              lectures_per_week, practical_hours_per_week, is_elective, description, syllabus_url))
        
        connection.commit()
        flash(f'Subject {name} added successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error adding subject: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_subjects'))

@academic_bp.route('/subjects/edit/<int:id>', methods=['POST'])
@has_permission('subjects_change_subject')
def edit_subject(id):
    """Edit subject"""
    name = request.form.get('name')
    course_code = request.form.get('course_code')
    course_id = request.form.get('course_id')
    class_id = request.form.get('class_id') or None
    semester_id = request.form.get('semester_id') or None
    course_type = request.form.get('course_type')
    theory_practical = request.form.get('theory_practical')
    credits = float(request.form.get('credits'))
    theory_credits = float(request.form.get('theory_credits'))
    practical_credits = float(request.form.get('practical_credits'))
    marks = int(request.form.get('marks'))
    theory_marks = int(request.form.get('theory_marks'))
    practical_marks = int(request.form.get('practical_marks'))
    lectures_per_week = int(request.form.get('lectures_per_week'))
    practical_hours_per_week = int(request.form.get('practical_hours_per_week'))
    is_elective = 1 if request.form.get('is_elective') else 0
    description = request.form.get('description', '')
    syllabus_url = request.form.get('syllabus_url', '')
    
    # Normalize credits/marks and validate semester selection against course structure
    if theory_practical == 'Theory':
        practical_credits = 0.0
        practical_marks = 0
    elif theory_practical == 'Practical':
        theory_credits = 0.0
        theory_marks = 0
    calculated_credits = round((theory_credits + practical_credits), 1)
    if abs(credits - calculated_credits) > 0.1:
        credits = calculated_credits
    calculated_marks = theory_marks + practical_marks
    if marks != calculated_marks:
        marks = calculated_marks

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Validate semester compatibility with the selected course
        cursor.execute("SELECT program, total_semesters FROM courses WHERE id = %s", (course_id,))
        course_row = cursor.fetchone()
        if not course_row:
            raise Exception('Invalid course selected')

        if semester_id:
            cursor.execute("SELECT semester_number FROM semesters WHERE id = %s", (semester_id,))
            sem_row = cursor.fetchone()
            if not sem_row:
                raise Exception('Invalid semester selected')
            if int(sem_row['semester_number']) > int(course_row['total_semesters'] or 0):
                raise Exception(f"Selected semester exceeds total semesters for the course ({course_row['total_semesters']}).")

        cursor.execute("""
            UPDATE subjects 
            SET name = %s, course_code = %s, course_id = %s, class_id = %s, semester_id = %s,
                course_type = %s, theory_practical = %s, credits = %s, theory_credits = %s,
                practical_credits = %s, marks = %s, theory_marks = %s, practical_marks = %s,
                lectures_per_week = %s, practical_hours_per_week = %s, is_elective = %s,
                description = %s, syllabus_url = %s
            WHERE id = %s
        """, (name, course_code, course_id, class_id, semester_id, course_type, theory_practical,
              credits, theory_credits, practical_credits, marks, theory_marks, practical_marks,
              lectures_per_week, practical_hours_per_week, is_elective, description, syllabus_url, id))
        
        connection.commit()
        flash(f'Subject {name} updated successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error updating subject: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_subjects'))

@academic_bp.route('/subjects/delete/<int:id>', methods=['POST'])
@has_permission('subjects_delete_subject')
def delete_subject(id):
    """Delete subject"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        cursor.execute("DELETE FROM subjects WHERE id = %s", (id,))
        connection.commit()
        flash('Subject deleted successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error deleting subject: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_subjects'))

# ============================================================================
# COURSE BATCHES MANAGEMENT
# ============================================================================

@academic_bp.route('/batches')
@has_permission('batches_view')
def manage_batches():
    """Display Course Batches Management Page"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT cb.*, c.name as course_name, c.program, c.duration_years,
                   ay.name as academic_year_name
            FROM course_batches cb
            JOIN courses c ON cb.course_id = c.id
            LEFT JOIN academic_years ay ON cb.academic_year_id = ay.id
            ORDER BY cb.start_year DESC, c.name
        """)
        batches = cursor.fetchall()
        
        cursor.execute("SELECT * FROM courses WHERE is_active = TRUE ORDER BY name")
        courses = cursor.fetchall()
        
        cursor.execute("SELECT * FROM academic_years ORDER BY start_date DESC")
        academic_years = cursor.fetchall()
        
        return render_template('admin/manage_batches.html',
                             batches=batches,
                             courses=courses,
                             academic_years=academic_years)
    
    finally:
        cursor.close()
        connection.close()

@academic_bp.route('/batches/add', methods=['POST'])
@has_permission('batches_add')
def add_batch():
    """Add new course batch"""
    course_id = request.form.get('course_id')
    batch_name = request.form.get('batch_name')
    academic_year_id = request.form.get('academic_year_id') or None
    start_year = request.form.get('start_year')
    end_year = request.form.get('end_year')
    total_students = int(request.form.get('total_students', 0))
    current_semester = int(request.form.get('current_semester', 1))
    is_active = 1 if request.form.get('is_active') else 0
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO course_batches 
            (course_id, batch_name, academic_year_id, start_year, end_year, 
             total_students, current_semester, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (course_id, batch_name, academic_year_id, start_year, end_year,
              total_students, current_semester, is_active))
        
        connection.commit()
        flash(f'Batch {batch_name} added successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error adding batch: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_batches'))

@academic_bp.route('/batches/edit/<int:id>', methods=['POST'])
@has_permission('batches_change')
def edit_batch(id):
    """Edit course batch"""
    course_id = request.form.get('course_id')
    batch_name = request.form.get('batch_name')
    academic_year_id = request.form.get('academic_year_id') or None
    start_year = request.form.get('start_year')
    end_year = request.form.get('end_year')
    total_students = int(request.form.get('total_students'))
    current_semester = int(request.form.get('current_semester'))
    is_active = 1 if request.form.get('is_active') else 0
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        cursor.execute("""
            UPDATE course_batches 
            SET course_id = %s, batch_name = %s, academic_year_id = %s,
                start_year = %s, end_year = %s, total_students = %s,
                current_semester = %s, is_active = %s
            WHERE id = %s
        """, (course_id, batch_name, academic_year_id, start_year, end_year,
              total_students, current_semester, is_active, id))
        
        connection.commit()
        flash(f'Batch {batch_name} updated successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error updating batch: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_batches'))

@academic_bp.route('/batches/delete/<int:id>', methods=['POST'])
@has_permission('batches_delete')
def delete_batch(id):
    """Delete course batch"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        cursor.execute("DELETE FROM course_batches WHERE id = %s", (id,))
        connection.commit()
        flash('Batch deleted successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error deleting batch: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_batches'))

# ============================================================================
# FACULTY ALLOCATIONS MANAGEMENT
# ============================================================================

@academic_bp.route('/allocations')
@has_permission('allocations_view')
def manage_allocations():
    """Display Faculty Allocations Management Page with class-based filtering"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Get filter parameters for class-centric view
    filter_class_id = request.args.get('class_id', type=int)
    filter_faculty_id = request.args.get('faculty_id', type=int)
    filter_course_id = request.args.get('course_id', type=int)
    
    try:
        # Build dynamic WHERE clause for filters
        where_conditions = []
        query_params = []
        
        if filter_class_id:
            where_conditions.append("fa.class_id = %s")
            query_params.append(filter_class_id)
        
        if filter_faculty_id:
            where_conditions.append("f.id = %s")
            query_params.append(filter_faculty_id)
        
        if filter_course_id:
            where_conditions.append("s.course_id = %s")
            query_params.append(filter_course_id)
        
        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)
        
        # NOTE: faculty_allocations.faculty_id FK references faculty.user_id
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
        allocations = cursor.fetchall()
        # Ensure Decimal fields are JSON-serializable for tojson in template
        try:
            import decimal as _decimal
            for a in allocations:
                for key in ('allocated_hours','workload_percentage'):
                    if key in a and isinstance(a[key], _decimal.Decimal):
                        a[key] = float(a[key])
        except Exception:
            pass
        
        cursor.execute("SELECT * FROM faculty WHERE is_active = TRUE ORDER BY name")
        faculty = cursor.fetchall()
        
        cursor.execute("SELECT * FROM subjects ORDER BY name")
        subjects = cursor.fetchall()
        
        cursor.execute("SELECT * FROM classes ORDER BY display_order")
        classes = cursor.fetchall()
        
        cursor.execute("SELECT * FROM divisions ORDER BY name")
        divisions = cursor.fetchall()
        
        cursor.execute("SELECT * FROM semesters ORDER BY semester_number")
        semesters = cursor.fetchall()
        
        cursor.execute("SELECT * FROM course_batches WHERE is_active = TRUE ORDER BY batch_name")
        batches = cursor.fetchall()
        
        cursor.execute("SELECT * FROM courses WHERE is_active = TRUE ORDER BY name")
        courses = cursor.fetchall()
        
        return render_template('admin/manage_allocations.html',
                             allocations=allocations,
                             faculty=faculty,
                             subjects=subjects,
                             classes=classes,
                             divisions=divisions,
                             semesters=semesters,
                             batches=batches,
                             courses=courses,
                             filter_class_id=filter_class_id,
                             filter_faculty_id=filter_faculty_id,
                             filter_course_id=filter_course_id)
    
    finally:
        cursor.close()
        connection.close()

@academic_bp.route('/allocations/add', methods=['POST'])
@has_permission('allocations_add')
def add_allocation():
    """Add new faculty allocation"""
    faculty_id_from_form = request.form.get('faculty_id')
    subject_id = request.form.get('subject_id')
    class_id = request.form.get('class_id') or None
    division_id = request.form.get('division_id') or None
    semester_id = request.form.get('semester_id') or None
    course_batch_id = request.form.get('course_batch_id') or None
    allocated_hours = float(request.form.get('allocated_hours', 0))
    workload_percentage = float(request.form.get('workload_percentage', 100.0))
    is_primary = 1 if request.form.get('is_primary') else 0
    allocation_type = request.form.get('allocation_type', 'Regular')
    start_date = request.form.get('start_date') or None
    end_date = request.form.get('end_date') or None
    notes = request.form.get('notes', '')
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # CRITICAL: FK constraint requires faculty.user_id, not faculty.id
        # Convert faculty.id to user_id
        cursor.execute("SELECT user_id FROM faculty WHERE id = %s", (faculty_id_from_form,))
        faculty_row = cursor.fetchone()
        if not faculty_row:
            flash('Invalid faculty selection.', 'danger')
            return redirect(url_for('academic.manage_allocations'))
        
        faculty_user_id = faculty_row[0]
        
        cursor.execute("""
            INSERT INTO faculty_allocations 
            (faculty_id, subject_id, class_id, division_id, semester_id, course_batch_id,
             allocated_hours, workload_percentage, is_primary, allocation_type, 
             start_date, end_date, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (faculty_user_id, subject_id, class_id, division_id, semester_id, course_batch_id,
              allocated_hours, workload_percentage, is_primary, allocation_type,
              start_date, end_date, notes))
        
        connection.commit()
        flash('Faculty allocation added successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error adding allocation: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_allocations'))

@academic_bp.route('/allocations/edit/<int:id>', methods=['POST'])
@has_permission('allocations_change')
def edit_allocation(id):
    """Edit faculty allocation"""
    faculty_id_from_form = request.form.get('faculty_id')
    subject_id = request.form.get('subject_id')
    class_id = request.form.get('class_id') or None
    division_id = request.form.get('division_id') or None
    semester_id = request.form.get('semester_id') or None
    course_batch_id = request.form.get('course_batch_id') or None
    allocated_hours = float(request.form.get('allocated_hours'))
    workload_percentage = float(request.form.get('workload_percentage'))
    is_primary = 1 if request.form.get('is_primary') else 0
    allocation_type = request.form.get('allocation_type')
    start_date = request.form.get('start_date') or None
    end_date = request.form.get('end_date') or None
    notes = request.form.get('notes', '')
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # CRITICAL: FK constraint requires faculty.user_id, not faculty.id
        cursor.execute("SELECT user_id FROM faculty WHERE id = %s", (faculty_id_from_form,))
        faculty_row = cursor.fetchone()
        if not faculty_row:
            flash('Invalid faculty selection.', 'danger')
            return redirect(url_for('academic.manage_allocations'))
        
        faculty_user_id = faculty_row[0]
        
        cursor.execute("""
            UPDATE faculty_allocations 
            SET faculty_id = %s, subject_id = %s, class_id = %s, division_id = %s,
                semester_id = %s, course_batch_id = %s, allocated_hours = %s,
                workload_percentage = %s, is_primary = %s, allocation_type = %s,
                start_date = %s, end_date = %s, notes = %s
            WHERE id = %s
        """, (faculty_user_id, subject_id, class_id, division_id, semester_id, course_batch_id,
              allocated_hours, workload_percentage, is_primary, allocation_type,
              start_date, end_date, notes, id))
        
        connection.commit()
        flash('Faculty allocation updated successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error updating allocation: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_allocations'))

@academic_bp.route('/allocations/delete/<int:id>', methods=['POST'])
@has_permission('allocations_delete')
def delete_allocation(id):
    """Delete faculty allocation"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        cursor.execute("DELETE FROM faculty_allocations WHERE id = %s", (id,))
        connection.commit()
        flash('Faculty allocation deleted successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error deleting allocation: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('academic.manage_allocations'))

# ============================================================================
# HELPER API ROUTES FOR CASCADING DROPDOWNS
# ============================================================================

@academic_bp.route('/api/courses/by-department/<int:department_id>')
@has_permission('courses_view_course')
def api_courses_by_department(department_id):
    """Get courses for a department"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT id, name, code, program 
            FROM courses 
            WHERE department_id = %s AND is_active = TRUE 
            ORDER BY name
        """, (department_id,))
        courses = cursor.fetchall()
        
        return jsonify(courses)
    
    finally:
        cursor.close()
        connection.close()

@academic_bp.route('/api/subjects/by-course/<int:course_id>')
@has_permission('subjects_view_subject')
def api_subjects_by_course(course_id):
    """Get subjects for a course"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT id, name, course_code, credits, course_type 
            FROM subjects 
            WHERE course_id = %s 
            ORDER BY name
        """, (course_id,))
        subjects = cursor.fetchall()
        
        return jsonify(subjects)
    
    finally:
        cursor.close()
        connection.close()

@academic_bp.route('/api/faculty/by-department/<int:department_id>')
@has_permission('faculty_view_faculty')
def api_faculty_by_department(department_id):
    """Get faculty for a department"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT id, name, email, designation 
            FROM faculty 
            WHERE department_id = %s AND is_active = TRUE 
            ORDER BY name
        """, (department_id,))
        faculty = cursor.fetchall()
        
        return jsonify(faculty)
    
    finally:
        cursor.close()
        connection.close()

@academic_bp.route('/api/semesters/by-year/<int:academic_year_id>')
@has_permission('semesters_view')
def api_semesters_by_year(academic_year_id):
    """Get semesters for an academic year"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT id, semester_number, semester_name, is_current 
            FROM semesters 
            WHERE academic_year_id = %s 
            ORDER BY semester_number
        """, (academic_year_id,))
        semesters = cursor.fetchall()
        
        return jsonify(semesters)
    
    finally:
        cursor.close()
        connection.close()

@academic_bp.route('/api/batches/by-course/<int:course_id>')
@has_permission('batches_view')
def api_batches_by_course(course_id):
    """Get batches for a course"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT id, batch_name, start_year, end_year, current_semester 
            FROM course_batches 
            WHERE course_id = %s AND is_active = TRUE 
            ORDER BY start_year DESC
        """, (course_id,))
        batches = cursor.fetchall()
        
        return jsonify(batches)
    
    finally:
        cursor.close()
        connection.close()
