"""
Admin API Routes
Provides JSON endpoints for dynamic data loading, previews, and exports
"""

from flask import Blueprint, request, jsonify, make_response
from datetime import datetime
import io
import csv
import math as _math

from database import get_db_connection
from routes.admin_utils import admin_required
from routes.timetable_algorithm import generate_timetable_for_class

api_bp = Blueprint('api', __name__, url_prefix='/admin/api')


@api_bp.route('/classes')
@admin_required
def get_classes():
    """Get classes for a given course (or all classes if no course specified)"""
    course_id = request.args.get('course_id')
    
    connection = get_db_connection()

    
    cursor = connection.cursor(dictionary=True)
    try:
        # Note: classes table doesn't have direct course_id relationship
        # Classes are generic (e.g., "FY", "SY", "TY") and used across courses
        # Return all classes since they're not course-specific
        cursor.execute("SELECT id, name FROM classes ORDER BY display_order, name")
        classes = cursor.fetchall()
        return jsonify([{'id': c[0], 'name': c[1]} for c in classes])
    finally:

        cursor.close()

        connection.close()


@api_bp.route('/divisions')
@admin_required
def get_divisions():
    """Get divisions for a given class (or all divisions if no class specified)"""
    class_id = request.args.get('class_id')
    
    connection = get_db_connection()

    
    cursor = connection.cursor(dictionary=True)
    try:
        # Note: divisions table doesn't have class_id relationship
        # Divisions are generic (e.g., "A", "B", "C", "D") and used across all classes
        # Return all divisions since they're not class-specific
        cursor.execute("SELECT id, name FROM divisions ORDER BY name")
        divisions = cursor.fetchall()
        return jsonify([{'id': d[0], 'name': d[1]} for d in divisions])
    finally:

        cursor.close()

        connection.close()


