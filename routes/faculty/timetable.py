from flask import session, jsonify, make_response
from ui.pages import render_template
import csv
import io
from .teacher import teacher_bp, teacher_required, format_time
from services.teacher_portal import load_timetable_download, load_timetable_rows

# --- Timetable: page, JSON, download ---
@teacher_bp.route('/timetable')
@teacher_required
def my_timetable():
    # Just render the page; DataTables will fetch data via AJAX
    return render_template('teacher/timetable.html')


@teacher_bp.route('/timetable/data')
@teacher_required
def timetable_data():
    data = load_timetable_rows(session.get('faculty_id'))
    if data == 'missing':
        return jsonify({'data': []})
    return jsonify({'data': data})


@teacher_bp.route('/timetable/download')
@teacher_required
def download_timetable():
    rows = load_timetable_download(session.get('faculty_id'))
    if rows == 'missing':
        return "Faculty not found", 404

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Day', 'Start', 'End', 'Subject', 'Class', 'Division'])
    for row in rows:
        writer.writerow([row['day_of_week'], format_time(row['start_time']), format_time(row['end_time']), row['subject_name'], row['class_name'], row['division_name']])

    resp = make_response(output.getvalue())
    resp.headers['Content-Disposition'] = 'attachment; filename=my_timetable.csv'
    resp.headers['Content-Type'] = 'text/csv'
    return resp
