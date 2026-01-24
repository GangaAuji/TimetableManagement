from flask import session, render_template, jsonify, make_response
from database import get_db_connection
import csv
import io
from .teacher import teacher_bp, teacher_required, format_time

# --- Timetable: page, JSON, download ---
@teacher_bp.route('/timetable')
@teacher_required
def my_timetable():
    # Just render the page; DataTables will fetch data via AJAX
    return render_template('teacher/timetable.html')


@teacher_bp.route('/timetable/data')
@teacher_required
def timetable_data():
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    faculty_id = session.get('faculty_id')
    
    # Get user_id for this faculty (timetable uses user_id as faculty_id)
    cursor.execute("SELECT user_id FROM faculty WHERE id = %s", (faculty_id,))
    faculty_record = cursor.fetchone()
    if not faculty_record:
        return jsonify({'data': []})
    
    faculty_user_id = faculty_record['user_id']
    
    cursor.execute(
        """
        SELECT t.id, t.day_of_week, t.start_time, t.end_time, s.name AS subject_name, c.name AS class_name, d.name AS division_name
        FROM timetable t
        JOIN subjects s ON t.subject_id = s.id
        JOIN classes c ON t.class_id = c.id
        JOIN divisions d ON t.division_id = d.id
        WHERE t.faculty_id = %s
        ORDER BY FIELD(t.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'), t.start_time
        """,
        [faculty_user_id],
    )
    data = []
    for row in cursor.fetchall():
        data.append(
            {
                'id': row['id'],
                'day': row['day_of_week'],
                'start_time': format_time(row['start_time']),
                'end_time': format_time(row['end_time']),
                'subject': row['subject_name'],
                'class': row['class_name'],
                'division': row['division_name'],
            }
        )
    cursor.close()
    return jsonify({'data': data})


@teacher_bp.route('/timetable/download')
@teacher_required
def download_timetable():
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    faculty_id = session.get('faculty_id')
    
    # Get user_id for this faculty (timetable uses user_id as faculty_id)
    cursor.execute("SELECT user_id FROM faculty WHERE id = %s", (faculty_id,))
    faculty_record = cursor.fetchone()
    if not faculty_record:
        return "Faculty not found", 404
    
    faculty_user_id = faculty_record['user_id']
    
    cursor.execute(
        """
        SELECT t.day_of_week, t.start_time, t.end_time, s.name AS subject_name, c.name AS class_name, d.name AS division_name
        FROM timetable t
        JOIN subjects s ON t.subject_id = s.id
        JOIN classes c ON t.class_id = c.id
        JOIN divisions d ON t.division_id = d.id
        WHERE t.faculty_id = %s
        ORDER BY FIELD(t.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'), t.start_time
        """,
        [faculty_user_id],
    )
    rows = cursor.fetchall()
    cursor.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Day', 'Start', 'End', 'Subject', 'Class', 'Division'])
    for row in rows:
        writer.writerow([row['day_of_week'], format_time(row['start_time']), format_time(row['end_time']), row['subject_name'], row['class_name'], row['division_name']])

    resp = make_response(output.getvalue())
    resp.headers['Content-Disposition'] = 'attachment; filename=my_timetable.csv'
    resp.headers['Content-Type'] = 'text/csv'
    return resp
