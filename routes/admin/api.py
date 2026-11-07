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

from routes.admin_utils import admin_required
from services.timetable.generator import generate_timetable_for_class
from services.admin_api import (
    coverage_subjects,
    eligible_subject_payload,
    faculty_for_subject,
    list_classes,
    list_divisions,
    quality_sample_counts,
)

api_bp = Blueprint('api', __name__, url_prefix='/admin/api')


@api_bp.route('/classes')
@admin_required
def get_classes():
    """Get classes for a given course (or all classes if no course specified)"""
    course_id = request.args.get('course_id')
    classes = list_classes()
    return jsonify([{'id': item['id'], 'name': item['name']} for item in classes])


@api_bp.route('/divisions')
@admin_required
def get_divisions():
    """Get divisions for a given class (or all divisions if no class specified)"""
    class_id = request.args.get('class_id')
    divisions = list_divisions()
    return jsonify([{'id': item['id'], 'name': item['name']} for item in divisions])


@api_bp.route('/faculty-by-subject')
@admin_required
def get_faculty_by_subject():
    """Get faculty allocated to a specific subject"""
    subject_id = request.args.get('subject_id')
    if not subject_id:
        return jsonify({'error': 'subject_id is required'}), 400
    faculty = faculty_for_subject(subject_id)
    return jsonify([{
        'id': item['user_id'],
        'name': item['name'],
        'is_primary': bool(item['is_primary'])
    } for item in faculty])


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

    return jsonify(eligible_subject_payload(course_id, class_id, division_id))


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

    subjects, scheduled_counts = coverage_subjects(course_id, class_id, division_id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Subject', 'Required Slots (est.)', 'Scheduled Slots'])

    for subject in subjects:
        lpw = int(subject['lpw'] or 0)
        ph_minutes = float(subject['phw'] or 0.0) * 60.0
        practical_slots = int(_math.ceil(ph_minutes / max(1, lecture_minutes))) if ph_minutes > 0 else 0
        required_total = lpw + practical_slots
        scheduled = scheduled_counts.get(subject['id'], 0)
        writer.writerow([subject['name'], required_total, scheduled])

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
    counts = quality_sample_counts()

    model_exists = bool(model_path and os.path.exists(model_path))
    last_retrain_at = None
    model_metadata = {}

    if model_exists:
        try:
            last_retrain_at = datetime.fromtimestamp(os.path.getmtime(model_path))
            from ml_models.scoring.learned_predictor import _load_model  # pylint: disable=protected-access

            loaded_model = _load_model(model_path=model_path)
            if isinstance(loaded_model, dict):
                model_metadata = {
                    'model_type': loaded_model.get('model_type'),
                    'training_accuracy': loaded_model.get('training_accuracy'),
                    'sample_count': loaded_model.get('sample_count'),
                }
        except Exception as model_error:
            current_app.logger.debug('Unable to read quality model metadata: %s', str(model_error))

    last_run_at = counts['last_run_at']
    response = {
        'status': 'ok',
        'model_source': 'learned_predictor' if model_exists else 'rule_fallback',
        'model_path': model_path,
        'retrain_interval_minutes': interval_minutes,
        'last_retrain_at': last_retrain_at.isoformat() if last_retrain_at else None,
        'training_samples': counts['training_samples'],
        'accepted_samples': counts['accepted_samples'],
        'rejected_samples': counts['rejected_samples'],
        'last_generation_run_at': last_run_at.isoformat() if last_run_at else None,
        'last_generation_quality_score': counts['last_run_score'],
        'model_metadata': model_metadata,
    }
    return jsonify(response)
