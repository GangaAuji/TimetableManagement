"""
Admin API Routes
Provides JSON endpoints for dynamic data loading, previews, and exports
"""

from flask import Blueprint, request, jsonify, make_response, current_app
from datetime import datetime
import io
import csv
import math as _math
import os
from flask import session

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
        return jsonify([{'id': c['id'], 'name': c['name']} for c in classes])
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
        return jsonify([{'id': d['id'], 'name': d['name']} for d in divisions])
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
            'id': f['user_id'],
            'name': f['name'],
            'is_primary': bool(f['is_primary'])
        } for f in faculty])
    finally:

        cursor.close()

        connection.close()


@api_bp.route('/generate_preview', methods=['POST'])
@admin_required
def generate_preview():
    """Generate a preview of the timetable without saving to database"""
    data = request.get_json()

    try:
        current_app.logger.info('Preview request received by user_id=%s; payload keys=%s', session.get('user_id'), list((data or {}).keys()))
    except Exception:
        current_app.logger.info('Preview request received; unable to log payload keys')

    course_id = data.get('course_id') or data.get('course')
    class_id = data.get('class_id') or data.get('class')
    division_id = data.get('division_id') or data.get('division')
    week_start_date_str = data.get('week_start_date')
    day_start_str = data.get('day_start')
    day_end_str = data.get('day_end')
    lecture_minutes = data.get('lecture_minutes')
    break_start_str = data.get('break_start')
    break_duration = data.get('break_duration')
    working_days_raw = data.get('working_days', '')

    # Validate required fields
    if not all([course_id, class_id, division_id]):
        current_app.logger.warning('Preview validation failed: missing required identifiers (course/class/division)')
        return jsonify({
            'status': 'error',
            'message': 'course_id, class_id, and division_id are required'
        }), 400

    if isinstance(working_days_raw, list):
        working_days = [str(d).strip() for d in working_days_raw if str(d).strip()]
    else:
        working_days = [d.strip() for d in str(working_days_raw or '').split(',') if d.strip()] or None

    result = generate_timetable_for_class(
        course_id,
        class_id,
        division_id,
        week_start_date=week_start_date_str,
        day_start=day_start_str or '09:00',
        day_end=day_end_str or '15:00',
        lecture_minutes=lecture_minutes,
        break_start=break_start_str,
        break_duration=break_duration,
        working_days=working_days,
        preview_only=True,
        candidate_count=5,
        created_by=session.get('user_id'),
    )

    status = result.get('status')
    current_app.logger.info(
        'Preview result status=%s assigned=%s unassigned=%s quality_score=%s',
        status,
        len(result.get('assigned') or []),
        len(result.get('unassigned') or []),
        result.get('quality_score'),
    )
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


@api_bp.route('/quality_model_status', methods=['GET'])
@admin_required
def quality_model_status():
    """Return quality-model health details for admin UI."""

    model_path = current_app.config.get('QUALITY_MODEL_PATH')
    interval_minutes = int(current_app.config.get('QUALITY_MODEL_RETRAIN_INTERVAL_MINUTES', 180) or 180)

    training_samples = 0
    accepted_samples = 0
    rejected_samples = 0
    last_run_at = None
    last_run_score = None

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        try:
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_samples,
                    SUM(CASE WHEN is_selected = 1 THEN 1 ELSE 0 END) AS accepted_samples,
                    SUM(CASE WHEN is_selected = 0 THEN 1 ELSE 0 END) AS rejected_samples
                FROM timetable_quality_candidates
                """
            )
            sample_row = cursor.fetchone() or {}
            training_samples = int(sample_row.get('total_samples') or 0)
            accepted_samples = int(sample_row.get('accepted_samples') or 0)
            rejected_samples = int(sample_row.get('rejected_samples') or 0)
        except Exception:
            # Candidates table may not exist yet in older databases.
            training_samples = 0
            accepted_samples = 0
            rejected_samples = 0

        try:
            cursor.execute(
                """
                SELECT created_at, quality_score
                FROM timetable_quality_runs
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            latest_row = cursor.fetchone() or {}
            last_run_at = latest_row.get('created_at')
            if latest_row.get('quality_score') is not None:
                last_run_score = float(latest_row.get('quality_score'))
        except Exception:
            last_run_at = None
            last_run_score = None
    finally:

        cursor.close()

        connection.close()

    model_exists = bool(model_path and os.path.exists(model_path))
    last_retrain_at = None
    model_metadata = {}

    if model_exists:
        try:
            last_retrain_at = datetime.fromtimestamp(os.path.getmtime(model_path))
            from ml.scoring.learned_predictor import _load_model  # pylint: disable=protected-access

            loaded_model = _load_model(model_path=model_path)
            if isinstance(loaded_model, dict):
                model_metadata = {
                    'model_type': loaded_model.get('model_type'),
                    'training_accuracy': loaded_model.get('training_accuracy'),
                    'sample_count': loaded_model.get('sample_count'),
                }
        except Exception as model_error:
            current_app.logger.debug('Unable to read quality model metadata: %s', str(model_error))

    response = {
        'status': 'ok',
        'model_source': 'learned_predictor' if model_exists else 'rule_fallback',
        'model_path': model_path,
        'retrain_interval_minutes': interval_minutes,
        'last_retrain_at': last_retrain_at.isoformat() if last_retrain_at else None,
        'training_samples': training_samples,
        'accepted_samples': accepted_samples,
        'rejected_samples': rejected_samples,
        'last_generation_run_at': last_run_at.isoformat() if last_run_at else None,
        'last_generation_quality_score': last_run_score,
        'model_metadata': model_metadata,
    }
    return jsonify(response)
