
from flask import Blueprint, make_response, render_template, redirect, url_for, request, flash, current_app, jsonify
from routes.faculty.teacher import format_time
from security import has_permission
from database import get_db_connection

rooms_bp = Blueprint('rooms', __name__, url_prefix='/admin/rooms')


# --- Room Management ---
@rooms_bp.route('/')
@has_permission('rooms_view_room')
def rooms_index():
    """List rooms and show add/edit modal."""
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    
    # Get all departments for filters
    cursor.execute("SELECT id, name FROM departments ORDER BY name")
    departments = [{'id': row['id'], 'name': row['name']} for row in cursor.fetchall()]
    
    # Get all rooms with department info
    cursor.execute("""
        SELECT r.id, r.room_number, r.room_type, r.capacity, r.department_id,
               d.name AS department_name
        FROM rooms r
        LEFT JOIN departments d ON r.department_id = d.id
        ORDER BY r.room_type, r.room_number
    """)
    rooms = []
    for row in cursor.fetchall():
        rooms.append({
            'id': row['id'],
            'room_number': row['room_number'],
            'room_type': row['room_type'],
            'capacity': row['capacity'],
            'department_id': row['department_id'],
            'department_name': row['department_name'],
        })

    cursor.close()
    return render_template('admin/manage_rooms.html', rooms=rooms, departments=departments)


@rooms_bp.route('/<int:room_id>')
@has_permission('rooms_view_room')
def get_room(room_id):
    """Get room details for editing."""
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, room_number, room_type, capacity, department_id
        FROM rooms WHERE id = %s
    """, (room_id,))
    row = cursor.fetchone()
    cursor.close()
    if not row:
        return jsonify({'ok': False, 'error': 'Room not found'}), 404
    return jsonify({
        'id': row['id'],
        'room_number': row['room_number'],
        'room_type': row['room_type'],
        'capacity': row['capacity'],
        'department_id': row['department_id'],
    })


@rooms_bp.route('', methods=['POST'])
@has_permission('rooms_add_room')
def create_room():
    """Create a new room."""
    room_number = request.form.get('room_number', '').strip()
    room_type = request.form.get('room_type', '').strip()
    capacity = request.form.get('capacity')
    department_id = request.form.get('department_id') or None

    if not room_number or not room_type or not capacity:
        return jsonify({'ok': False, 'error': 'Room number, type, and capacity are required.'}), 400
    try:
        capacity = int(capacity)
        if capacity < 1:
            raise ValueError()
    except ValueError:
        return jsonify({'ok': False, 'error': 'Capacity must be a positive number.'}), 400

    connection = get_db_connection()


    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT 1 FROM rooms WHERE room_number = %s", (room_number,))
        if cursor.fetchone():
            return jsonify({'ok': False, 'error': 'Room number already exists.'}), 400

        cursor.execute(
            "INSERT INTO rooms (room_number, room_type, capacity, department_id) VALUES (%s, %s, %s, %s)",
            (room_number, room_type, capacity, department_id)
        )
        connection.commit()
        flash('Room added successfully.', 'success')
        return jsonify({'ok': True})
    except Exception as e:
        connection.rollback()
        current_app.logger.error(f"Error creating room: {str(e)}")
        return jsonify({'ok': False, 'error': 'Failed to create room.'}), 500
    finally:

        cursor.close()

        connection.close()


@rooms_bp.route('/<int:room_id>', methods=['PUT'])
@has_permission('rooms_change_room')
def update_room(room_id):
    """Update an existing room."""
    room_number = request.form.get('room_number', '').strip()
    room_type = request.form.get('room_type', '').strip()
    capacity = request.form.get('capacity')
    department_id = request.form.get('department_id') or None

    if not room_number or not room_type or not capacity:
        return jsonify({'ok': False, 'error': 'Room number, type, and capacity are required.'}), 400
    try:
        capacity = int(capacity)
        if capacity < 1:
            raise ValueError()
    except ValueError:
        return jsonify({'ok': False, 'error': 'Capacity must be a positive number.'}), 400

    connection = get_db_connection()


    cursor = connection.cursor(dictionary=True)
    try:
        # Check if number exists but not this room
        cursor.execute("SELECT 1 FROM rooms WHERE room_number = %s AND id != %s", (room_number, room_id))
        if cursor.fetchone():
            return jsonify({'ok': False, 'error': 'Room number already exists.'}), 400

        cursor.execute(
            "UPDATE rooms SET room_number = %s, room_type = %s, capacity = %s, department_id = %s WHERE id = %s",
            (room_number, room_type, capacity, department_id, room_id)
        )
        connection.commit()
        flash('Room updated successfully.', 'success')
        return jsonify({'ok': True})
    except Exception as e:
        connection.rollback()
        current_app.logger.error(f"Error updating room: {str(e)}")
        return jsonify({'ok': False, 'error': 'Failed to update room.'}), 500
    finally:

        cursor.close()

        connection.close()


@rooms_bp.route('/<int:room_id>', methods=['DELETE'])
@has_permission('rooms_delete_room')
def delete_room(room_id):
    """Delete a room if it has no timetable entries."""
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    try:
        # Check if room is in use
        cursor.execute("SELECT 1 FROM timetable WHERE room_id = %s LIMIT 1", (room_id,))
        if cursor.fetchone():
            return jsonify({'ok': False, 'error': 'Cannot delete room: it is used in timetable entries.'}), 400

        cursor.execute("DELETE FROM rooms WHERE id = %s", (room_id,))
        connection.commit()
        flash('Room deleted successfully.', 'success')
        return jsonify({'ok': True})
    except Exception as e:
        connection.rollback()
        current_app.logger.error(f"Error deleting room: {str(e)}")
        return jsonify({'ok': False, 'error': 'Failed to delete room.'}), 500
    finally:

        cursor.close()

        connection.close()


@rooms_bp.route('/<int:room_id>/schedule')
@has_permission('rooms_view_room')
def room_schedule(room_id):
    """Get the schedule for a specific room (all assigned slots)."""
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT t.day_of_week, t.start_time, t.end_time,
                   s.name AS subject_name,
                   c.name AS class_name,
                   d.name AS division_name,
                   f.name AS faculty_name
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            JOIN divisions d ON t.division_id = d.id
            LEFT JOIN faculty f ON t.faculty_id = f.id
            WHERE t.room_id = %s
            ORDER BY FIELD(t.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'),
                     t.start_time
        """, (room_id,))
        schedule = []
        for row in cursor.fetchall():
            schedule.append({
                'day': row['day_of_week'],
                'start_time': format_time(row['start_time']),
                'end_time': format_time(row['end_time']),
                'subject_name': row['subject_name'],
                'class_name': row['class_name'],
                'division_name': row['division_name'],
                'faculty_name': row['faculty_name'] or '',
            })
        return jsonify({'ok': True, 'schedule': schedule})
    except Exception as e:
        current_app.logger.error(f"Error fetching room schedule: {str(e)}")
        return jsonify({'ok': False, 'error': 'Failed to fetch schedule.'}), 500
    finally:

        cursor.close()

        connection.close()


