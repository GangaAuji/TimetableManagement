"""Faculty shift management. Uses a private MySQL connection, not the shared helper."""

import mysql.connector
from flask import flash

from config import Config
from data_access.admin_shifts import (
    count_active_shifts,
    count_faculty_with_shifts,
    count_shift_usage,
    delete_shift_pattern,
    fetch_active_departments,
    fetch_active_faculty,
    fetch_active_patterns,
    fetch_active_shift_choices,
    fetch_availability_records,
    fetch_change_request,
    fetch_change_requests,
    fetch_day_availability,
    fetch_day_availability_id,
    fetch_faculty_available_days,
    fetch_shift_by_name,
    fetch_shift_patterns,
    insert_day_availability,
    insert_shift_pattern,
    update_change_request,
    update_day_availability,
    update_shift_pattern,
    upsert_approved_availability,
)


def get_db_connection():
    """Get database connection"""
    return mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB
    )


def _format_time_td(td):
    if td is None:
        return None
    if isinstance(td, str):
        return td[:5]
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return f"{hours:02d}:{minutes:02d}"


def load_shift_dashboard():
    """Return shift patterns and counts. Both the cursor and connection are closed."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        return {
            'shift_patterns': fetch_shift_patterns(cursor),
            'active_shifts_count': count_active_shifts(cursor)['count'],
            'faculty_with_shifts_count': count_faculty_with_shifts(cursor)['count'],
        }
    finally:
        cursor.close()
        connection.close()


def add_shift_pattern(shift_name, shift_code, start_time, end_time, shift_order, description, is_active):
    """Insert a shift pattern. Both the cursor and connection are closed."""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        insert_shift_pattern(cursor, (
            shift_name, shift_code, start_time, end_time, shift_order, description, is_active,
        ))
        connection.commit()
        flash(f'Shift pattern "{shift_name}" added successfully!', 'success')
    except Exception as exc:
        connection.rollback()
        flash(f'Error adding shift pattern: {str(exc)}', 'danger')
    finally:
        cursor.close()
        connection.close()


def edit_shift_pattern(shift_id, shift_name, shift_code, start_time, end_time, shift_order, description, is_active):
    """Update a shift pattern. Both the cursor and connection are closed."""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        update_shift_pattern(cursor, (
            shift_name, shift_code, start_time, end_time, shift_order, description, is_active, shift_id,
        ))
        connection.commit()
        flash(f'Shift pattern "{shift_name}" updated successfully!', 'success')
    except Exception as exc:
        connection.rollback()
        flash(f'Error updating shift pattern: {str(exc)}', 'danger')
    finally:
        cursor.close()
        connection.close()


def remove_shift_pattern(shift_id):
    """Delete an unused shift pattern. The usage lookup uses a non-dictionary cursor."""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        usage_count = count_shift_usage(cursor, shift_id)['count']
        if usage_count > 0:
            flash(f'Cannot delete shift pattern: it is assigned to {usage_count} faculty member(s)', 'danger')
        else:
            delete_shift_pattern(cursor, shift_id)
            connection.commit()
            flash('Shift pattern deleted successfully!', 'success')
    except Exception as exc:
        connection.rollback()
        flash(f'Error deleting shift pattern: {str(exc)}', 'danger')
    finally:
        cursor.close()
        connection.close()


def load_faculty_availability():
    """Return faculty availability for the admin page. Both the cursor and connection are closed."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        faculty_list = fetch_active_faculty(cursor)
        availability_records = fetch_availability_records(cursor)
        availability_map = {}
        for record in availability_records:
            faculty_id = record['faculty_id']
            day = record['day_of_week']
            if faculty_id not in availability_map:
                availability_map[faculty_id] = {}
            if day not in availability_map[faculty_id]:
                availability_map[faculty_id][day] = []
            if record['shift_pattern_id']:
                display_text = record['shift_code']
                shift_start_str = _format_time_td(record['shift_start'])
                shift_end_str = _format_time_td(record['shift_end'])
                time_range = f"{shift_start_str} - {shift_end_str}" if shift_start_str else ''
            elif record['start_time'] and record['end_time']:
                start_str = _format_time_td(record['start_time'])
                end_str = _format_time_td(record['end_time'])
                display_text = f"{start_str}-{end_str}"
                time_range = f"{start_str} - {end_str}"
            else:
                display_text = 'Available'
                time_range = ''
            availability_map[faculty_id][day].append({
                'is_available': bool(record['is_available']),
                'shift_pattern_id': record['shift_pattern_id'],
                'shift_code': record['shift_code'],
                'shift_name': record['shift_name'],
                'start_time': record['start_time'],
                'end_time': record['end_time'],
                'notes': record['notes'],
                'display_text': display_text,
                'time_range': time_range
            })
        faculty_with_availability = []
        for faculty in faculty_list:
            user_availability = availability_map.get(faculty['user_id'], {})
            day_summary = {}
            for day, slots in user_availability.items():
                if slots:
                    day_summary[day] = slots[0]
                    day_summary[day]['all_slots'] = slots
            faculty_with_availability.append({
                'faculty': faculty,
                'availability': day_summary
            })
        return {
            'faculty_list': faculty_with_availability,
            'shift_patterns': fetch_active_shift_choices(cursor),
            'departments': fetch_active_departments(cursor),
        }
    finally:
        cursor.close()
        connection.close()


