from flask import session, redirect, url_for, flash, render_template, request
from database import get_db_connection
from datetime import datetime
from .teacher import teacher_bp, teacher_required

# --- Proxy requests: page + create ---
@teacher_bp.route('/proxy-requests')
@teacher_required
def proxy_requests():
    faculty_id = session.get('faculty_id')  # This is faculty.id
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    
    # Get user_id for this faculty (proxy_log uses user_id)
    cursor.execute("SELECT user_id FROM faculty WHERE id = %s", (faculty_id,))
    faculty_record = cursor.fetchone()
    if not faculty_record:
        flash("Faculty profile not found.", "danger")
        cursor.close()
        connection.close()
        return redirect(url_for('teacher.dashboard'))
    
    faculty_user_id = faculty_record['user_id']

    # Logs
    cursor.execute(
        """
        SELECT p.id, p.absence_date, p.status, p.approval_status, t.day_of_week, t.start_time, t.end_time, s.name AS subject_name,
               ofc.name AS original_name, pfc.name AS proxy_name
        FROM proxy_log p
        JOIN timetable t ON p.timetable_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        JOIN faculty ofc ON ofc.user_id = p.original_faculty_id
        LEFT JOIN faculty pfc ON pfc.user_id = p.proxy_faculty_id
        WHERE p.original_faculty_id = %s OR p.proxy_faculty_id = %s
        ORDER BY p.absence_date DESC, t.start_time
        """,
        (faculty_user_id, faculty_user_id),
    )
    logs = cursor.fetchall()

    # Lectures for request form (timetable.faculty_id stores user_id)
    cursor.execute(
        """
        SELECT t.id, t.day_of_week, t.start_time, t.end_time, s.name
        FROM timetable t
        JOIN subjects s ON s.id = t.subject_id
        WHERE t.faculty_id = %s
        ORDER BY FIELD(t.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'), t.start_time
        """,
        [faculty_user_id],
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
    for row in cursor.fetchall():
        sid = row['subject_id']
        fid = row['faculty_id']
        fname = row['name']
        proxy_map.setdefault(sid, []).append({'faculty_id': fid, 'name': fname})

    cursor.close()
    return render_template('teacher/proxy_requests.html', logs=logs, lectures=lectures, proxy_map=proxy_map)


@teacher_bp.route('/request-proxy', methods=['GET', 'POST'])
@teacher_required
def request_proxy():
    faculty_id = session.get('faculty_id')  # This is faculty.id
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    
    # Get user_id for this faculty (timetable and proxy_log use user_id)
    cursor.execute("SELECT user_id FROM faculty WHERE id = %s", (faculty_id,))
    faculty_record = cursor.fetchone()
    if not faculty_record:
        flash("Faculty profile not found.", "danger")
        cursor.close()
        connection.close()
        return redirect(url_for('teacher.dashboard'))
    
    faculty_user_id = faculty_record['user_id']

    if request.method == 'POST':
        timetable_id = request.form.get('timetable_id', type=int)
        proxy_faculty_id = request.form.get('proxy_faculty_id', type=int)  # This is faculty.id from form
        absence_date_str = request.form.get('absence_date')
        if not (timetable_id and absence_date_str):
            cursor.close()
            connection.close()
            flash('Please select a lecture and date.', 'danger')
            return redirect(url_for('teacher.request_proxy'))
        ad = datetime.strptime(absence_date_str, '%Y-%m-%d').date()
        
        # Convert proxy_faculty_id (faculty.id) to user_id if provided
        proxy_user_id = None
        if proxy_faculty_id:
            cursor.execute("SELECT user_id FROM faculty WHERE id = %s", (proxy_faculty_id,))
            proxy_record = cursor.fetchone()
            if proxy_record:
                proxy_user_id = proxy_record['user_id']
        
        # Fetch lecture to derive day/time/subject (timetable.faculty_id stores user_id)
        cursor.execute(
            "SELECT day_of_week, subject_id, start_time, end_time FROM timetable WHERE id = %s AND faculty_id = %s",
            (timetable_id, faculty_user_id),
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            connection.close()
            flash('Invalid lecture selected.', 'danger')
            return redirect(url_for('teacher.request_proxy'))
        day = row['day_of_week']
        subject_id = row['subject_id']
        start_t = row['start_time']
        end_t = row['end_time']

        # Create a pending proxy request; admin will approve/reject and finalize
        # proxy_log stores user_id values in original_faculty_id and proxy_faculty_id
        status = 'PENDING'
        cursor.execute(
            """
            INSERT INTO proxy_log (original_faculty_id, proxy_faculty_id, timetable_id, absence_date, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (faculty_user_id, proxy_user_id, timetable_id, ad, status),
        )
        connection.commit()
        cursor.close()
        connection.close()
        flash('Proxy request submitted for approval.', 'success')
        return redirect(url_for('teacher.proxy_requests'))

    # GET: upcoming timetable options and suggested proxies per subject
    # timetable.faculty_id stores user_id
    cursor.execute(
        """
        SELECT t.id, t.day_of_week, t.start_time, t.end_time, s.name
        FROM timetable t
        JOIN subjects s ON s.id = t.subject_id
        WHERE t.faculty_id = %s
        ORDER BY FIELD(t.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'), t.start_time
        """,
        [faculty_user_id],
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
    for row in cursor.fetchall():
        proxy_map.setdefault(row['subject_id'], []).append({'faculty_id': row['faculty_id'], 'name': row['name']})

    cursor.close()
    return render_template('teacher/request_proxy.html', lectures=lectures, proxy_map=proxy_map)

