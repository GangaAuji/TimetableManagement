from flask import session, redirect, url_for, request
from ui.pages import render_template
from datetime import datetime
from .teacher import teacher_bp, teacher_required
from services.teacher_portal import load_proxy_form, load_proxy_page, submit_proxy_request

# --- Proxy requests: page + create ---
@teacher_bp.route('/proxy-requests')
@teacher_required
def proxy_requests():
    page = load_proxy_page(session.get('faculty_id'))
    if page == 'missing':
        return redirect(url_for('teacher.dashboard'))
    return render_template(
        'teacher/proxy_requests.html',
        logs=page['logs'],
        lectures=page['lectures'],
        proxy_map=page['proxy_map'],
    )


@teacher_bp.route('/request-proxy', methods=['GET', 'POST'])
@teacher_required
def request_proxy():
    faculty_id = session.get('faculty_id')
    if request.method == 'POST':
        result = submit_proxy_request(
            faculty_id,
            request.form.get('timetable_id', type=int),
            request.form.get('proxy_faculty_id', type=int),
            request.form.get('absence_date'),
        )
        if result == 'missing':
            return redirect(url_for('teacher.dashboard'))
        if result in ('fields', 'invalid'):
            return redirect(url_for('teacher.request_proxy'))
        return redirect(url_for('teacher.proxy_requests'))
    page = load_proxy_form(faculty_id)
    if page == 'missing':
        return redirect(url_for('teacher.dashboard'))
    return render_template('teacher/request_proxy.html', lectures=page['lectures'], proxy_map=page['proxy_map'])