def set_day_availability(data):
    """Update one faculty day. Both the cursor and connection are closed."""
    faculty_user_id = data.get('faculty_id')
    day_of_week = data.get('day_of_week')
    is_available = 1 if data.get('is_available') else 0
    shift_pattern_id = data.get('shift_pattern_id') if 'shift_pattern_id' in data else None
    notes = data.get('notes', '')
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        existing = fetch_day_availability(cursor, faculty_user_id, day_of_week)
        if existing:
            update_shift_id = shift_pattern_id if 'shift_pattern_id' in data else existing['shift_pattern_id']
            update_notes = notes if notes else existing['notes']
            update_day_availability(cursor, is_available, update_shift_id, update_notes, existing['id'])
        else:
            insert_day_availability(
                cursor, faculty_user_id, day_of_week, is_available, shift_pattern_id, notes,
            )
        connection.commit()
        return {'success': True, 'message': 'Availability updated successfully'}
    except Exception as exc:
        connection.rollback()
        return {'success': False, 'message': f'Error updating availability: {str(exc)}', 'status': 500}
    finally:
        cursor.close()
        connection.close()


def bulk_set_day_availability(faculty_user_ids, shift_pattern_id, days, is_available, notes):
    """Update many faculty days. The lookup cursor is not a dictionary cursor."""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        updated_count = 0
        for faculty_user_id in faculty_user_ids:
            for day in days:
                existing = fetch_day_availability_id(cursor, faculty_user_id, day)
                if existing:
                    update_day_availability(cursor, is_available, shift_pattern_id, notes, existing[0])
                else:
                    insert_day_availability(
                        cursor, faculty_user_id, day, is_available, shift_pattern_id, notes,
                    )
                updated_count += 1
        connection.commit()
        flash(f'Bulk availability updated successfully! ({updated_count} assignments)', 'success')
    except Exception as exc:
        connection.rollback()
        flash(f'Error updating bulk availability: {str(exc)}', 'danger')
    finally:
        cursor.close()
        connection.close()


def faculty_availability_api(faculty_user_id):
    """Return one faculty user's available days. Both the cursor and connection are closed."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        return fetch_faculty_available_days(cursor, faculty_user_id)
    finally:
        cursor.close()
        connection.close()


def shift_patterns_api():
    """Return active shift patterns. Both the cursor and connection are closed."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        return fetch_active_patterns(cursor)
    finally:
        cursor.close()
        connection.close()


def load_change_requests():
    """Return shift change requests. Both the cursor and connection are closed."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        requests = fetch_change_requests(cursor)
        pending_count = sum(1 for row in requests if row['status'] == 'pending')
        return {'requests': requests, 'pending_count': pending_count}
    finally:
        cursor.close()
        connection.close()


def respond_change_request(request_id, action, admin_response, user_id):
    """Review a shift change request. A missing request still closes both."""
    status = 'approved' if action == 'approve' else 'rejected'
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        req = fetch_change_request(cursor, request_id)
        if not req:
            flash('Request not found.', 'danger')
            return 'missing'
        update_change_request(cursor, status, admin_response, user_id, request_id)
        if action == 'approve':
            shift = fetch_shift_by_name(cursor, req['requested_shift_name'])
            shift_id = shift['id'] if shift else None
            upsert_approved_availability(cursor, req['faculty_id'], req['day_of_week'], shift_id)
        connection.commit()
        flash(f'Request {status} successfully!', 'success')
        return 'ok'
    except Exception as exc:
        connection.rollback()
        flash(f'Error processing request: {str(exc)}', 'danger')
        return 'error'
    finally:
        cursor.close()
        connection.close()
