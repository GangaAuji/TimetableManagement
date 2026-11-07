
from flask import Blueprint, make_response, redirect, url_for, request, flash, current_app, jsonify
from ui.pages import render_template
from routes.faculty.teacher import format_time
from security import has_permission
from services.admin_rooms import (
    change_room,
    create_room as save_room,
    find_room,
    list_rooms,
    remove_room,
    room_schedule as load_room_schedule,
    room_utilization_rows,
)

rooms_bp = Blueprint('rooms', __name__, url_prefix='/admin/rooms')


@rooms_bp.route('/')
@has_permission('rooms_view_room')
def rooms_index():
    """List rooms and show add/edit modal."""
    rooms, departments = list_rooms()
    return render_template('legacy/admin/manage_rooms.html', rooms=rooms, departments=departments)


@rooms_bp.route('/<int:room_id>')
@has_permission('rooms_view_room')
def get_room(room_id):
    """Get room details for editing."""
    payload, status = find_room(room_id)
    return jsonify(payload), status


@rooms_bp.route('', methods=['POST'])
@has_permission('rooms_add_room')
def create_room():
    """Create a new room."""
    payload, status = save_room(
        request.form.get('room_number', ''),
        request.form.get('room_type', ''),
        request.form.get('capacity'),
        request.form.get('department_id'),
    )
    return jsonify(payload), status


@rooms_bp.route('/<int:room_id>', methods=['PUT'])
@has_permission('rooms_change_room')
def update_room(room_id):
    """Update an existing room."""
    payload, status = change_room(
        room_id,
        request.form.get('room_number', ''),
        request.form.get('room_type', ''),
        request.form.get('capacity'),
        request.form.get('department_id'),
    )
    return jsonify(payload), status


@rooms_bp.route('/<int:room_id>', methods=['DELETE'])
@has_permission('rooms_delete_room')
def delete_room(room_id):
    """Delete a room if it has no timetable entries."""
    payload, status = remove_room(room_id)
    return jsonify(payload), status


@rooms_bp.route('/<int:room_id>/schedule')
@has_permission('rooms_view_room')
def room_schedule(room_id):
    """Get the schedule for a specific room (all assigned slots)."""
    payload, status = load_room_schedule(room_id)
    return jsonify(payload), status


@rooms_bp.route('/utilization.csv', methods=['GET'])
@has_permission('rooms_view_room')
def rooms_utilization_csv():
    """Export room utilization across the timetable as a CSV.
    Columns: Room, Day, Start, End, Course, Class, Division, Subject, Faculty
    """
    rows, has_rooms = room_utilization_rows()
    import io, csv
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Room', 'Day', 'Start', 'End', 'Course', 'Class', 'Division', 'Subject', 'Faculty'])
    if has_rooms:
        for row in rows:
            room, day, st, et, course, cls, div, subj, fac = row
            writer.writerow([room or '', format_time(st), format_time(et), course, cls, div, subj, fac or ''])

    resp = make_response(output.getvalue())
    resp.headers['Content-Disposition'] = 'attachment; filename=room_utilization.csv'
    resp.headers['Content-Type'] = 'text/csv'
    return resp
