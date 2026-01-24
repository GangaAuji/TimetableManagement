from datetime import datetime
from flask import Blueprint, make_response, render_template, redirect, url_for, session, request, flash, current_app, jsonify
from werkzeug.security import generate_password_hash
from department_access import get_accessible_faculty_ids
from routes.admin_utils import _admin_find_and_assign_proxy, _is_faculty_free, admin_required, paginate, format_time
from security import has_permission
from database import get_db_connection

faculty_bp = Blueprint('faculty', __name__, url_prefix='/admin/faculty')

# --- Faculty Management (NEW CRUD) ---
@faculty_bp.route('/')
@has_permission('faculty_view_faculty')
def manage_faculty():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    department_filter = request.args.get('department_filter', '', type=str)
    
    query_base = "FROM faculty f LEFT JOIN departments d ON f.department_id = d.id"
    
    # Build WHERE clause
    where_conditions = []
    params = []
    
    # Apply department filtering based on user permissions
    user_id = session.get('user_id')
    accessible_faculty_ids = get_accessible_faculty_ids(user_id)
    
    if accessible_faculty_ids is not None:  # None means access to all
        if accessible_faculty_ids:  # Has specific access
            placeholders = ','.join(['%s'] * len(accessible_faculty_ids))
            where_conditions.append(f"f.id IN ({placeholders})")
            params.extend(accessible_faculty_ids)
        else:  # No access
            where_conditions.append("f.id = -1")  # Impossible condition
    
    if search:
        search_term = f"%{search}%"
        where_conditions.append("(f.name LIKE %s OR f.email LIKE %s OR f.employee_id LIKE %s)")
        params.extend([search_term, search_term, search_term])
    
    if department_filter:
        where_conditions.append("f.department_id = %s")
        params.append(department_filter)
    
    if where_conditions:
        query_base += " WHERE " + " AND ".join(where_conditions)

    # Fetch: id, name, email, username, phone, is_active, employee_id, designation, department_name
    query = f"SELECT f.id, f.name, f.email, u.username, f.phone, f.is_active, f.employee_id, f.designation, d.name {query_base.replace('FROM faculty f', 'FROM faculty f LEFT JOIN users u ON f.user_id = u.id')}"
    faculty, total_pages = paginate(query, tuple(params), page)
    
    connection = get_db_connection()

    
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM departments ORDER BY name")
    departments = cursor.fetchall()
    
    # Get total active and inactive faculty counts (without filters)
    total_active_query = "SELECT COUNT(f.id) AS total FROM faculty f WHERE f.is_active = 1"
    total_inactive_query = "SELECT COUNT(f.id) AS total FROM faculty f WHERE f.is_active = 0"
    
    # Respect department access permissions
    if accessible_faculty_ids is not None:
        if accessible_faculty_ids:
            placeholders = ','.join(['%s'] * len(accessible_faculty_ids))
            total_active_query += f" AND f.id IN ({placeholders})"
            total_inactive_query += f" AND f.id IN ({placeholders})"
            cursor.execute(total_active_query, tuple(accessible_faculty_ids))
            total_active_faculty = cursor.fetchone()['total']
            cursor.execute(total_inactive_query, tuple(accessible_faculty_ids))
            total_inactive_faculty = cursor.fetchone()['total']
        else:
            total_active_faculty = 0
            total_inactive_faculty = 0
    else:
        cursor.execute(total_active_query)
        total_active_faculty = cursor.fetchone()['total']
        cursor.execute(total_inactive_query)
        total_inactive_faculty = cursor.fetchone()['total']
    
    # Get filtered count (if filters are applied)
    count_query = f"SELECT COUNT(f.id) AS total {query_base}"
    cursor.execute(count_query, tuple(params))
    total = cursor.fetchone()['total']
    
    cursor.close()
    return render_template('admin/manage_faculty.html', faculty=faculty, departments=departments, page=page, total_pages=total_pages, search=search, total_active_faculty=total_active_faculty, total_inactive_faculty=total_inactive_faculty, total=total)

