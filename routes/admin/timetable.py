from flask import Blueprint, request, session
from ui.pages import render_template
from security import has_permission
from services.admin_timetable import manage_timetable, prepare_generate_page

timetable_bp = Blueprint('timetable', __name__, url_prefix='/admin/timetable')


@timetable_bp.route('/generate', methods=['GET', 'POST'])
@has_permission('timetable_generate')
def generate_timetable():
    page = prepare_generate_page(request.method, request.form, session.get('user_id'))
    return render_template(
        'admin/generate.html',
        courses=page['courses'],
        classes=page['classes'],
        divisions=page['divisions'],
        form_state=page['form_state'],
        generation_result=page['generation_result'],
        selected_course=page['selected_course'],
        selected_class=page['selected_class'],
        selected_division=page['selected_division'],
    )

# --- View & Manage Timetable ---
@timetable_bp.route('/', methods=['GET', 'POST'])
@has_permission('timetable_change')
def timetable_manage():
    page = manage_timetable(request.method, request.form, request.values)
    return render_template(
        'admin/timetable_manage.html',
        courses=page['courses'],
        classes=page['classes'],
        divisions=page['divisions'],
        selected_course=page['selected_course'],
        selected_class=page['selected_class'],
        selected_division=page['selected_division'],
        sessions=page['sessions'],
        subjects=page['subjects'],
        rooms=page['rooms'],
        time_columns=page['time_columns'],
        grid_rows=page['grid_rows'],
    )