@api_bp.route('/faculty-by-subject')
@admin_required
def get_faculty_by_subject():
    """Get faculty allocated to a specific subject"""
    subject_id = request.args.get('subject_id')
    if not subject_id:
        return jsonify({'error': 'subject_id is required'}), 400
    
    connection = get_db_connection()

    
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT f.user_id, f.name, fa.is_primary
            FROM faculty_allocations fa
            JOIN faculty f ON fa.faculty_id = f.user_id
            WHERE fa.subject_id = %s AND f.is_active = 1
            ORDER BY fa.is_primary DESC, f.name
        """, (subject_id,))
        faculty = cursor.fetchall()
        return jsonify([{
            'id': f[0],
            'name': f[1],
            'is_primary': bool(f[2])
        } for f in faculty])
    finally:

        cursor.close()

        connection.close()


@api_bp.route('/generate_preview', methods=['POST'])
@admin_required
def generate_preview():
    """Generate a preview of the timetable without saving to database"""
    data = request.get_json()
    
    course_id = data.get('course_id')
    class_id = data.get('class_id')
    division_id = data.get('division_id')
    week_start_date_str = data.get('week_start_date')
    day_start_str = data.get('day_start')
    day_end_str = data.get('day_end')
    lecture_minutes = data.get('lecture_minutes')
    break_start_str = data.get('break_start')
    break_duration = data.get('break_duration')
    working_days_str = data.get('working_days', '')

    # Validate required fields
    if not all([course_id, class_id, division_id]):
        return jsonify({
            'status': 'error',
            'message': 'course_id, class_id, and division_id are required'
        }), 400

    # Parse dates and times
    try:
        week_start_date = datetime.strptime(week_start_date_str, '%Y-%m-%d').date() if week_start_date_str else None
    except Exception:
        week_start_date = None

    try:
        day_start = datetime.strptime(day_start_str, '%H:%M').time() if day_start_str else None
    except Exception:
        day_start = None

    try:
        day_end = datetime.strptime(day_end_str, '%H:%M').time() if day_end_str else None
    except Exception:
        day_end = None

    try:
        break_start = datetime.strptime(break_start_str, '%H:%M').time() if break_start_str else None
    except Exception:
        break_start = None

    try:
        working_days = [d.strip() for d in working_days_str.split(',') if d.strip()] if working_days_str else None
    except Exception:
        working_days = None

    result = generate_timetable_for_class(
        course_id,
        class_id,
        division_id,
        week_start_date=week_start_date,
        day_start=day_start,
        day_end=day_end,
        lecture_minutes=lecture_minutes,
        break_start=break_start,
        break_duration=break_duration,
        working_days=working_days,
        preview_only=True,
    )

    status = result.get('status')
    if status in ('error',):
        return jsonify(result), 400
    return jsonify(result)


@api_bp.route('/eligible_subjects', methods=['GET'])
@admin_required
def api_eligible_subjects():
    """
    Return eligible subjects for a given course/class/division and which have matching allocations.
    Also returns course subjects that are missing allocations for the selected class/division.
    """
    course_id = request.args.get('course_id')
    class_id = request.args.get('class_id')
    division_id = request.args.get('division_id')

    if not course_id or not class_id or not division_id:
        return jsonify({
            'status': 'error',
            'message': 'course_id, class_id and division_id are required'
        }), 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        # Eligible subjects (at least one allocation that matches class/division)
        cursor.execute(
            """
            SELECT DISTINCT
                s.id,
                s.name,
                s.course_code,
                s.theory_practical,
                COALESCE(s.lectures_per_week, 0) AS lectures_per_week,
                COALESCE(s.practical_hours_per_week, 0) AS practical_hours_per_week
            FROM subjects s
            JOIN faculty_allocations fa ON fa.subject_id = s.id
            WHERE s.course_id = %s
              AND (fa.class_id IS NULL OR fa.class_id = %s)
              AND (fa.division_id IS NULL OR fa.division_id = %s)
            ORDER BY s.name
            """,
            (course_id, class_id, division_id),
        )
        eligible_rows = cursor.fetchall()

        eligible_subject_ids = [r['id'] for r in eligible_rows]

        faculty_map = {sid: [] for sid in eligible_subject_ids}
        if eligible_subject_ids:
            placeholder = ','.join(['%s'] * len(eligible_subject_ids))
            cursor.execute(
                f"""
                SELECT fa.subject_id, f.name AS faculty_name, COALESCE(fa.is_primary, 1) AS is_primary
                FROM faculty_allocations fa
                JOIN faculty f ON f.user_id = fa.faculty_id
                WHERE fa.subject_id IN ({placeholder})
                  AND (fa.class_id IS NULL OR fa.class_id = %s)
                  AND (fa.division_id IS NULL OR fa.division_id = %s)
                ORDER BY fa.subject_id, is_primary DESC, f.name
                """,
                (*eligible_subject_ids, class_id, division_id),
            )
            for row in cursor.fetchall():
                faculty_map[row['subject_id']].append({
                    'name': row['faculty_name'],
                    'is_primary': bool(row['is_primary']),
                })

        eligible = []
        for r in eligible_rows:
            eligible.append({
                'id': r['id'],
                'name': r['name'],
                'course_code': r['course_code'],
                'theory_practical': r['theory_practical'],
                'lectures_per_week': int(r['lectures_per_week'] or 0),
                'practical_hours_per_week': float(r['practical_hours_per_week'] or 0),
                'faculty': faculty_map.get(r['id'], []),
            })

        # Subjects in this course that are not eligible for this class/division (missing allocation)
        cursor.execute(
            """
            SELECT s.id, s.name, s.course_code
            FROM subjects s
            WHERE s.course_id = %s
              AND (s.class_id IS NULL OR s.class_id = %s)
            ORDER BY s.name
            """,
            (course_id, class_id),
        )
        all_course_subjects = cursor.fetchall()
        missing = [
            {'id': r['id'], 'name': r['name'], 'course_code': r['course_code']}
            for r in all_course_subjects if r['id'] not in eligible_subject_ids
        ]

        return jsonify({
            'status': 'ok',
            'eligible': eligible,
            'missing': missing,
        })
    finally:

        cursor.close()

        connection.close()


@api_bp.route('/coverage.csv', methods=['GET'])
@admin_required
def coverage_csv():
    """
    Export coverage for the selected Course/Class/Division.
    Computes required total slots per subject (lectures_per_week + practical hours converted to slots)
    and compares with scheduled count in timetable for that class/division.
    """
    course_id = request.args.get('course_id') or request.args.get('course')
    class_id = request.args.get('class_id') or request.args.get('class')
    division_id = request.args.get('division_id') or request.args.get('division')
    
    # Default lecture duration for conversion when not otherwise specified
    try:
        lecture_minutes = int(request.args.get('lecture_minutes', 45))
    except Exception:
        lecture_minutes = 45

    if not course_id or not class_id or not division_id:
        return jsonify({
            'status': 'error',
            'message': 'course_id, class_id, division_id are required'
        }), 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        # Subjects applicable to this course/class
        cursor.execute(
            """
            SELECT s.id, s.name, 
                   COALESCE(s.lectures_per_week,0) AS lpw, 
                   COALESCE(s.practical_hours_per_week,0) AS phw
            FROM subjects s
            WHERE s.course_id = %s AND (s.class_id IS NULL OR s.class_id = %s)
            ORDER BY s.name
            """,
            (course_id, class_id),
        )
        subjects = cursor.fetchall()
        subject_ids = [s['id'] for s in subjects]

        scheduled_counts = {}
        if subject_ids:
            placeholder = ','.join(['%s'] * len(subject_ids))
            cursor.execute(
                f"""
                SELECT subject_id, COUNT(*) AS cnt
                FROM timetable
                WHERE course_id = %s AND class_id = %s AND division_id = %s 
                  AND subject_id IN ({placeholder})
                GROUP BY subject_id
                """,
                (int(course_id), int(class_id), int(division_id), *subject_ids),
            )
            for row in cursor.fetchall():
                scheduled_counts[int(row['subject_id'])] = int(row['cnt'])
    finally:

        cursor.close()

        connection.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Subject', 'Required Slots (est.)', 'Scheduled Slots'])

    for s in subjects:
        lpw = int(s['lpw'] or 0)
        ph_minutes = float(s['phw'] or 0.0) * 60.0
        practical_slots = int(_math.ceil(ph_minutes / max(1, lecture_minutes))) if ph_minutes > 0 else 0
        required_total = lpw + practical_slots
        scheduled = scheduled_counts.get(s['id'], 0)
        writer.writerow([s['name'], required_total, scheduled])

    resp = make_response(output.getvalue())
    resp.headers['Content-Disposition'] = f'attachment; filename=coverage_class_{course_id}_{class_id}_{division_id}.csv'
    resp.headers['Content-Type'] = 'text/csv'
    return resp
