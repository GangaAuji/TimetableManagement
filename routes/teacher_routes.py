from flask import Blueprint, render_template, redirect, url_for, session, request, flash, current_app, jsonify, make_response
from functools import wraps
from app import mysql
from datetime import datetime, date, timedelta
import csv
import io

teacher_bp = Blueprint('teacher', __name__, url_prefix='/teacher')

def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Ensure only logged-in teachers with a bound faculty profile can access
        if 'role' not in session or session['role'] != 'Teacher':
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for('auth.login'))
        if 'faculty_id' not in session or not session.get('faculty_id'):
            flash("Faculty profile not found. Please contact administrator.", "danger")
            # Log the user out to reset inconsistent session state
            return redirect(url_for('auth.logout'))
        return f(*args, **kwargs)
    return decorated_function

# --- Utility function for time formatting ---
def format_time(time_obj):
    """Convert time/timedelta to HH:MM string format"""
    if time_obj is None:
        return ''
    if isinstance(time_obj, timedelta):
        # Convert timedelta to hours:minutes
        total_seconds = int(time_obj.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f'{hours:02d}:{minutes:02d}'
    elif hasattr(time_obj, 'strftime'):
        # datetime.time object
        return time_obj.strftime('%H:%M')
    else:
        return str(time_obj)

# --- Proxy Logic ---
def is_faculty_available(cursor, faculty_id, day, start_time, end_time):
    cursor.execute(
        """
        SELECT 1
        FROM timetable
        WHERE faculty_id = %s
          AND day_of_week = %s
          AND NOT (end_time <= %s OR start_time >= %s)
        LIMIT 1
        """,
        (faculty_id, day, start_time, end_time),
    )
    return cursor.fetchone() is None


def find_and_assign_proxy(absent_faculty_id, absence_date):
    cursor = mysql.connection.cursor()
    day_of_week = absence_date.strftime('%A')
    cursor.execute(
        "SELECT id, subject_id, start_time, end_time FROM timetable WHERE faculty_id = %s AND day_of_week = %s",
        (absent_faculty_id, day_of_week),
    )
    affected_lectures = cursor.fetchall()

    for lecture in affected_lectures:
        timetable_id, subject_id, start_time, end_time = lecture
        cursor.execute(
            "SELECT faculty_id FROM faculty_allocations WHERE subject_id = %s AND faculty_id != %s",
            (subject_id, absent_faculty_id),
        )
        potential_proxies = cursor.fetchall()
        assigned_proxy_id = next(
            (p[0] for p in potential_proxies if is_faculty_available(cursor, p[0], day_of_week, start_time, end_time)),
            None,
        )

        status = 'ASSIGNED' if assigned_proxy_id else 'UNASSIGNED'
        cursor.execute(
            """
            INSERT INTO proxy_log (original_faculty_id, proxy_faculty_id, timetable_id, absence_date, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (absent_faculty_id, assigned_proxy_id, timetable_id, absence_date, status),
        )

    mysql.connection.commit()
    cursor.close()


# --- Assignments page (classes, departments, subjects, syllabus) ---
@teacher_bp.route('/assignments')
@teacher_required
def assignments():
    faculty_id = session.get('faculty_id')
    if not faculty_id:
        flash("Faculty profile not found.", "danger")
        return redirect(url_for('auth.logout'))
    cursor = mysql.connection.cursor()
    cursor.execute(
        """
        SELECT dep.name AS department, crs.name AS course, c.name AS class_name, d.name AS division_name,
               s.id AS subject_id, s.name AS subject_name, COALESCE(s.syllabus_url, '') AS syllabus_url
        FROM faculty_allocations fa
        JOIN subjects s ON s.id = fa.subject_id
        JOIN classes c ON c.id = fa.class_id
        JOIN divisions d ON d.id = fa.division_id
        JOIN courses crs ON crs.id = s.course_id
        JOIN departments dep ON dep.id = crs.department_id
        WHERE fa.faculty_id = %s
        ORDER BY dep.name, crs.name, c.name, d.name, s.name
        """,
        [faculty_id],
    )
    rows = cursor.fetchall()
    cursor.close()
    # Transform rows into friendly dicts
    assignments = [
        {
            'department': r[0],
            'course': r[1],
            'class': r[2],
            'division': r[3],
            'subject_id': r[4],
            'subject': r[5],
            'syllabus_url': r[6] or ''
        }
        for r in rows
    ]
    return render_template('teacher/assignments.html', assignments=assignments)


# --- Dashboard ---
@teacher_bp.route('/dashboard')
@teacher_required
def dashboard():
    cursor = mysql.connection.cursor()
    faculty_id = session.get('faculty_id')
    if not faculty_id:
        flash("Faculty profile not found. Please contact administrator.", "danger")
        return redirect(url_for('auth.logout'))

    cursor.execute(
        """
        SELECT t.day_of_week, t.start_time, t.end_time, s.name, c.name, d.name
        FROM timetable t
        JOIN subjects s ON t.subject_id = s.id
        JOIN classes c ON t.class_id = c.id
        JOIN divisions d ON t.division_id = d.id
        WHERE t.faculty_id = %s
        ORDER BY FIELD(t.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'), t.start_time
        """,
        [faculty_id],
    )
    timetable = cursor.fetchall()

    cursor.execute(
        "SELECT absence_date, reason, status FROM faculty_absences WHERE faculty_id = %s ORDER BY absence_date DESC",
        [faculty_id],
    )
    absences = cursor.fetchall()
    cursor.close()
    return render_template('teacher/dashboard.html', timetable=timetable, absences=absences)


@teacher_bp.route('/mark_absence', methods=['POST'])
@teacher_required
def mark_absence():
    absence_date_str = request.form.get('absence_date')
    if not absence_date_str:
        flash("Absence date is required.", "danger")
        return redirect(url_for('teacher.dashboard'))

    cursor = mysql.connection.cursor()
    faculty_id = session.get('faculty_id')
    if not faculty_id:
        flash("Faculty profile not found.", "danger")
        return redirect(url_for('auth.logout'))

    absence_date = datetime.strptime(absence_date_str, '%Y-%m-%d').date()
    cursor.execute(
        "INSERT INTO faculty_absences (faculty_id, absence_date, reason, status) VALUES (%s, %s, %s, 'UNPROCESSED')",
        (faculty_id, absence_date, request.form.get('reason')),
    )
    mysql.connection.commit()
    cursor.close()
    flash("Absence request submitted for approval.", "success")
    return redirect(url_for('teacher.dashboard'))


# --- Timetable: page, JSON, download ---
@teacher_bp.route('/timetable')
@teacher_required
def my_timetable():
    # Just render the page; DataTables will fetch data via AJAX
    return render_template('teacher/timetable.html')


@teacher_bp.route('/timetable/data')
@teacher_required
def timetable_data():
    cursor = mysql.connection.cursor()
    faculty_id = session.get('faculty_id')
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
        [faculty_id],
    )
    data = []
    for row in cursor.fetchall():
        (tid, day, start_t, end_t, subj, cls, div) = row
        data.append(
            {
                'id': tid,
                'day': day,
                'start_time': format_time(start_t),
                'end_time': format_time(end_t),
                'subject': subj,
                'class': cls,
                'division': div,
            }
        )
    cursor.close()
    return jsonify({'data': data})


@teacher_bp.route('/timetable/download')
@teacher_required
def download_timetable():
    cursor = mysql.connection.cursor()
    faculty_id = session.get('faculty_id')
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
        [faculty_id],
    )
    rows = cursor.fetchall()
    cursor.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Day', 'Start', 'End', 'Subject', 'Class', 'Division'])
    for day, start_t, end_t, subj, cls, div in rows:
        writer.writerow([day, format_time(start_t), format_time(end_t), subj, cls, div])

    resp = make_response(output.getvalue())
    resp.headers['Content-Disposition'] = 'attachment; filename=my_timetable.csv'
    resp.headers['Content-Type'] = 'text/csv'
    return resp


# --- Availability ---
@teacher_bp.route('/availability', methods=['GET', 'POST'])
@teacher_required
def availability():
    cursor = mysql.connection.cursor()
    faculty_id = session.get('faculty_id')
    if request.method == 'POST':
        # Replace all rows for this faculty with submitted schedule
        cursor.execute("DELETE FROM faculty_availability WHERE faculty_id = %s", [faculty_id])
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        for day in days:
            is_avail = request.form.get(f'{day}-available') == 'on'
            start_t = request.form.get(f'{day}-start') or '00:00'
            end_t = request.form.get(f'{day}-end') or '00:00'
            cursor.execute(
                """
                INSERT INTO faculty_availability (faculty_id, day_of_week, start_time, end_time, is_available)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (faculty_id, day, start_t, end_t, 1 if is_avail else 0),
            )
        mysql.connection.commit()
        cursor.close()
        flash('Availability updated successfully.', 'success')
        return redirect(url_for('teacher.availability'))

    # GET
    cursor.execute(
        "SELECT day_of_week, start_time, end_time, is_available FROM faculty_availability WHERE faculty_id = %s",
        [faculty_id],
    )
    avail = {d: {'start_time': None, 'end_time': None, 'is_available': False} for d in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']}
    for day, st, et, avail_flag in cursor.fetchall():
        avail[day] = {
            'start_time': format_time(st),
            'end_time': format_time(et),
            'is_available': bool(avail_flag),
        }
    cursor.close()
    return render_template('teacher/availability.html', avail=avail)


# --- Absences JSON (AJAX) ---
@teacher_bp.route('/absences', methods=['GET', 'POST'])
@teacher_required
def absences():
    faculty_id = session.get('faculty_id')
    cursor = mysql.connection.cursor()

    if request.method == 'GET':
        cursor.execute(
            "SELECT id, absence_date, reason, status FROM faculty_absences WHERE faculty_id = %s ORDER BY absence_date DESC",
            [faculty_id],
        )
        items = [
            {
                'id': rid,
                'absence_date': ad.strftime('%Y-%m-%d') if isinstance(ad, (datetime, date)) else str(ad),
                'reason': rsn,
                'status': st,
            }
            for (rid, ad, rsn, st) in cursor.fetchall()
        ]
        cursor.close()
        return jsonify({'data': items})

    # POST create
    data = request.get_json(silent=True) or {}
    absence_date_str = data.get('absence_date') or request.form.get('absence_date')
    reason = data.get('reason') or request.form.get('reason')
    if not absence_date_str:
        cursor.close()
        return jsonify({'ok': False, 'error': 'absence_date required'}), 400
    ad = datetime.strptime(absence_date_str, '%Y-%m-%d').date()
    cursor.execute(
        "INSERT INTO faculty_absences (faculty_id, absence_date, reason, status) VALUES (%s, %s, %s, 'UNPROCESSED')",
        (faculty_id, ad, reason),
    )
    mysql.connection.commit()
    cursor.close()
    return jsonify({'ok': True})


@teacher_bp.route('/absences/<int:absence_id>', methods=['DELETE'])
@teacher_required
def delete_absence(absence_id):
    faculty_id = session.get('faculty_id')
    cursor = mysql.connection.cursor()
    # Only allow deleting UNPROCESSED ones owned by this faculty
    cursor.execute(
        "SELECT status FROM faculty_absences WHERE id = %s AND faculty_id = %s",
        (absence_id, faculty_id),
    )
    row = cursor.fetchone()
    if not row:
        cursor.close()
        return jsonify({'ok': False, 'error': 'Not found'}), 404
    if row[0] != 'UNPROCESSED':
        cursor.close()
        return jsonify({'ok': False, 'error': 'Cannot delete processed absence'}), 400
    cursor.execute("DELETE FROM faculty_absences WHERE id = %s AND faculty_id = %s", (absence_id, faculty_id))
    mysql.connection.commit()
    cursor.close()
    return jsonify({'ok': True})


# --- Proxy requests: page + create ---
@teacher_bp.route('/proxy-requests')
@teacher_required
def proxy_requests():
    faculty_id = session.get('faculty_id')
    cursor = mysql.connection.cursor()

    # Logs
    cursor.execute(
        """
        SELECT p.id, p.absence_date, p.status, p.approval_status, t.day_of_week, t.start_time, t.end_time, s.name AS subject_name,
               ofc.name AS original_name, pfc.name AS proxy_name
        FROM proxy_log p
        JOIN timetable t ON p.timetable_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        JOIN faculty ofc ON ofc.id = p.original_faculty_id
        LEFT JOIN faculty pfc ON pfc.id = p.proxy_faculty_id
        WHERE p.original_faculty_id = %s OR p.proxy_faculty_id = %s
        ORDER BY p.absence_date DESC, t.start_time
        """,
        (faculty_id, faculty_id),
    )
    logs = cursor.fetchall()

    # Lectures for request form
    cursor.execute(
        """
        SELECT t.id, t.day_of_week, t.start_time, t.end_time, s.name
        FROM timetable t
        JOIN subjects s ON s.id = t.subject_id
        WHERE t.faculty_id = %s
        ORDER BY FIELD(t.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'), t.start_time
        """,
        [faculty_id],
    )
    lectures = cursor.fetchall()

    # Proxy map for request form
    cursor.execute(
        """
        SELECT fa.subject_id, fa.faculty_id, f.name
        FROM faculty_allocations fa
        JOIN faculty f ON f.id = fa.faculty_id
        WHERE fa.faculty_id != %s
        """,
        [faculty_id],
    )
    proxy_map = {}
    for sid, fid, fname in cursor.fetchall():
        proxy_map.setdefault(sid, []).append({'faculty_id': fid, 'name': fname})

    cursor.close()
    return render_template('teacher/proxy_requests.html', logs=logs, lectures=lectures, proxy_map=proxy_map)


@teacher_bp.route('/request-proxy', methods=['GET', 'POST'])
@teacher_required
def request_proxy():
    faculty_id = session.get('faculty_id')
    cursor = mysql.connection.cursor()

    if request.method == 'POST':
        timetable_id = request.form.get('timetable_id', type=int)
        proxy_faculty_id = request.form.get('proxy_faculty_id', type=int)
        absence_date_str = request.form.get('absence_date')
        if not (timetable_id and absence_date_str):
            cursor.close()
            flash('Please select a lecture and date.', 'danger')
            return redirect(url_for('teacher.request_proxy'))
        ad = datetime.strptime(absence_date_str, '%Y-%m-%d').date()
        # Fetch lecture to derive day/time/subject
        cursor.execute(
            "SELECT day_of_week, subject_id, start_time, end_time FROM timetable WHERE id = %s AND faculty_id = %s",
            (timetable_id, faculty_id),
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            flash('Invalid lecture selected.', 'danger')
            return redirect(url_for('teacher.request_proxy'))
        day, subject_id, start_t, end_t = row

        # Create a pending proxy request; admin will approve/reject and finalize
        assigned_proxy_id = proxy_faculty_id if proxy_faculty_id else None
        status = 'PENDING'
        cursor.execute(
            """
            INSERT INTO proxy_log (original_faculty_id, proxy_faculty_id, timetable_id, absence_date, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (faculty_id, assigned_proxy_id, timetable_id, ad, status),
        )
        mysql.connection.commit()
        cursor.close()
        flash('Proxy request submitted for approval.', 'success')
        return redirect(url_for('teacher.proxy_requests'))

    # GET: upcoming timetable options and suggested proxies per subject
    cursor.execute(
        """
        SELECT t.id, t.day_of_week, t.start_time, t.end_time, s.name
        FROM timetable t
        JOIN subjects s ON s.id = t.subject_id
        WHERE t.faculty_id = %s
        ORDER BY FIELD(t.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'), t.start_time
        """,
        [faculty_id],
    )
    lectures = cursor.fetchall()

    # Map subject -> potential proxies (other faculty allocated to same subject)
    cursor.execute(
        """
        SELECT fa.subject_id, fa.faculty_id, f.name
        FROM faculty_allocations fa
        JOIN faculty f ON f.id = fa.faculty_id
        WHERE fa.faculty_id != %s
        """,
        [faculty_id],
    )
    proxy_map = {}
    for sid, fid, fname in cursor.fetchall():
        proxy_map.setdefault(sid, []).append({'faculty_id': fid, 'name': fname})

    cursor.close()
    return render_template('teacher/request_proxy.html', lectures=lectures, proxy_map=proxy_map)


# --- Placeholder to avoid broken nav if referenced ---
@teacher_bp.route('/attendance')
@teacher_required
def attendance():
    return render_template('teacher/placeholder.html', title='Attendance', message='Attendance module is coming soon.')
