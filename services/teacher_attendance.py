"""Teacher attendance load and save. Exceptions are left for the route."""

from datetime import date, datetime

from flask import flash

from academic_rules.weekdays import weekday_name

from data_access.teacher_attendance import (
    count_attendance_for_date,
    fetch_attendance_history,
    fetch_attendance_summary,
    fetch_existing_attendance,
    fetch_faculty_table_id,
    fetch_history_lecture,
    fetch_lecture_filters,
    fetch_lecture_roster,
    fetch_owned_lecture_detail,
    fetch_teacher_lectures,
    upsert_attendance,
)
from extensions import get_db_connection
from utils.dates import format_hhmm


def _cursor():
    connection = get_db_connection()
    return connection, connection.cursor(dictionary=True)


def load_attendance_index(user_id):
    """Return today's lecture list. The caller handles a database error."""
    connection, cursor = _cursor()
    lectures = fetch_teacher_lectures(cursor, user_id)
    today = date.today().strftime('%Y-%m-%d')
    today_formatted = date.today().strftime('%d %b %Y')
    for lecture in lectures:
        lecture['start_time'] = format_hhmm(lecture['start_time'])
        lecture['end_time'] = format_hhmm(lecture['end_time'])
        result = count_attendance_for_date(cursor, lecture['timetable_id'], today)
        lecture['attendance_marked_today'] = result['count'] > 0 if result else False
    marked_today_count = sum(1 for lecture in lectures if lecture['attendance_marked_today'])
    cursor.close()
    connection.close()
    return {
        'lectures': lectures,
        'today': today_formatted,
        'marked_today_count': marked_today_count,
    }


def load_mark_page(user_id, timetable_id):
    """Return the mark page, missing, or denied. The caller handles a database error."""
    connection, cursor = _cursor()
    faculty_row = fetch_faculty_table_id(cursor, user_id)
    if not faculty_row:
        flash("Faculty profile not found.", "danger")
        cursor.close()
        connection.close()
        return 'missing'
    attendance_date = date.today().strftime('%Y-%m-%d')
    lecture = fetch_owned_lecture_detail(cursor, timetable_id, user_id)
    if not lecture:
        flash("Lecture not found or you don't have permission to mark attendance for it.", "danger")
        cursor.close()
        connection.close()
        return 'denied'
    lecture['start_time'] = format_hhmm(lecture['start_time'])
    lecture['end_time'] = format_hhmm(lecture['end_time'])
    students = fetch_lecture_roster(cursor, lecture)
    existing_attendance = {
        row['student_id']: {'status': row['status'], 'remarks': row['remarks']}
        for row in fetch_existing_attendance(cursor, timetable_id, attendance_date)
    }
    attendance_already_marked = len(existing_attendance) > 0
    for student in students:
        if student['id'] in existing_attendance:
            student['attendance_status'] = existing_attendance[student['id']]['status']
            student['remarks'] = existing_attendance[student['id']]['remarks']
        else:
            student['attendance_status'] = None
            student['remarks'] = None
    cursor.close()
    connection.close()
    return {
        'lecture': lecture,
        'students': students,
        'attendance_date': attendance_date,
        'attendance_already_marked': attendance_already_marked,
    }


_MARK_STATUSES = frozenset(('Present', 'Late', 'Absent'))


def _close(cursor, connection):
    cursor.close()
    connection.close()


def _marks(form):
    """Return student marks, or None when a status or student id is not acceptable."""
    marks = {}
    for key, value in form.items():
        if not str(key).startswith('status_'):
            continue
        if value not in _MARK_STATUSES:
            return None
        try:
            student_id = int(str(key).split('_', 1)[1])
        except (TypeError, ValueError):
            return None
        if student_id < 1 or student_id in marks:
            return None
        marks[student_id] = (value, form.get(f'remarks_{student_id}', '') or '')
    return marks


