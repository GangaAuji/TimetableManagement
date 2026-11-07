"""Admin faculty screens. Connection close behavior matches the previous route code."""

from datetime import datetime

from flask import current_app, flash
from werkzeug.security import generate_password_hash

from data_access.admin_faculty import (
    approve_proxy_log,
    deactivate_faculty,
    deactivate_faculty_users,
    delete_absence,
    delete_faculty_availability,
    fetch_absence_for_approval,
    fetch_absence_status,
    fetch_absences,
    fetch_active_shift_patterns,
    fetch_availability_slots,
    fetch_availability_with_shifts,
    fetch_departments,
    fetch_download_with_rooms,
    fetch_download_without_rooms,
    fetch_faculty_email,
    fetch_faculty_form,
    fetch_faculty_name,
    fetch_faculty_name_user,
    fetch_faculty_proxy_rows,
    fetch_faculty_totals,
    fetch_faculty_user_id,
    fetch_faculty_user_ids,
    fetch_owned_proxy,
    fetch_proxy_candidates,
    fetch_timetable_with_rooms,
    fetch_timetable_without_rooms,
    fetch_username,
    insert_availability_slot,
    insert_faculty_profile,
    insert_processed_absence,
    insert_teacher_user,
    insert_unavailable_day,
    mark_absence_processed,
    reject_absence,
    reject_proxy_log,
    update_faculty_profile,
    update_user_password,
)
from extensions import get_db_connection
from routes.admin_utils import _admin_find_and_assign_proxy, _is_faculty_free, format_time, paginate
from security.permissions import get_accessible_faculty_ids

