from flask import session, request, redirect, url_for
from ui.pages import render_template
from .teacher import teacher_bp, teacher_required
from services.teacher_portal import load_availability, save_availability

# --- Availability ---
@teacher_bp.route('/availability', methods=['GET', 'POST'])
@teacher_required
def availability():
    faculty_id = session.get('faculty_id')
    if request.method == 'POST':
        result = save_availability(faculty_id, request.form)
        if result == 'missing':
            return redirect(url_for('teacher.dashboard'))
        return redirect(url_for('teacher.availability'))
    slots = load_availability(faculty_id)
    if slots == 'missing':
        return redirect(url_for('teacher.dashboard'))
    return render_template('teacher/availability.html', avail_all_slots=slots)