def _date_allowed(raw, lecture_day):
    """Attendance is taken today, and only when today is the lecture weekday."""
    try:
        chosen = datetime.strptime(str(raw), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return False
    if chosen != date.today():
        return False
    return weekday_name(chosen) == weekday_name(lecture_day)


def save_teacher_attendance(user_id, timetable_id, form):
    """Save marks. A database error rolls back and is raised again. The connection stays open on that path."""
    connection = None
    try:
        connection, cursor = _cursor()
        faculty_row = fetch_faculty_table_id(cursor, user_id)
        if not faculty_row:
            flash("Faculty profile not found.", "danger")
            _close(cursor, connection)
            return 'missing'
        faculty_id = faculty_row['id']
        lecture = fetch_owned_lecture_detail(cursor, timetable_id, user_id)
        if not lecture:
            flash("Unauthorized access.", "danger")
            _close(cursor, connection)
            return 'denied'
        attendance_date = form.get('attendance_date')
        if not attendance_date or not _date_allowed(attendance_date, lecture.get('day_of_week')):
            flash("Attendance can only be marked today, on the lecture's scheduled day.", "danger")
            _close(cursor, connection)
            return 'date'
        marks = _marks(form)
        enrolled = {row['id'] for row in fetch_lecture_roster(cursor, lecture)}
        if marks is None or not set(marks) <= enrolled:
            flash("A student in this request is not in this class.", "danger")
            _close(cursor, connection)
            return 'student'
        saved_count = 0
        for student_id, (status, remarks) in marks.items():
            upsert_attendance(
                cursor, student_id, timetable_id, attendance_date, status, faculty_id, remarks,
            )
            saved_count += 1
        connection.commit()
        _close(cursor, connection)
        return saved_count
    except Exception:
        if connection:
            connection.rollback()
        raise


def load_attendance_report(user_id, subject_id, class_id, division_id, date_from, date_to):
    """Return report filters and rows. The caller handles a database error."""
    connection, cursor = _cursor()
    filter_options = fetch_lecture_filters(cursor, user_id)
    attendance_data = []
    if subject_id and class_id and division_id:
        date_filter = ""
        params = [class_id, division_id, subject_id, user_id]
        if date_from and date_to:
            date_filter = "AND a.attendance_date BETWEEN %s AND %s"
            params.extend([date_from, date_to])
        elif date_from:
            date_filter = "AND a.attendance_date >= %s"
            params.append(date_from)
        elif date_to:
            date_filter = "AND a.attendance_date <= %s"
            params.append(date_to)
        attendance_data = fetch_attendance_summary(cursor, date_filter, params)
        for record in attendance_data:
            record['total_marked'] = int(record['total_marked']) if record['total_marked'] else 0
            record['present_count'] = int(record['present_count']) if record['present_count'] else 0
            record['late_count'] = int(record['late_count']) if record['late_count'] else 0
            record['absent_count'] = int(record['absent_count']) if record['absent_count'] else 0
            record['attendance_percentage'] = float(record['attendance_percentage']) if record['attendance_percentage'] else 0.0
    cursor.close()
    connection.close()
    return {'filter_options': filter_options, 'attendance_data': attendance_data}


def load_attendance_history(user_id, timetable_id):
    """Return history, or denied. The caller handles a database error."""
    connection, cursor = _cursor()
    lecture = fetch_history_lecture(cursor, timetable_id, user_id)
    if not lecture:
        flash("Unauthorized access.", "danger")
        cursor.close()
        connection.close()
        return 'denied'
    history = fetch_attendance_history(cursor, timetable_id)
    for record in history:
        record['total_students'] = int(record['total_students']) if record['total_students'] else 0
        record['present'] = int(record['present']) if record['present'] else 0
        record['late'] = int(record['late']) if record['late'] else 0
        record['absent'] = int(record['absent']) if record['absent'] else 0
    cursor.close()
    connection.close()
    return {'lecture': lecture, 'history': history}