_DAY_MAP = {'Monday': 1, 'Tuesday': 2, 'Wednesday': 3, 'Thursday': 4, 'Friday': 5, 'Saturday': 6}
_DAY_NAMES = {1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday', 5: 'Friday', 6: 'Saturday'}

_ACTIVE_COUNT = """
        SELECT COUNT(f.id) AS total
        FROM faculty f
        LEFT JOIN users u ON f.user_id = u.id
        WHERE f.is_active = 1
          AND u.role = 'Teacher'
          AND COALESCE(u.status, 'active') = 'active'
    """
_INACTIVE_COUNT = """
        SELECT COUNT(f.id) AS total
        FROM faculty f
        LEFT JOIN users u ON f.user_id = u.id
        WHERE f.is_active = 0
          AND u.role = 'Teacher'
          AND COALESCE(u.status, 'active') = 'active'
    """


def _cursor():
    connection = get_db_connection()
    return connection, connection.cursor(dictionary=True)


def _date_text(value):
    return value.strftime('%Y-%m-%d') if hasattr(value, 'strftime') else str(value)


def list_faculty(page, search, department_filter, user_id):
    """Return the faculty list. The count connection stays open."""
    query_base = "FROM faculty f LEFT JOIN departments d ON f.department_id = d.id LEFT JOIN users u ON f.user_id = u.id"
    where_conditions = [
        "u.role = 'Teacher'",
        "COALESCE(u.status, 'active') = 'active'",
    ]
    params = []
    accessible_faculty_ids = get_accessible_faculty_ids(user_id)
    if accessible_faculty_ids is not None:
        if accessible_faculty_ids:
            placeholders = ','.join(['%s'] * len(accessible_faculty_ids))
            where_conditions.append(f"f.id IN ({placeholders})")
            params.extend(accessible_faculty_ids)
        else:
            where_conditions.append("f.id = -1")
    if search:
        search_term = f"%{search}%"
        where_conditions.append("(f.name LIKE %s OR f.email LIKE %s OR f.employee_id LIKE %s)")
        params.extend([search_term, search_term, search_term])
    if department_filter:
        where_conditions.append("f.department_id = %s")
        params.append(department_filter)
    if where_conditions:
        query_base += " WHERE " + " AND ".join(where_conditions)
    query = f"SELECT f.id, f.name, f.email, u.username, f.phone, f.is_active, f.employee_id, f.designation, d.name AS department_name {query_base}"
    faculty, total_pages = paginate(query, tuple(params), page)
    connection, cursor = _cursor()
    departments = fetch_departments(cursor)
    if accessible_faculty_ids is not None:
        if accessible_faculty_ids:
            placeholders = ','.join(['%s'] * len(accessible_faculty_ids))
            active_query = _ACTIVE_COUNT + f" AND f.id IN ({placeholders})"
            inactive_query = _INACTIVE_COUNT + f" AND f.id IN ({placeholders})"
            total_active_faculty = fetch_faculty_totals(cursor, active_query, tuple(accessible_faculty_ids))
            total_inactive_faculty = fetch_faculty_totals(cursor, inactive_query, tuple(accessible_faculty_ids))
        else:
            total_active_faculty = 0
            total_inactive_faculty = 0
    else:
        total_active_faculty = fetch_faculty_totals(cursor, _ACTIVE_COUNT)
        total_inactive_faculty = fetch_faculty_totals(cursor, _INACTIVE_COUNT)
    total = fetch_faculty_totals(cursor, f"SELECT COUNT(f.id) AS total {query_base}", tuple(params))
    cursor.close()
    return {
        'faculty': faculty,
        'departments': departments,
        'total_pages': total_pages,
        'total_active_faculty': total_active_faculty,
        'total_inactive_faculty': total_inactive_faculty,
        'total': total,
    }


def add_faculty_member(username, password, name, email, department_id, phone, designation, is_active, employee_id):
    """Create a faculty member. Duplicate checks close both without rolling back."""
    connection, cursor = _cursor()
    try:
        if fetch_username(cursor, username):
            flash('Username already exists.', 'danger')
            return 'duplicate'
        if fetch_faculty_email(cursor, email):
            flash('Email already registered for a faculty member.', 'danger')
            return 'duplicate'
        user_id = insert_teacher_user(cursor, username, generate_password_hash(password))
        if not employee_id:
            employee_id = f"EMP{datetime.now().year}{user_id:06d}"
        insert_faculty_profile(cursor, (
            user_id, user_id, name, email, department_id, employee_id, phone, designation, is_active,
        ))
        connection.commit()
        flash('Faculty member added successfully.', 'success')
        return 'ok'
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error adding faculty: {str(exc)}")
        flash('Error adding faculty. Please try again.', 'danger')
        return 'error'
    finally:
        cursor.close()
        connection.close()


def find_faculty_form(faculty_id):
    """Return one faculty form row. The connection stays open."""
    connection, cursor = _cursor()
    row = fetch_faculty_form(cursor, faculty_id)
    cursor.close()
    return row


def change_faculty(faculty_id, name, email, department_id, phone, designation, is_active, password):
    """Update a faculty member. Both the cursor and connection are closed."""
    connection, cursor = _cursor()
    try:
        update_faculty_profile(cursor, (name, email, department_id, phone, designation, is_active, faculty_id))
        if password:
            result = fetch_faculty_user_id(cursor, faculty_id)
            if result and result['user_id']:
                update_user_password(cursor, generate_password_hash(password), result['user_id'])
        connection.commit()
        flash('Faculty member updated successfully.', 'success')
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error updating faculty: {str(exc)}")
        flash('Error updating faculty. Please try again.', 'danger')
    finally:
        cursor.close()
        connection.close()


def deactivate_selected_faculty(ids_to_delete):
    """Soft-delete faculty and their users. Both the cursor and connection are closed."""
    connection, cursor = _cursor()
    try:
        user_ids = [row['user_id'] for row in fetch_faculty_user_ids(cursor, ids_to_delete) if row.get('user_id')]
        deactivate_faculty(cursor, ids_to_delete)
        if user_ids:
            deactivate_faculty_users(cursor, user_ids)
        connection.commit()
        flash(f'{len(ids_to_delete)} faculty members deactivated.', 'success')
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error deactivating faculty: {str(exc)}")
        flash('Error deactivating faculty. Please try again.', 'danger')
    finally:
        cursor.close()
        connection.close()


def find_faculty_header(faculty_id):
    """Return a faculty name and email. The connection stays open."""
    connection, cursor = _cursor()
    row = fetch_faculty_name(cursor, faculty_id)
    cursor.close()
    return row


def _timetable_rows(cursor, faculty_user_id, with_rooms, without_rooms):
    try:
        rows = with_rooms(cursor, faculty_user_id)
        return rows, True
    except Exception:
        return without_rooms(cursor, faculty_user_id), False


def load_faculty_timetable(faculty_id):
    """Return timetable JSON rows, or missing. The connection stays open."""
    connection, cursor = _cursor()
    faculty_row = fetch_faculty_user_id(cursor, faculty_id)
    if not faculty_row or not faculty_row.get('user_id'):
        cursor.close()
        return 'missing'
    rows, has_room = _timetable_rows(cursor, faculty_row['user_id'], fetch_timetable_with_rooms, fetch_timetable_without_rooms)
    data = []
    for row in rows:
        data.append({
            'id': row['id'],
            'day': row['day_of_week'],
            'start_time': format_time(row['start_time']),
            'end_time': format_time(row['end_time']),
            'subject': row['subject_name'],
            'class': row['class_name'],
            'division': row['division_name'],
            'room': (row.get('room_number', '') if has_room else ''),
        })
    cursor.close()
    return data


def load_faculty_timetable_download(faculty_id):
    """Return download rows, or missing. The connection stays open."""
    connection, cursor = _cursor()
    faculty_row = fetch_faculty_user_id(cursor, faculty_id)
    if not faculty_row or not faculty_row.get('user_id'):
        cursor.close()
        return 'missing'
    rows, has_room = _timetable_rows(cursor, faculty_row['user_id'], fetch_download_with_rooms, fetch_download_without_rooms)
    cursor.close()
    return rows, has_room


def _save_form_availability(cursor, form, faculty_user_id):
    for day_name, day_num in _DAY_MAP.items():
        is_avail = form.get(f'{day_name}-available') == 'on'
        if is_avail:
            slot_index = 0
            while True:
                start_time = form.get(f'{day_name}-start-{slot_index}')
                end_time = form.get(f'{day_name}-end-{slot_index}')
                notes = form.get(f'{day_name}-notes-{slot_index}', '')
                shift_id = form.get(f'{day_name}-shift-{slot_index}') or None
                if not start_time or not end_time:
                    break
                insert_availability_slot(cursor, (faculty_user_id, day_num, shift_id, 1, start_time, end_time, notes))
                slot_index += 1
            if slot_index == 0:
                insert_unavailable_day(cursor, faculty_user_id, day_num)
        else:
            insert_unavailable_day(cursor, faculty_user_id, day_num)


def save_or_load_managed_availability(faculty_id, method, form):
    """Save or load the availability editor. A missing faculty leaves both open."""
    connection, cursor = _cursor()
    faculty_row = fetch_faculty_name_user(cursor, faculty_id)
    if not faculty_row:
        flash('Faculty not found.', 'danger')
        return 'missing'
    faculty_name = faculty_row['name']
    faculty_user_id = faculty_row['user_id']
    if method == 'POST':
        try:
            delete_faculty_availability(cursor, faculty_user_id)
            connection.commit()
            _save_form_availability(cursor, form, faculty_user_id)
            connection.commit()
            cursor.close()
            flash('Availability updated successfully.', 'success')
            return 'saved'
        except Exception as exc:
            connection.rollback()
            cursor.close()
            flash(f'Error updating availability: {str(exc)}', 'danger')
            return 'error'
    avail_all_slots = {day: [] for day in _DAY_NAMES.values()}
    for row in fetch_availability_slots(cursor, faculty_user_id):
        day_name = _DAY_NAMES.get(row['day_of_week'])
        if day_name:
            avail_all_slots[day_name].append({
                'is_available': bool(row['is_available']),
                'start_time': format_time(row['start_time']) if row['start_time'] else None,
                'end_time': format_time(row['end_time']) if row['end_time'] else None,
                'notes': row['notes'] or '',
                'shift_id': row['shift_pattern_id']
            })
    shift_patterns = []
    for row in fetch_active_shift_patterns(cursor):
        shift_patterns.append({
            'id': row['id'],
            'shift_name': row['shift_name'],
            'start_time': format_time(row['start_time']),
            'end_time': format_time(row['end_time'])
        })
    cursor.close()
    return {
        'faculty_name': faculty_name,
        'avail_all_slots': avail_all_slots,
        'shift_patterns': shift_patterns,
    }


def save_or_load_availability_api(faculty_id, method, form, json_data):
    """Update or return availability JSON. The connection stays open."""
    connection, cursor = _cursor()
    faculty_row = fetch_faculty_user_id(cursor, faculty_id)
    if not faculty_row or not faculty_row.get('user_id'):
        cursor.close()
        return 'missing'
    faculty_user_id = faculty_row['user_id']
    if method == 'POST':
        delete_faculty_availability(cursor, faculty_user_id)
        if json_data and 'availability' in json_data:
            for slot in json_data.get('availability', []):
                day_num = slot.get('day_num')
                if day_num:
                    insert_availability_slot(cursor, (
                        faculty_user_id,
                        day_num,
                        slot.get('shift_id'),
                        1 if slot.get('is_available', True) else 0,
                        slot.get('start_time'),
                        slot.get('end_time'),
                        slot.get('notes', ''),
                    ))
            connection.commit()
            cursor.close()
            return 'json_saved'
        _save_form_availability(cursor, form, faculty_user_id)
        connection.commit()
        cursor.close()
        flash('Availability updated.', 'success')
        return 'form_saved'
    avail_by_day = {day: [] for day in _DAY_NAMES.values()}
    for row in fetch_availability_with_shifts(cursor, faculty_user_id):
        day_name = _DAY_NAMES.get(row['day_of_week'])
        if day_name:
            start_time = row['start_time'] if row['start_time'] else row['sp_start']
            end_time = row['end_time'] if row['end_time'] else row['sp_end']
            avail_by_day[day_name].append({
                'is_available': bool(row['is_available']),
                'shift_id': row['shift_pattern_id'],
                'shift_name': row['shift_name'],
                'start_time': format_time(start_time) if start_time else None,
                'end_time': format_time(end_time) if end_time else None,
                'notes': row['notes'] or ''
            })
    shift_patterns = fetch_active_shift_patterns(cursor)
    cursor.close()
    return {
        'availability': avail_by_day,
        'shift_patterns': [{
            'id': pattern['id'],
            'name': pattern['shift_name'],
            'start_time': format_time(pattern['start_time']),
            'end_time': format_time(pattern['end_time'])
        } for pattern in shift_patterns]
    }


def load_faculty_absences(faculty_id):
    """Return absence JSON rows. The connection stays open."""
    connection, cursor = _cursor()
    items = []
    for row in fetch_absences(cursor, faculty_id):
        items.append({
            'id': row['id'],
            'absence_date': _date_text(row['absence_date']),
            'reason': row['reason'],
            'status': row['status'],
        })
    cursor.close()
    return items


def add_faculty_absence(faculty_id, absence_date_str, reason):
    """Store a processed absence and assign proxies. The connection stays open."""
    connection, cursor = _cursor()
    if not absence_date_str:
        cursor.close()
        return 'date'
    absence_date = datetime.strptime(absence_date_str, '%Y-%m-%d').date()
    insert_processed_absence(cursor, faculty_id, absence_date, reason)
    connection.commit()
    _admin_find_and_assign_proxy(faculty_id, absence_date)
    cursor.close()
    return 'ok'


def remove_faculty_absence(faculty_id, absence_id):
    """Delete an unprocessed absence. The connection stays open."""
    connection, cursor = _cursor()
    row = fetch_absence_status(cursor, absence_id, faculty_id)
    if not row:
        cursor.close()
        return 'missing'
    if row['status'] != 'UNPROCESSED':
        cursor.close()
        return 'processed'
    delete_absence(cursor, absence_id, faculty_id)
    connection.commit()
    cursor.close()
    return 'ok'


def approve_faculty_absence(faculty_id, absence_id):
    """Process an absence and assign proxies. The connection stays open."""
    connection, cursor = _cursor()
    row = fetch_absence_for_approval(cursor, absence_id, faculty_id)
    if not row:
        cursor.close()
        flash('Absence record not found.', 'danger')
        return 'missing'
    if row['status'] == 'PROCESSED':
        cursor.close()
        flash('Absence already processed.', 'info')
        return 'already'
    mark_absence_processed(cursor, absence_id, faculty_id)
    connection.commit()
    cursor.close()
    absence_date = row['absence_date']
    _admin_find_and_assign_proxy(
        faculty_id,
        absence_date if hasattr(absence_date, 'strftime') else datetime.strptime(str(absence_date), '%Y-%m-%d').date(),
    )
    flash('Absence approved and proxies assigned.', 'success')
    return 'ok'


def reject_faculty_absence(faculty_id, absence_id):
    """Reject an absence. The connection stays open."""
    connection, cursor = _cursor()
    reject_absence(cursor, absence_id, faculty_id)
    connection.commit()
    cursor.close()
    flash('Absence request rejected.', 'warning')


def load_faculty_proxy_log(faculty_id):
    """Return proxy JSON rows. The connection stays open."""
    connection, cursor = _cursor()
    rows = fetch_faculty_proxy_rows(cursor, faculty_id)
    cursor.close()
    items = []
    for row in rows:
        items.append({
            'id': row['id'],
            'absence_date': _date_text(row['absence_date']),
            'status': row['status'],
            'approval_status': row['approval_status'],
            'day': row['day_of_week'],
            'start_time': format_time(row['start_time']),
            'end_time': format_time(row['end_time']),
            'subject_id': row['subject_id'],
            'subject': row['subject_name'],
            'original_faculty_id': row['original_id'],
            'original_faculty': row['original_name'],
            'proxy_faculty_id': row['proxy_id'] or '',
            'proxy_faculty': row['proxy_name'] or '',
        })
    return items


def approve_faculty_proxy(faculty_id, proxy_id, selected_proxy_id, approved_by):
    """Approve a proxy request. The connection stays open."""
    connection, cursor = _cursor()
    faculty_row = fetch_faculty_user_id(cursor, faculty_id)
    if not faculty_row or not faculty_row.get('user_id'):
        cursor.close()
        return 'missing', None
    faculty_user_id = faculty_row['user_id']
    row = fetch_owned_proxy(cursor, proxy_id, faculty_user_id)
    if not row:
        cursor.close()
        return 'not_found', None
    if row['approval_status'] == 'APPROVED':
        cursor.close()
        flash('Proxy request already approved.', 'info')
        return 'already', None
    proxy_faculty_id = selected_proxy_id or row['proxy_faculty_id']
    if not proxy_faculty_id:
        candidates = [item['faculty_id'] for item in fetch_proxy_candidates(cursor, row['subject_id'], faculty_user_id)]
        for candidate in candidates:
            if _is_faculty_free(cursor, candidate, row['day_of_week'], row['start_time'], row['end_time']):
                proxy_faculty_id = candidate
                break
    final_status = 'ASSIGNED' if proxy_faculty_id else 'UNASSIGNED'
    approve_proxy_log(cursor, final_status, proxy_faculty_id, approved_by, proxy_id)
    connection.commit()
    cursor.close()
    flash('Proxy request approved successfully.', 'success')
    return 'ok', proxy_faculty_id


def reject_faculty_proxy(faculty_id, proxy_id, approved_by):
    """Reject a proxy request. The connection stays open."""
    connection, cursor = _cursor()
    faculty_row = fetch_faculty_user_id(cursor, faculty_id)
    if not faculty_row or not faculty_row.get('user_id'):
        cursor.close()
        return 'missing'
    reject_proxy_log(cursor, approved_by, proxy_id, faculty_row['user_id'])
    connection.commit()
    cursor.close()
    flash('Proxy request rejected.', 'warning')
    return 'ok'