@rooms_bp.route('/utilization.csv', methods=['GET'])
@has_permission('rooms_view_room')
def rooms_utilization_csv():
    """Export room utilization across the timetable as a CSV.
    Columns: Room, Day, Start, End, Course, Class, Division, Subject, Faculty
    """
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    try:
        # Prefer joining rooms if timetable has room_id; otherwise, return an empty CSV with header
        try:
            cursor.execute(
                """
                SELECT 
                    COALESCE(r.room_number, '') AS room_number,
                    t.day_of_week,
                    t.start_time,
                    t.end_time,
                    co.name AS course_name,
                    cl.name AS class_name,
                    dv.name AS division_name,
                    s.name AS subject_name,
                    COALESCE(f.name, '') AS faculty_name
                FROM timetable t
                LEFT JOIN rooms r ON t.room_id = r.id
                JOIN subjects s ON s.id = t.subject_id
                JOIN courses co ON co.id = t.course_id
                JOIN classes cl ON cl.id = t.class_id
                JOIN divisions dv ON dv.id = t.division_id
                LEFT JOIN faculty f ON f.user_id = t.faculty_id
                WHERE t.room_id IS NOT NULL
                ORDER BY r.room_number, FIELD(t.day_of_week,'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'), t.start_time
                """
            )
            rows = cursor.fetchall()
            has_rooms = True
        except Exception:
            rows = []
            has_rooms = False
    finally:

        cursor.close()

        connection.close()

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