@faculty_bp.route('/add', methods=['POST'])
@has_permission('faculty_add_faculty')
def add_faculty():
    username = request.form.get('username')
    password = request.form.get('password')
    name = request.form.get('name')
    email = request.form.get('email')
    department_id = request.form.get('department_id')
    phone = request.form.get('phone', '')
    designation = request.form.get('designation', '')
    is_active = request.form.get('is_active', '1') == '1'
    employee_id = request.form.get('employee_id', '').strip()

    if not username or not password or not name:
        flash('Username, password, and name are required.', 'danger')
        return redirect(url_for('faculty.manage_faculty'))

    connection = get_db_connection()


    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id FROM users WHERE username = %s", [username])
        if cursor.fetchone():
            flash('Username already exists.', 'danger')
            return redirect(url_for('faculty.manage_faculty'))

        cursor.execute("SELECT id FROM faculty WHERE email = %s", [email])
        if cursor.fetchone():
            flash('Email already registered for a faculty member.', 'danger')
            return redirect(url_for('faculty.manage_faculty'))

        hashed = generate_password_hash(password)
        cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, 'Teacher')", (username, hashed))
        user_id = cursor.lastrowid
        
        # Generate unique employee_id if not provided
        if not employee_id:
            from datetime import datetime
            employee_id = f"EMP{datetime.now().year}{user_id:06d}"
        
        cursor.execute(
            """INSERT INTO faculty (id, user_id, name, email, department_id, employee_id, phone, designation, is_active) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (user_id, user_id, name, email, department_id, employee_id, phone, designation, is_active)
        )
        connection.commit()
        flash('Faculty member added successfully.', 'success')
    except Exception as e:
        connection.rollback()
        current_app.logger.error(f"Error adding faculty: {str(e)}")
        flash('Error adding faculty. Please try again.', 'danger')
    finally:

        cursor.close()

        connection.close()
    return redirect(url_for('faculty.manage_faculty'))

@faculty_bp.route('/get/<int:faculty_id>')
@has_permission('faculty_view_faculty')
def get_faculty(faculty_id):
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    cursor.execute("""
        SELECT f.name, f.email, f.department_id, u.username, f.phone, 
               f.employee_id, f.designation, f.is_active
        FROM faculty f 
        LEFT JOIN users u ON f.user_id = u.id 
        WHERE f.id = %s
    """, [faculty_id])
    faculty_member = cursor.fetchone()
    cursor.close()
    if faculty_member:
        return jsonify({
            'name': faculty_member[0],
            'email': faculty_member[1],
            'department_id': faculty_member[2],
            'username': faculty_member[3] or '',
            'phone': faculty_member[4] or '',
            'employee_id': faculty_member[5] or '',
            'designation': faculty_member[6] or '',
            'is_active': bool(faculty_member[7])
        })
    return jsonify({'error': 'Faculty not found'}), 404

@faculty_bp.route('/update/<int:faculty_id>', methods=['POST'])
@has_permission('faculty_change_faculty')
def update_faculty(faculty_id):
    name = request.form.get('name')
    email = request.form.get('email')
    department_id = request.form.get('department_id')
    phone = request.form.get('phone', '')
    designation = request.form.get('designation', '')
    is_active = request.form.get('is_active', '1') == '1'
    password = request.form.get('password')
    
    connection = get_db_connection()

    
    cursor = connection.cursor(dictionary=True)
    try:
        # Update faculty table
        cursor.execute(
            """UPDATE faculty 
               SET name=%s, email=%s, department_id=%s, phone=%s, designation=%s, is_active=%s 
               WHERE id=%s""",
            (name, email, department_id, phone, designation, is_active, faculty_id)
        )
        
        # Update password if provided
        if password:
            cursor.execute("SELECT user_id FROM faculty WHERE id = %s", [faculty_id])
            result = cursor.fetchone()
            if result and result[0]:
                user_id = result[0]
                hashed = generate_password_hash(password)
                cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed, user_id))
        
        connection.commit()
        flash('Faculty member updated successfully.', 'success')
    except Exception as e:
        connection.rollback()
        current_app.logger.error(f"Error updating faculty: {str(e)}")
        flash('Error updating faculty. Please try again.', 'danger')
    finally:

        cursor.close()

        connection.close()
    
    return redirect(url_for('faculty.manage_faculty'))

@faculty_bp.route('/bulk_delete', methods=['POST'])
@has_permission('faculty_delete_faculty')
def bulk_delete_faculty():
    ids_to_delete = request.form.getlist('faculty_ids')
    if ids_to_delete:
        connection = get_db_connection()

        cursor = connection.cursor(dictionary=True)
        format_strings = ','.join(['%s'] * len(ids_to_delete))
        # Without user_id FK, just delete faculty records
        cursor.execute(f"DELETE FROM faculty WHERE id IN ({format_strings})", tuple(ids_to_delete))
        connection.commit()
        flash(f'{len(ids_to_delete)} faculty members deleted.', 'success')
        cursor.close()
    return redirect(url_for('faculty.manage_faculty'))


@faculty_bp.route('/<int:faculty_id>/details')
@has_permission('faculty_view_faculty')   
def faculty_details(faculty_id):
    """Details dashboard for a faculty member (timetable, availability, absences, proxy log)."""
    # Basic lookup to show name/email in header
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT name, email FROM faculty WHERE id = %s", [faculty_id])
    fac = cursor.fetchone()
    cursor.close()
    if not fac:
        flash('Faculty not found.', 'danger')
        return redirect(url_for('faculty.manage_faculty'))
    return render_template('admin/faculty_details.html', faculty_id=faculty_id, faculty_name=fac[0], faculty_email=fac[1])


@faculty_bp.route('/<int:faculty_id>/timetable/data')
@has_permission('faculty_view_faculty')
def faculty_timetable_data(faculty_id):
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT t.id, t.day_of_week, t.start_time, t.end_time, s.name AS subject_name, c.name AS class_name, d.name AS division_name, r.room_number
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            JOIN divisions d ON t.division_id = d.id
            LEFT JOIN rooms r ON t.room_id = r.id
            WHERE t.faculty_id = %s
            ORDER BY FIELD(t.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'), t.start_time
            """,
            [faculty_id],
        )
        has_room = True
    except Exception:
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
        has_room = False
    data = []
    for row in cursor.fetchall():
        (tid, day, start_t, end_t, subj, cls, div, *rest) = row
        data.append({
            'id': tid,
            'day': day,
            'start_time': format_time(start_t),
            'end_time': format_time(end_t),
            'subject': subj,
            'class': cls,
            'division': div,
            'room': (rest[0] if (has_room and rest) else ''),
        })
    cursor.close()
    return jsonify({'data': data})


