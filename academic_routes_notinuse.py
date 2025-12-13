from flask import Blueprint, render_template, redirect, url_for, session, request, flash, jsonify
from functools import wraps
from app import mysql

academic_bp = Blueprint('academic', __name__, url_prefix='/admin/academic')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session or session['role'] not in ('Admin', 'Super Admin'):
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for('auth.admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@academic_bp.route('/')
@admin_required
def manage_academics():
    """Main academic management dashboard"""
    cursor = mysql.connection.cursor()
    
    # Get current academic year
    cursor.execute("SELECT id, name FROM academic_years WHERE is_current = 1 LIMIT 1")
    current_year = cursor.fetchone()
    
    # Get current semester
    cursor.execute("SELECT id, semester_name FROM semesters WHERE is_current = 1 LIMIT 1")
    current_semester = cursor.fetchone()
    
    # Get all academic years
    cursor.execute("SELECT id, name, start_date, end_date, is_current FROM academic_years ORDER BY start_date DESC")
    academic_years = cursor.fetchall()
    
    # Get all semesters for current year
    if current_year:
        cursor.execute("""
            SELECT id, semester_number, semester_name, start_date, end_date, is_current 
            FROM semesters WHERE academic_year_id = %s ORDER BY semester_number
        """, (current_year[0],))
        semesters = cursor.fetchall()
    else:
        semesters = []
    
    # Get courses
    cursor.execute("SELECT id, name, program, duration_years, total_semesters FROM courses WHERE is_active = 1")
    courses = cursor.fetchall()
    
    # Get departments
    cursor.execute("SELECT id, name FROM departments ORDER BY name")
    departments = cursor.fetchall()
    
    # Get course-department mapping
    dept_courses = {}
    for dept in departments:
        cursor.execute("SELECT id, name FROM courses WHERE department_id = %s", (dept[0],))
        dept_courses[dept[0]] = cursor.fetchall()
    
    # Get course batches
    cursor.execute("""
        SELECT cb.id, cb.batch_name, cb.start_year, cb.end_year, cb.total_students, cb.current_semester,
               c.name as course_name, c.program
        FROM course_batches cb
        LEFT JOIN courses c ON cb.course_id = c.id
        WHERE cb.is_active = 1
        ORDER BY cb.start_year DESC, c.name
    """)
    course_batches = cursor.fetchall()
    
    # Get subjects with basic info only
    cursor.execute("""
        SELECT s.id, s.name, s.course_code, s.course_type, s.theory_practical, 
               s.credits, s.theory_credits, s.practical_credits, s.marks,
               s.lectures_per_week, s.is_elective,
               c.name as course_name, c.program
        FROM subjects s
        LEFT JOIN courses c ON s.course_id = c.id
        ORDER BY c.name, s.name
    """)
    subjects = cursor.fetchall()
    
    # Get faculty allocations
    cursor.execute("""
        SELECT fa.id, f.name as faculty_name, s.name as subject_name, s.course_code,
               fa.allocated_hours, fa.workload_percentage, fa.is_primary,
               c.name as course_name
        FROM faculty_allocations fa
        LEFT JOIN faculty f ON fa.faculty_id = f.id
        LEFT JOIN subjects s ON fa.subject_id = s.id  
        LEFT JOIN courses c ON s.course_id = c.id
        ORDER BY f.name, s.name
    """)
    faculty_allocations = cursor.fetchall()
    
    # Create subject-faculty mapping for template
    subject_faculty = {}
    for alloc in faculty_allocations:
        subject_id = alloc[0]  # This might need adjustment based on actual query structure
        if subject_id not in subject_faculty:
            subject_faculty[subject_id] = []
        subject_faculty[subject_id].append(alloc)
    
    # Get statistics
    stats = {
        'total_courses': len(courses),
        'total_subjects': len(subjects),
        'total_batches': len(course_batches),
        'total_allocations': len(faculty_allocations)
    }
    
    cursor.close()
    
    return render_template('admin/academic_simple.html',
                         current_year=current_year,
                         current_semester=current_semester,
                         academic_years=academic_years,
                         semesters=semesters,
                         courses=courses,
                         departments=departments,
                         dept_courses=dept_courses,
                         course_batches=course_batches,
                         subjects=subjects,
                         faculty_allocations=faculty_allocations,
                         subject_faculty=subject_faculty,
                         stats=stats)

@academic_bp.route('/academic-years')
@admin_required
def manage_academic_years():
    """Manage academic years"""
    return "Academic Years Management - Coming Soon!"
@admin_required
def manage_academic_years():
    """Manage academic years"""
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT id, name, start_date, end_date, is_current, created_at FROM academic_years ORDER BY start_date DESC")
    academic_years = cursor.fetchall()
    cursor.close()
    
    return render_template('admin/academic_years.html', academic_years=academic_years)

@academic_bp.route('/semesters')
@admin_required 
def manage_semesters():
    """Manage semesters"""
    cursor = mysql.connection.cursor()
    
    # Get semesters with academic year info
    cursor.execute("""
        SELECT s.id, s.semester_number, s.semester_name, s.start_date, s.end_date, 
               s.is_current, s.min_credits, s.max_credits,
               ay.name as academic_year_name
        FROM semesters s
        LEFT JOIN academic_years ay ON s.academic_year_id = ay.id
        ORDER BY ay.start_date DESC, s.semester_number
    """)
    semesters = cursor.fetchall()
    
    # Get academic years for dropdown
    cursor.execute("SELECT id, name FROM academic_years ORDER BY start_date DESC")
    academic_years = cursor.fetchall()
    
    cursor.close()
    
    return render_template('admin/semesters.html', semesters=semesters, academic_years=academic_years)

@academic_bp.route('/subjects')
@admin_required
def manage_subjects():
    """Manage subjects"""
    cursor = mysql.connection.cursor()
    
    # Get subjects with course info
    cursor.execute("""
        SELECT s.id, s.name, s.course_code, s.course_type, s.theory_practical,
               s.credits, s.theory_credits, s.practical_credits, s.marks,
               s.lectures_per_week, s.is_elective, s.description,
               c.name as course_name, c.program
        FROM subjects s
        LEFT JOIN courses c ON s.course_id = c.id
        ORDER BY c.name, s.name
    """)
    subjects = cursor.fetchall()
    
    # Get courses for dropdown
    cursor.execute("SELECT id, name, program FROM courses WHERE is_active = 1 ORDER BY name")
    courses = cursor.fetchall()
    
    # Get classes for dropdown  
    cursor.execute("SELECT id, name FROM classes ORDER BY name")
    classes = cursor.fetchall()
    
    cursor.close()
    
    return render_template('admin/subjects.html', subjects=subjects, courses=courses, classes=classes)

@academic_bp.route('/course-batches')
@admin_required
def manage_course_batches():
    """Manage course batches"""
    cursor = mysql.connection.cursor()
    
    # Get course batches with course info
    cursor.execute("""
        SELECT cb.id, cb.batch_name, cb.start_year, cb.end_year, cb.total_students,
               cb.current_semester, cb.is_active,
               c.name as course_name, c.program, c.duration_years,
               ay.name as academic_year_name
        FROM course_batches cb
        LEFT JOIN courses c ON cb.course_id = c.id
        LEFT JOIN academic_years ay ON cb.academic_year_id = ay.id
        ORDER BY cb.start_year DESC, c.name
    """)
    course_batches = cursor.fetchall()
    
    # Get courses for dropdown
    cursor.execute("SELECT id, name, program FROM courses WHERE is_active = 1 ORDER BY name")
    courses = cursor.fetchall()
    
    # Get academic years for dropdown
    cursor.execute("SELECT id, name FROM academic_years ORDER BY start_date DESC")
    academic_years = cursor.fetchall()
    
    cursor.close()
    
    return render_template('admin/course_batches.html', 
                         course_batches=course_batches, 
                         courses=courses, 
                         academic_years=academic_years)

# API endpoints for AJAX calls
@academic_bp.route('/api/courses')
@admin_required
def api_courses():
    """Get all courses"""
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT id, name, program FROM courses WHERE is_active = 1 ORDER BY name")
    courses = cursor.fetchall()
    cursor.close()
    
    return jsonify([{
        'id': course[0],
        'name': course[1], 
        'program': course[2]
    } for course in courses])

@academic_bp.route('/api/academic-years')
@admin_required
def api_academic_years():
    """Get all academic years"""
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT id, name, is_current FROM academic_years ORDER BY start_date DESC")
    years = cursor.fetchall()
    cursor.close()
    
    return jsonify([{
        'id': year[0],
        'name': year[1],
        'is_current': bool(year[2])
    } for year in years])

@academic_bp.route('/api/semesters/<int:academic_year_id>')
@admin_required
def api_semesters(academic_year_id):
    """Get semesters for an academic year"""
    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT id, semester_number, semester_name, is_current 
        FROM semesters 
        WHERE academic_year_id = %s 
        ORDER BY semester_number
    """, (academic_year_id,))
    semesters = cursor.fetchall()
    cursor.close()
    
    return jsonify([{
        'id': semester[0],
        'semester_number': semester[1],
        'semester_name': semester[2],
        'is_current': bool(semester[3])
    } for semester in semesters])

# Simple add/edit/delete routes (basic implementations)
@academic_bp.route('/add-academic-year', methods=['POST'])
@admin_required
def add_academic_year():
    """Add new academic year"""
    name = request.form.get('name')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    is_current = 'is_current' in request.form
    description = request.form.get('description', '')
    
    cursor = mysql.connection.cursor()
    
    # If this is set as current, unset all others
    if is_current:
        cursor.execute("UPDATE academic_years SET is_current = 0")
    
    cursor.execute("""
        INSERT INTO academic_years (name, start_date, end_date, is_current, description) 
        VALUES (%s, %s, %s, %s, %s)
    """, (name, start_date, end_date, is_current, description))
    
    mysql.connection.commit()
    cursor.close()
    
    flash('Academic year added successfully!', 'success')
    return redirect(url_for('academic.manage_academic_years'))

@academic_bp.route('/add-subject', methods=['POST'])
@admin_required
def add_subject():
    """Add new subject"""
    name = request.form.get('name')
    course_code = request.form.get('course_code')
    course_id = request.form.get('course_id')
    class_id = request.form.get('class_id') or None
    course_type = request.form.get('course_type', 'Core')
    theory_practical = request.form.get('theory_practical', 'Theory')
    credits = float(request.form.get('credits', 3.0))
    theory_credits = float(request.form.get('theory_credits', 0))
    practical_credits = float(request.form.get('practical_credits', 0))
    marks = int(request.form.get('marks', 100))
    lectures_per_week = int(request.form.get('lectures_per_week', 3))
    is_elective = 'is_elective' in request.form
    description = request.form.get('description', '')
    
    cursor = mysql.connection.cursor()
    cursor.execute("""
        INSERT INTO subjects (
            name, course_code, course_id, class_id, course_type, theory_practical,
            credits, theory_credits, practical_credits, marks, lectures_per_week,
            is_elective, description
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (name, course_code, course_id, class_id, course_type, theory_practical,
          credits, theory_credits, practical_credits, marks, lectures_per_week,
          is_elective, description))
    
    mysql.connection.commit()
    cursor.close()
    
    flash('Subject added successfully!', 'success')
    return redirect(url_for('academic.manage_subjects'))

# Placeholder routes for other functionality
@academic_bp.route('/timetable-generation')
@admin_required
def timetable_generation():
    """Timetable generation interface"""
    return render_template('admin/timetable_generation.html')

@academic_bp.route('/reports')
@admin_required
def academic_reports():
    """Academic reports and analytics"""
    cursor = mysql.connection.cursor()
    
    # Basic statistics
    cursor.execute("SELECT COUNT(*) FROM courses WHERE is_active = 1")
    total_courses = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM subjects")
    total_subjects = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM course_batches WHERE is_active = 1")
    total_batches = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM faculty_allocations")
    total_allocations = cursor.fetchone()[0]
    
    stats = {
        'total_courses': total_courses,
        'total_subjects': total_subjects,
        'total_batches': total_batches,
        'total_allocations': total_allocations
    }
    
    cursor.close()
    
    return render_template('admin/academic_reports.html', stats=stats)