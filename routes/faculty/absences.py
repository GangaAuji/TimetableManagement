from flask import session, request, jsonify, redirect, url_for, flash
from datetime import datetime, date
from .teacher import teacher_bp, teacher_required
from services.teacher_portal import add_absence, load_absences, remove_absence, submit_absence

# --- Absences JSON (AJAX) ---
@teacher_bp.route('/absences', methods=['GET', 'POST'])
@teacher_required
def absences():
    faculty_id = session.get('faculty_id')
    if request.method == 'GET':
        return jsonify({'data': load_absences(faculty_id)})

    data = request.get_json(silent=True) or {}
    absence_date_str = data.get('absence_date') or request.form.get('absence_date')
    reason = data.get('reason') or request.form.get('reason')
    if add_absence(faculty_id, absence_date_str, reason) == 'missing':
        return jsonify({'ok': False, 'error': 'absence_date required'}), 400
    return jsonify({'ok': True})


@teacher_bp.route('/absences/<int:absence_id>', methods=['DELETE'])
@teacher_required
def delete_absence(absence_id):
    result = remove_absence(session.get('faculty_id'), absence_id)
    if result == 'missing':
        return jsonify({'ok': False, 'error': 'Not found'}), 404
    if result == 'processed':
        return jsonify({'ok': False, 'error': 'Cannot delete processed absence'}), 400
    return jsonify({'ok': True})


@teacher_bp.route('/mark_absence', methods=['POST'])
@teacher_required
def mark_absence():
    absence_date_str = request.form.get('absence_date')
    if not absence_date_str:
        flash("Absence date is required.", "danger")
        return redirect(url_for('teacher.dashboard'))
    if submit_absence(session.get('faculty_id'), absence_date_str, request.form.get('reason')) == 'missing':
        return redirect(url_for('auth.logout'))
    return redirect(url_for('teacher.dashboard'))