@faculty_bp.route('/<int:faculty_id>/timetable/download')
@has_permission('faculty_view_faculty')
def faculty_timetable_download(faculty_id):
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT t.day_of_week, t.start_time, t.end_time, s.name AS subject_name, c.name AS class_name, d.name AS division_name, r.room_number
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            JOIN divisions d ON t.division_id = d.id
            LEFT JOIN rooms r ON t.room_id = r.id
            WHERE t.faculty_id = %s
            ORDER BY FIELD(t.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'), t.start_time
            """,
            [faculty_id],
        )
        rows = cursor.fetchall()
        has_room = True
    except Exception:
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
        has_room = False
    cursor.close()

    import io, csv
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Day', 'Start', 'End', 'Subject', 'Class', 'Division', 'Room'])
    for row in rows:
        day, start_t, end_t, subj, cls, div = row['day_of_week'], row['start_time'], row['end_time'], row['subject_name'], row['class_name'], row['division_name']
        room = row['room_number'] if has_room else ''
        writer.writerow([day, format_time(start_t), format_time(end_t), subj, cls, div, room])

    resp = make_response(output.getvalue())
    resp.headers['Content-Disposition'] = f'attachment; filename=faculty_{faculty_id}_timetable.csv'
    resp.headers['Content-Type'] = 'text/csv'
    return resp


@faculty_bp.route('/<int:faculty_id>/availability/manage', methods=['GET', 'POST'])
@has_permission('faculty_change_faculty')
def manage_faculty_availability(faculty_id):
    """Admin UI for managing faculty availability (same interface as teacher panel)"""
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    
    # Get faculty name
    cursor.execute("SELECT name FROM faculty WHERE id = %s", [faculty_id])
    faculty_row = cursor.fetchone()
    if not faculty_row:
        flash('Faculty not found.', 'danger')
        return redirect(url_for('faculty.manage_faculty'))
    faculty_name = faculty_row[0]
    
    if request.method == 'POST':
        try:
            # Delete existing availability
            cursor.execute("DELETE FROM faculty_availability WHERE faculty_id = %s", [faculty_id])
            connection.commit()  # Commit DELETE immediately to avoid cursor issues
            
            # Map day names to numbers (1=Monday, 6=Saturday)
            day_map = {'Monday': 1, 'Tuesday': 2, 'Wednesday': 3, 'Thursday': 4, 'Friday': 5, 'Saturday': 6}
            
            for day_name, day_num in day_map.items():
                is_avail = request.form.get(f'{day_name}-available') == 'on'
                
                if is_avail:
                    # Collect all time slots for this day (indexed 0, 1, 2, ...)
                    slot_index = 0
                    while True:
                        start_time = request.form.get(f'{day_name}-start-{slot_index}')
                        end_time = request.form.get(f'{day_name}-end-{slot_index}')
                        notes = request.form.get(f'{day_name}-notes-{slot_index}', '')
                        shift_id = request.form.get(f'{day_name}-shift-{slot_index}') or None
                        
                        if not start_time or not end_time:
                            break
                        
                        # Store each time slot
                        cursor.execute(
                            """
                            INSERT INTO faculty_availability 
                            (faculty_id, day_of_week, shift_pattern_id, is_available, start_time, end_time, notes)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """,
                            (faculty_id, day_num, shift_id, 1, start_time, end_time, notes),
                        )
                        slot_index += 1
                    
                    # If no slots were added, add a default unavailable entry
                    if slot_index == 0:
                        cursor.execute(
                            """
                            INSERT INTO faculty_availability 
                            (faculty_id, day_of_week, is_available, start_time, end_time, notes)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (faculty_id, day_num, 0, None, None, ''),
                        )
                else:
                    # Mark as unavailable
                    cursor.execute(
                        """
                        INSERT INTO faculty_availability 
                        (faculty_id, day_of_week, is_available, start_time, end_time, notes)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (faculty_id, day_num, 0, None, None, ''),
                    )
            
            connection.commit()
            cursor.close()
            flash('Availability updated successfully.', 'success')
            return redirect(url_for('faculty.faculty_details', faculty_id=faculty_id))
        except Exception as e:
            connection.rollback()
            cursor.close()
            flash(f'Error updating availability: {str(e)}', 'danger')
            return redirect(url_for('faculty.manage_faculty_availability', faculty_id=faculty_id))
    
    # GET - Fetch ALL availability slots (not just first per day)
    cursor.execute("""
        SELECT day_of_week, is_available, start_time, end_time, notes, shift_pattern_id
        FROM faculty_availability
        WHERE faculty_id = %s
        ORDER BY day_of_week, start_time
    """, [faculty_id])
    
    # Map day numbers to names
    day_names = {1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday', 5: 'Friday', 6: 'Saturday'}
    
    # Collect ALL slots per day (not just first)
    avail_all_slots = {day: [] for day in day_names.values()}
    for day_num, is_avail, start_t, end_t, notes, shift_id in cursor.fetchall():
        day_name = day_names.get(day_num)
        if day_name:
            avail_all_slots[day_name].append({
                'is_available': bool(is_avail),
                'start_time': format_time(start_t) if start_t else None,
                'end_time': format_time(end_t) if end_t else None,
                'notes': notes or '',
                'shift_id': shift_id
            })
    
    # Fetch shift patterns for dropdown
    cursor.execute("SELECT id, shift_name, start_time, end_time FROM shift_patterns WHERE is_active = TRUE ORDER BY shift_order")
    shift_patterns = []
    for sp_id, sp_name, sp_start, sp_end in cursor.fetchall():
        shift_patterns.append({
            'id': sp_id,
            'shift_name': sp_name,
            'start_time': format_time(sp_start),
            'end_time': format_time(sp_end)
        })
    
    cursor.close()
    return render_template('admin/manage_availability.html', 
                         faculty_id=faculty_id, 
                         faculty_name=faculty_name, 
                         avail_all_slots=avail_all_slots,
                         shift_patterns=shift_patterns)


@faculty_bp.route('/<int:faculty_id>/availability', methods=['GET', 'POST'])
@has_permission('faculty_change_faculty')
def faculty_availability_admin(faculty_id):
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    if request.method == 'POST':
        # Support JSON format with time slot data (like teacher panel)
        json_data = request.get_json(silent=True)
        
        cursor.execute("DELETE FROM faculty_availability WHERE faculty_id = %s", [faculty_id])
        
        if json_data and 'availability' in json_data:
            # Format: array of {day_num, start_time, end_time, is_available, notes, shift_id (optional)}
            availability_slots = json_data.get('availability', [])
            for slot in availability_slots:
                day_num = slot.get('day_num')
                start_time = slot.get('start_time')
                end_time = slot.get('end_time')
                shift_id = slot.get('shift_id')  # Optional: can link to shift
                is_available = slot.get('is_available', True)
                notes = slot.get('notes', '')
                
                if day_num:
                    cursor.execute(
                        """
                        INSERT INTO faculty_availability 
                        (faculty_id, day_of_week, shift_pattern_id, is_available, start_time, end_time, notes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (faculty_id, day_num, shift_id, 1 if is_available else 0, start_time, end_time, notes),
                    )
            connection.commit()
            cursor.close()
            return jsonify({'ok': True, 'message': 'Availability updated successfully.'})
        else:
            # Form format: Support both time slots and shifts like teacher panel
            day_map = {'Monday': 1, 'Tuesday': 2, 'Wednesday': 3, 'Thursday': 4, 'Friday': 5, 'Saturday': 6}
            for day_name, day_num in day_map.items():
                is_avail = request.form.get(f'{day_name}-available') == 'on'
                
                if is_avail:
                    # Collect all time slots for this day (indexed 0, 1, 2, ...)
                    slot_index = 0
                    while True:
                        start_time = request.form.get(f'{day_name}-start-{slot_index}')
                        end_time = request.form.get(f'{day_name}-end-{slot_index}')
                        notes = request.form.get(f'{day_name}-notes-{slot_index}', '')
                        shift_id = request.form.get(f'{day_name}-shift-{slot_index}') or None
                        
                        if not start_time or not end_time:
                            break
                        
                        # Store each time slot
                        cursor.execute(
                            """
                            INSERT INTO faculty_availability 
                            (faculty_id, day_of_week, shift_pattern_id, is_available, start_time, end_time, notes)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """,
                            (faculty_id, day_num, shift_id, 1, start_time, end_time, notes),
                        )
                        slot_index += 1
                    
                    # If no slots were added, add a default unavailable entry
                    if slot_index == 0:
                        cursor.execute(
                            """
                            INSERT INTO faculty_availability 
                            (faculty_id, day_of_week, is_available, start_time, end_time, notes)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (faculty_id, day_num, 0, None, None, ''),
                        )
                else:
                    # Mark as unavailable
                    cursor.execute(
                        """
                        INSERT INTO faculty_availability 
                        (faculty_id, day_of_week, is_available, start_time, end_time, notes)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (faculty_id, day_num, 0, None, None, ''),
                    )
            connection.commit()
            cursor.close()
            flash('Availability updated.', 'success')
            return redirect(url_for('faculty.faculty_details', faculty_id=faculty_id))

    # GET handler - return availability with time slots (either from shift_patterns or custom)
    cursor.execute(
        """SELECT fa.day_of_week, fa.is_available, fa.shift_pattern_id, fa.notes,
                  fa.start_time, fa.end_time,
                  sp.shift_name, sp.start_time as sp_start, sp.end_time as sp_end
           FROM faculty_availability fa
           LEFT JOIN shift_patterns sp ON fa.shift_pattern_id = sp.id
           WHERE fa.faculty_id = %s
           ORDER BY fa.day_of_week, fa.start_time""",
        [faculty_id],
    )
    
    # Map day numbers to names
    day_names = {1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday', 5: 'Friday', 6: 'Saturday'}
    avail_by_day = {day: [] for day in day_names.values()}
    
    for day_num, is_avail, shift_id, notes, fa_start, fa_end, shift_name, sp_start, sp_end in cursor.fetchall():
        day_name = day_names.get(day_num)
        if day_name:
            # Prefer faculty_availability times over shift_pattern times
            start_time = fa_start if fa_start else sp_start
            end_time = fa_end if fa_end else sp_end
            
            avail_by_day[day_name].append({
                'is_available': bool(is_avail),
                'shift_id': shift_id,
                'shift_name': shift_name,
                'start_time': format_time(start_time) if start_time else None,
                'end_time': format_time(end_time) if end_time else None,
                'notes': notes or ''
            })
    
    # Fetch all shift patterns for dropdown
    cursor.execute("SELECT id, shift_name, start_time, end_time FROM shift_patterns WHERE is_active = TRUE ORDER BY shift_order")
    shift_patterns = cursor.fetchall()
    
    cursor.close()
    
    # Return data for the template
    return jsonify({
        'availability': avail_by_day,
        'shift_patterns': [{
            'id': sp[0],
            'name': sp[1],
            'start_time': format_time(sp[2]),
            'end_time': format_time(sp[3])
        } for sp in shift_patterns]
    })


@faculty_bp.route('/<int:faculty_id>/absences', methods=['GET', 'POST'])
@has_permission('faculty_change_faculty')
def faculty_absences_admin(faculty_id):
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    if request.method == 'GET':
        cursor.execute(
            "SELECT id, absence_date, reason, status FROM faculty_absences WHERE faculty_id = %s ORDER BY absence_date DESC",
            [faculty_id],
        )
        items = [
            {
                'id': rid,
                'absence_date': ad.strftime('%Y-%m-%d') if isinstance(ad, (datetime,)) or (hasattr(ad, 'strftime')) else str(ad),
                'reason': rsn,
                'status': st,
            }
            for (rid, ad, rsn, st) in cursor.fetchall()
        ]
        cursor.close()
        return jsonify({'data': items})

    # POST create absence
    data = request.get_json(silent=True) or {}
    absence_date_str = data.get('absence_date') or request.form.get('absence_date')
    reason = data.get('reason') or request.form.get('reason')
    if not absence_date_str:
        cursor.close()
        return jsonify({'ok': False, 'error': 'absence_date required'}), 400
    ad = datetime.strptime(absence_date_str, '%Y-%m-%d').date()
    cursor.execute(
        "INSERT INTO faculty_absences (faculty_id, absence_date, reason, status) VALUES (%s, %s, %s, 'PROCESSED')",
        (faculty_id, ad, reason),
    )
    connection.commit()
    _admin_find_and_assign_proxy(faculty_id, ad)
    cursor.close()
    return jsonify({'ok': True})


@faculty_bp.route('/<int:faculty_id>/absences/<int:absence_id>', methods=['DELETE'])
@has_permission('faculty_delete_faculty')
def faculty_absence_delete_admin(faculty_id, absence_id):
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
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
    connection.commit()
    cursor.close()
    return jsonify({'ok': True})


@faculty_bp.route('/<int:faculty_id>/absences/<int:absence_id>/approve', methods=['POST'])
@has_permission('faculty_change_faculty')
def faculty_absence_approve_admin(faculty_id, absence_id):
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    # ensure exists and get date
    cursor.execute(
        "SELECT absence_date, status FROM faculty_absences WHERE id = %s AND faculty_id = %s",
        (absence_id, faculty_id),
    )
    row = cursor.fetchone()
    if not row:
        cursor.close()
        flash('Absence record not found.', 'danger')
        return jsonify({'ok': False, 'error': 'Not found'}), 404
    absence_date, st = row
    if st == 'PROCESSED':
        cursor.close()
        flash('Absence already processed.', 'info')
        return jsonify({'ok': True})
    # approve
    cursor.execute(
        "UPDATE faculty_absences SET status = 'PROCESSED' WHERE id = %s AND faculty_id = %s",
        (absence_id, faculty_id),
    )
    connection.commit()
    cursor.close()
    # trigger proxy assignment
    _admin_find_and_assign_proxy(faculty_id, absence_date if hasattr(absence_date, 'strftime') else datetime.strptime(str(absence_date), '%Y-%m-%d').date())
    flash('Absence approved and proxies assigned.', 'success')
    return jsonify({'ok': True})


@faculty_bp.route('/<int:faculty_id>/absences/<int:absence_id>/reject', methods=['POST'])
@has_permission('faculty_change_faculty')
def faculty_absence_reject_admin(faculty_id, absence_id):
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        "UPDATE faculty_absences SET status = 'REJECTED' WHERE id = %s AND faculty_id = %s AND status != 'PROCESSED'",
        (absence_id, faculty_id),
    )
    connection.commit()
    cursor.close()
    flash('Absence request rejected.', 'warning')
    return jsonify({'ok': True})


@faculty_bp.route('/<int:faculty_id>/proxy-log')
@has_permission('faculty_view_faculty')
def faculty_proxy_log_admin(faculty_id):
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT p.id, p.absence_date, p.status, p.approval_status, t.day_of_week, t.start_time, t.end_time, 
               s.id AS subject_id, s.name AS subject_name,
               ofc.id AS original_id, ofc.name AS original_name, 
               pfc.id AS proxy_id, pfc.name AS proxy_name
        FROM proxy_log p
        JOIN timetable t ON p.timetable_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        JOIN faculty ofc ON ofc.user_id = p.original_faculty_id
        LEFT JOIN faculty pfc ON pfc.user_id = p.proxy_faculty_id
        WHERE ofc.id = %s OR pfc.id = %s
        ORDER BY p.absence_date DESC, t.start_time
        """,
        (faculty_id, faculty_id),
    )
    rows = cursor.fetchall()
    cursor.close()

    items = []
    for rid, ad, status, approval_status, day, st, et, subj_id, subj, orig_id, orig, proxy_id, proxy in rows:
        ad_str = ad.strftime('%Y-%m-%d') if hasattr(ad, 'strftime') else str(ad)
        items.append({
            'id': rid,
            'absence_date': ad_str,
            'status': status,
            'approval_status': approval_status,
            'day': day,
            'start_time': format_time(st),
            'end_time': format_time(et),
            'subject_id': subj_id,
            'subject': subj,
            'original_faculty_id': orig_id,
            'original_faculty': orig,
            'proxy_faculty_id': proxy_id or '',
            'proxy_faculty': proxy or '',
        })
    return jsonify({'data': items})


@faculty_bp.route('/<int:faculty_id>/proxy-log/<int:proxy_id>/approve', methods=['POST'])
@has_permission('faculty_change_faculty')
def faculty_proxy_approve_admin(faculty_id, proxy_id):
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    
    # Get proxy_faculty_id from request (admin may have selected one)
    data = request.get_json(silent=True) or {}
    selected_proxy_id = data.get('proxy_faculty_id')
    
    # fetch record
    cursor.execute(
        """
        SELECT p.timetable_id, p.proxy_faculty_id, p.approval_status, t.day_of_week, t.start_time, t.end_time, t.subject_id
        FROM proxy_log p
        JOIN timetable t ON p.timetable_id = t.id
        WHERE p.id = %s AND (p.original_faculty_id = %s OR p.proxy_faculty_id = %s)
        """,
        (proxy_id, faculty_id, faculty_id),
    )
    row = cursor.fetchone()
    if not row:
        cursor.close()
        return jsonify({'ok': False, 'error': 'Not found'}), 404
    
    timetable_id, existing_proxy_id, approval_status, day, st, et, subject_id = row
    
    if approval_status == 'APPROVED':
        cursor.close()
        flash('Proxy request already approved.', 'info')
        return jsonify({'ok': True})

    # Use selected proxy if provided, otherwise existing, otherwise auto-assign
    proxy_faculty_id = selected_proxy_id or existing_proxy_id
    
    if not proxy_faculty_id:
        # Auto-assign: find qualified faculty who is free
        cursor.execute(
            "SELECT faculty_id FROM faculty_allocations WHERE subject_id = %s AND faculty_id != %s",
            (subject_id, faculty_id),
        )
        cands = [r[0] for r in cursor.fetchall()]
        for cand in cands:
            if _is_faculty_free(cursor, cand, day, st, et):
                proxy_faculty_id = cand
                break

    # Set approval status and assignment
    final_status = 'ASSIGNED' if proxy_faculty_id else 'UNASSIGNED'
    cursor.execute(
        """
        UPDATE proxy_log 
        SET approval_status = 'APPROVED', 
            status = %s, 
            proxy_faculty_id = %s,
            approval_date = NOW(),
            approved_by = %s
        WHERE id = %s
        """,
        (final_status, proxy_faculty_id, session.get('user_id'), proxy_id),
    )
    connection.commit()
    cursor.close()
    
    flash('Proxy request approved successfully.', 'success')
    return jsonify({'ok': True, 'proxy_faculty_id': proxy_faculty_id})


@faculty_bp.route('/<int:faculty_id>/proxy-log/<int:proxy_id>/reject', methods=['POST'])
@has_permission('faculty_change_faculty')
def faculty_proxy_reject_admin(faculty_id, proxy_id):
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        UPDATE proxy_log 
        SET approval_status = 'REJECTED',
            status = 'REJECTED',
            approval_date = NOW(),
            approved_by = %s
        WHERE id = %s AND (original_faculty_id = %s OR proxy_faculty_id = %s)
        """,
        (session.get('user_id'), proxy_id, faculty_id, faculty_id),
    )
    connection.commit()
    cursor.close()
    flash('Proxy request rejected.', 'warning')
    return jsonify({'ok': True})
