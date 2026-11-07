"""Teacher classes, absences, and availability. This module does not read the request."""

from datetime import date, datetime

from flask import flash

from academic_rules.clashes import faculty_timetable_free
from data_access.teacher_portal import (
    delete_faculty_absence,
    delete_faculty_availability,
    fetch_absence_rows,
    fetch_absence_status,
    fetch_assignments,
    fetch_availability_slots,
    fetch_class_students,
    fetch_day_schedule,
    fetch_faculty_absences,
    fetch_faculty_by_user,
    fetch_faculty_lectures,
    fetch_faculty_user_id,
    fetch_lectures_on_day,
    fetch_other_allocated_faculty,
    fetch_owned_lecture,
    fetch_proxy_candidates,
    fetch_proxy_logs,
    fetch_shift_availability,
    fetch_shift_faculty,
    fetch_shift_requests,
    fetch_teaching_assignments,
    fetch_teaching_class_counts,
    fetch_timetable_download_rows,
    fetch_timetable_rows,
    fetch_week_schedule,
    insert_assigned_proxy,
    insert_availability_slot,
    insert_pending_proxy,
    insert_shift_request,
    insert_unprocessed_absence,
)
from extensions import get_db_connection
from utils.dates import format_hhmm

_DAY_MAP = {'Monday': 1, 'Tuesday': 2, 'Wednesday': 3, 'Thursday': 4, 'Friday': 5, 'Saturday': 6}
_DAY_NAMES = {1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday', 5: 'Friday', 6: 'Saturday'}


def _cursor():
    connection = get_db_connection()
    return connection, connection.cursor(dictionary=True)


def load_my_classes(faculty_id):
    """Return class rows, or missing when the faculty profile cannot be used."""
    connection, cursor = _cursor()
    if not faculty_id:
        flash("Faculty profile not found. Please contact administrator.", "danger")
        return 'missing'
    faculty_record = fetch_faculty_user_id(cursor, faculty_id)
    if not faculty_record:
        flash("Faculty profile not found. Please contact administrator.", "danger")
        return 'missing'
    classes_with_students = []
    for assignment in fetch_teaching_assignments(cursor, faculty_record['user_id']):
        students = fetch_class_students(
            cursor,
            assignment['class_id'],
            assignment['division_id'],
            assignment['course_id'],
        )
        classes_with_students.append({
            'class_name': assignment['class_name'],
            'division_name': assignment['division_name'],
            'course_name': assignment['course_name'],
            'subject_name': assignment['subject_name'],
            'student_count': len(students),
            'students': students,
        })
    cursor.close()
    return classes_with_students


def load_absences(faculty_id):
    """Return absence rows. The connection stays open."""
    connection, cursor = _cursor()
    items = [
        {
            'id': row['id'],
            'absence_date': row['absence_date'].strftime('%Y-%m-%d') if isinstance(row['absence_date'], (datetime, date)) else str(row['absence_date']),
            'reason': row['reason'],
            'status': row['status'],
        }
        for row in fetch_faculty_absences(cursor, faculty_id)
    ]
    cursor.close()
    return items


def add_absence(faculty_id, absence_date_str, reason):
    """Insert an unprocessed absence. Return missing when the date is blank."""
    connection, cursor = _cursor()
    if not absence_date_str:
        cursor.close()
        return 'missing'
    absence_date = datetime.strptime(absence_date_str, '%Y-%m-%d').date()
    insert_unprocessed_absence(cursor, faculty_id, absence_date, reason)
    connection.commit()
    cursor.close()
    return 'ok'


def remove_absence(faculty_id, absence_id):
    """Delete an unprocessed absence owned by this faculty member."""
    connection, cursor = _cursor()
    row = fetch_absence_status(cursor, absence_id, faculty_id)
    if not row:
        cursor.close()
        return 'missing'
    if row['status'] != 'UNPROCESSED':
        cursor.close()
        return 'processed'
    delete_faculty_absence(cursor, absence_id, faculty_id)
    connection.commit()
    cursor.close()
    return 'ok'


def submit_absence(faculty_id, absence_date_str, reason):
    """Submit an absence from the dashboard form."""
    connection, cursor = _cursor()
    if not faculty_id:
        flash("Faculty profile not found.", "danger")
        return 'missing'
    absence_date = datetime.strptime(absence_date_str, '%Y-%m-%d').date()
    insert_unprocessed_absence(cursor, faculty_id, absence_date, reason)
    connection.commit()
    cursor.close()
    flash("Absence request submitted for approval.", "success")
    return 'ok'


def save_availability(faculty_id, form):
    """Replace availability. Return missing, ok, or an error string."""
    connection, cursor = _cursor()
    faculty_record = fetch_faculty_user_id(cursor, faculty_id)
    if not faculty_record:
        flash("Faculty profile not found. Please contact administrator.", "danger")
        return 'missing'
    faculty_user_id = faculty_record['user_id']
    try:
        delete_faculty_availability(cursor, faculty_user_id)
        connection.commit()
        for day_name, day_num in _DAY_MAP.items():
            is_avail = form.get(f'{day_name}-available') == 'on'
            if is_avail:
                slot_index = 0
                while True:
                    start_time = form.get(f'{day_name}-start-{slot_index}')
                    end_time = form.get(f'{day_name}-end-{slot_index}')
                    notes = form.get(f'{day_name}-notes-{slot_index}', '')
                    if not start_time or not end_time:
                        break
                    insert_availability_slot(cursor, faculty_user_id, day_num, 1, start_time, end_time, notes)
                    slot_index += 1
                if slot_index == 0:
                    insert_availability_slot(cursor, faculty_user_id, day_num, 0, None, None, '')
            else:
                insert_availability_slot(cursor, faculty_user_id, day_num, 0, None, None, '')
        connection.commit()
        cursor.close()
        connection.close()
        flash('Availability updated successfully.', 'success')
        return 'ok'
    except Exception as exc:
        connection.rollback()
        cursor.close()
        connection.close()
        flash(f'Error updating availability: {str(exc)}', 'danger')
        return str(exc)


def load_availability(faculty_id):
    """Return availability slots, or missing when the faculty profile is absent."""
    connection, cursor = _cursor()
    faculty_record = fetch_faculty_user_id(cursor, faculty_id)
    if not faculty_record:
        flash("Faculty profile not found. Please contact administrator.", "danger")
        return 'missing'
    avail_all_slots = {day: [] for day in _DAY_NAMES.values()}
    for row in fetch_availability_slots(cursor, faculty_record['user_id']):
        day_name = _DAY_NAMES.get(row['day_of_week'])
        if day_name:
            avail_all_slots[day_name].append({
                'is_available': bool(row['is_available']),
                'start_time': format_hhmm(row['start_time']) if row['start_time'] else None,
                'end_time': format_hhmm(row['end_time']) if row['end_time'] else None,
                'notes': row['notes'] or '',
                'shift_pattern_id': row['shift_pattern_id'],
                'shift_name': row['shift_name'],
                'shift_code': row['shift_code'],
                'shift_start': format_hhmm(row['shift_start']) if row['shift_start'] else None,
                'shift_end': format_hhmm(row['shift_end']) if row['shift_end'] else None,
            })
    cursor.close()
    return avail_all_slots


def load_assignments(faculty_id):
    """Return assignment rows. A missing profile is reported before or after the lookup."""
    if not faculty_id:
        flash("Faculty profile not found.", "danger")
        return 'missing'
    connection, cursor = _cursor()
    faculty_record = fetch_faculty_user_id(cursor, faculty_id)
    if not faculty_record:
        flash("Faculty profile not found.", "danger")
        cursor.close()
        connection.close()
        return 'missing'
    rows = fetch_assignments(cursor, faculty_record['user_id'])
    cursor.close()
    connection.close()
    return [
        {
            'department': row['department'],
            'course': row['course'],
            'class': row['class_name'],
            'division': row['division_name'],
            'subject_id': row['subject_id'],
            'subject': row['subject_name'],
            'syllabus_url': row['syllabus_url'] or '',
        }
        for row in rows
    ]


def load_teacher_dashboard(session):
    """Return the teacher dashboard rows. A missing profile leaves the connection open."""
    connection, cursor = _cursor()
    faculty_id = session.get('faculty_id')
    if not faculty_id:
        user_id = session.get('user_id')
        if user_id:
            faculty_record = fetch_faculty_by_user(cursor, user_id)
            if faculty_record:
                faculty_id = faculty_record['id']
                session['faculty_id'] = faculty_id
            else:
                flash("Faculty profile not found. Please contact administrator.", "danger")
                return 'missing'
        else:
            flash("Faculty profile not found. Please contact administrator.", "danger")
            return 'missing'
    faculty_record = fetch_faculty_user_id(cursor, faculty_id)
    if not faculty_record:
        flash("Faculty profile not found. Please contact administrator.", "danger")
        return 'missing'
    faculty_user_id = faculty_record['user_id']
    today_day = datetime.now().strftime('%A')
    page = {
        'timetable': fetch_day_schedule(cursor, faculty_user_id, today_day),
        'weekly_timetable': fetch_week_schedule(cursor, faculty_user_id),
        'absences': fetch_absence_rows(cursor, faculty_id),
        'teaching_classes': fetch_teaching_class_counts(cursor, faculty_user_id),
    }
    cursor.close()
    return page


def load_timetable_rows(faculty_id):
    """Return formatted timetable rows, or missing. The connection stays open."""
    connection, cursor = _cursor()
    faculty_record = fetch_faculty_user_id(cursor, faculty_id)
    if not faculty_record:
        return 'missing'
    data = []
    for row in fetch_timetable_rows(cursor, faculty_record['user_id']):
        data.append({
            'id': row['id'],
            'day': row['day_of_week'],
            'start_time': format_hhmm(row['start_time']),
            'end_time': format_hhmm(row['end_time']),
            'subject': row['subject_name'],
            'class': row['class_name'],
            'division': row['division_name'],
        })
    cursor.close()
    return data


def load_timetable_download(faculty_id):
    """Return download rows, or missing. The connection stays open."""
    connection, cursor = _cursor()
    faculty_record = fetch_faculty_user_id(cursor, faculty_id)
    if not faculty_record:
        return 'missing'
    rows = fetch_timetable_download_rows(cursor, faculty_record['user_id'])
    cursor.close()
    return rows


_SHIFT_DAYS = {
    1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday',
    5: 'Friday', 6: 'Saturday', 7: 'Sunday',
}


def is_faculty_available(cursor, faculty_id, day, start_time, end_time):
    return faculty_timetable_free(
        cursor, faculty_id, day, start_time, end_time, active_only=False,
    )


def find_and_assign_proxy(absent_faculty_id, absence_date):
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    day_of_week = absence_date.strftime('%A')
    affected_lectures = fetch_lectures_on_day(cursor, absent_faculty_id, day_of_week)

    for lecture in affected_lectures:
        timetable_id, subject_id, start_time, end_time = lecture['id'], lecture['subject_id'], lecture['start_time'], lecture['end_time']
        potential_proxies = fetch_other_allocated_faculty(cursor, subject_id, absent_faculty_id)
        assigned_proxy_id = next(
            (p['faculty_id'] for p in potential_proxies if is_faculty_available(cursor, p['faculty_id'], day_of_week, start_time, end_time)),
            None,
        )

        status = 'ASSIGNED' if assigned_proxy_id else 'UNASSIGNED'
        insert_assigned_proxy(
            cursor,
            absent_faculty_id,
            assigned_proxy_id,
            timetable_id,
            absence_date,
            status,
        )

    connection.commit()
    cursor.close()


def _proxy_map(cursor, faculty_id):
    proxy_map = {}
    for row in fetch_proxy_candidates(cursor, faculty_id):
        proxy_map.setdefault(row['subject_id'], []).append({
            'faculty_id': row['faculty_id'],
            'name': row['name'],
        })
    return proxy_map


def load_my_shifts(faculty_id):
    """Return the shifts page, or missing. An error string is flashed by the caller path."""
    connection, cursor = _cursor()
    try:
        faculty_record = fetch_faculty_user_id(cursor, faculty_id)
        if not faculty_record:
            flash("Faculty profile not found.", "danger")
            cursor.close()
            connection.close()
            return 'missing'
        faculty_user_id = faculty_record['user_id']
        faculty_info = fetch_shift_faculty(cursor, faculty_id)
        schedule = {}
        for record in fetch_shift_availability(cursor, faculty_user_id):
            day_num = record['day_of_week']
            day_name = _SHIFT_DAYS.get(day_num, f'Day {day_num}')
            schedule[day_name] = {
                'day_num': day_num,
                'is_available': bool(record['is_available']),
                'notes': record['notes'],
                'shift_name': record['shift_name'],
                'shift_code': record['shift_code'],
                'start_time': format_hhmm(record['start_time']) if record['start_time'] else None,
                'end_time': format_hhmm(record['end_time']) if record['end_time'] else None,
            }
        change_requests = fetch_shift_requests(cursor, faculty_user_id)
        cursor.close()
        connection.close()
        return {
            'faculty_info': faculty_info,
            'schedule': schedule,
            'day_names': _SHIFT_DAYS,
            'change_requests': change_requests,
        }
    except Exception as exc:
        cursor.close()
        flash(f'Error loading shift information: {str(exc)}', 'danger')
        return str(exc)


def submit_shift_change(faculty_id, day_of_week, current_shift_name, requested_shift_name, reason):
    """Store a shift-change request. Return missing or ok."""
    connection, cursor = _cursor()
    try:
        faculty_record = fetch_faculty_user_id(cursor, faculty_id)
        if not faculty_record or not faculty_record.get('user_id'):
            flash('Faculty profile not found.', 'danger')
            return 'missing'
        insert_shift_request(
            cursor,
            faculty_record['user_id'],
            day_of_week,
            current_shift_name,
            requested_shift_name,
            reason,
        )
        connection.commit()
        flash('Shift change request submitted successfully! Admin will review it soon.', 'success')
        return 'ok'
    except Exception as exc:
        connection.rollback()
        flash(f'Error submitting request: {str(exc)}', 'danger')
        return 'error'
    finally:
        cursor.close()
        connection.close()


def load_proxy_page(faculty_id):
    """Return proxy logs and the request form data, or missing."""
    connection, cursor = _cursor()
    faculty_record = fetch_faculty_user_id(cursor, faculty_id)
    if not faculty_record:
        flash("Faculty profile not found.", "danger")
        cursor.close()
        connection.close()
        return 'missing'
    faculty_user_id = faculty_record['user_id']
    page = {
        'logs': fetch_proxy_logs(cursor, faculty_user_id),
        'lectures': fetch_faculty_lectures(cursor, faculty_user_id),
        'proxy_map': _proxy_map(cursor, faculty_id),
    }
    cursor.close()
    return page


def load_proxy_form(faculty_id):
    """Return lectures and proxy choices, or missing. The connection stays open."""
    connection, cursor = _cursor()
    faculty_record = fetch_faculty_user_id(cursor, faculty_id)
    if not faculty_record:
        flash("Faculty profile not found.", "danger")
        cursor.close()
        connection.close()
        return 'missing'
    page = {
        'lectures': fetch_faculty_lectures(cursor, faculty_record['user_id']),
        'proxy_map': _proxy_map(cursor, faculty_id),
    }
    cursor.close()
    return page


def submit_proxy_request(faculty_id, timetable_id, proxy_faculty_id, absence_date_str):
    """Create a pending proxy request. Return missing, invalid, or ok."""
    connection, cursor = _cursor()
    faculty_record = fetch_faculty_user_id(cursor, faculty_id)
    if not faculty_record:
        flash("Faculty profile not found.", "danger")
        cursor.close()
        connection.close()
        return 'missing'
    if not (timetable_id and absence_date_str):
        cursor.close()
        connection.close()
        flash('Please select a lecture and date.', 'danger')
        return 'fields'
    absence_date = datetime.strptime(absence_date_str, '%Y-%m-%d').date()
    proxy_user_id = None
    if proxy_faculty_id:
        proxy_record = fetch_faculty_user_id(cursor, proxy_faculty_id)
        if proxy_record:
            proxy_user_id = proxy_record['user_id']
    row = fetch_owned_lecture(cursor, timetable_id, faculty_record['user_id'])
    if not row:
        cursor.close()
        connection.close()
        flash('Invalid lecture selected.', 'danger')
        return 'invalid'
    insert_pending_proxy(
        cursor,
        faculty_record['user_id'],
        proxy_user_id,
        timetable_id,
        absence_date,
    )
    connection.commit()
    cursor.close()
    connection.close()
    flash('Proxy request submitted for approval.', 'success')
    return 'ok'
