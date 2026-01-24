from flask import Blueprint, render_template, request, flash, current_app
from routes.timetable_algorithm import WEEKDAY_ORDER, generate_timetable_for_class
from routes.admin_utils import format_time
from security import has_permission
from database import get_db_connection
from datetime import date, time, timedelta, datetime

timetable_bp = Blueprint('timetable', __name__, url_prefix='/admin/timetable')


@timetable_bp.route('/generate', methods=['GET', 'POST'])
@has_permission('timetable_generate')
def generate_timetable():
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    current_app.logger.debug('Entered generate_timetable endpoint; method=%s', request.method)
    cursor.execute("SELECT id, name FROM courses"); courses = cursor.fetchall()
    cursor.execute("SELECT id, name FROM classes"); classes = cursor.fetchall()
    cursor.execute("SELECT id, name FROM divisions"); divisions = cursor.fetchall()
    # default form state for UI persistence
    default_config = {
        'week_start_date': date.today().isoformat(),
        'day_start': '09:00',
        'day_end': '15:00',
        'lecture_minutes': 45,
        'break_start': '',
        'break_duration': 0,
        'working_days': WEEKDAY_ORDER[:6],
    }
    form_state = default_config.copy()
    generation_result = None
    selected_course = None
    selected_class = None
    selected_division = None

    if request.method == 'POST':
        # Debug: log incoming form keys to trace client submit activity
        try:
            current_app.logger.info('generate_timetable POST received; form keys: %s', list(request.form.keys()))
        except Exception:
            current_app.logger.exception('Failed to log generate_timetable form keys')
        course_id = request.form.get('course')
        class_id = request.form.get('class')
        division_id = request.form.get('division')
        selected_course = course_id
        selected_class = class_id
        selected_division = division_id

        # Auto-detect lecture duration based on course program type (PG=60min, UG=45min)
        # This overrides the form input to ensure correct duration per program
        default_lecture_minutes = default_config['lecture_minutes']
        if course_id:
            cursor.execute("SELECT program FROM courses WHERE id = %s", (course_id,))
            course_row = cursor.fetchone()
            if course_row:
                program = course_row[0] if course_row[0] else 'UG'  # Access by index since cursor is not DictCursor
                default_lecture_minutes = 60 if program == 'PG' else 45

        form_state['week_start_date'] = request.form.get('week_start_date') or ''
        form_state['day_start'] = request.form.get('day_start') or default_config['day_start']
        form_state['day_end'] = request.form.get('day_end') or default_config['day_end']
        form_state['lecture_minutes'] = int(request.form.get('lecture_minutes') or default_lecture_minutes)
        form_state['break_start'] = request.form.get('break_start') or ''
        form_state['break_duration'] = int(request.form.get('break_duration') or 0)
        form_state['working_days'] = request.form.getlist('working_days') or default_config['working_days']

        # Call generator and log timing to diagnose long-running executions
        try:
            current_app.logger.info('Starting timetable generation for course=%s class=%s division=%s', course_id, class_id, division_id)
            start_ts = datetime.now()
            result = generate_timetable_for_class(
                course_id,
                class_id,
                division_id,
                week_start_date=form_state['week_start_date'] or None,
                day_start=form_state['day_start'],
                day_end=form_state['day_end'],
                lecture_minutes=form_state['lecture_minutes'],
                break_start=form_state['break_start'] or None,
                break_duration=form_state['break_duration'] or 0,
                working_days=form_state['working_days'],
                preview_only=False,
            )
            duration = (datetime.now() - start_ts).total_seconds()
            current_app.logger.info('Timetable generation finished in %.2fs; status=%s', duration, result.get('status') if isinstance(result, dict) else type(result))
            generation_result = result
        except Exception as e:
            current_app.logger.exception('Exception during timetable generation: %s', str(e))
            generation_result = {'status': 'error', 'message': 'Internal error during generation. See server logs.'}
        # Normalize keys expected by the template to avoid UndefinedError on error/warning cases
        if isinstance(generation_result, dict):
            generation_result.setdefault('assigned', [])
            generation_result.setdefault('unassigned', [])
            generation_result.setdefault('proxy_suggestions', [])
            generation_result.setdefault('skipped_holidays', [])
        status = result.get('status', 'error')
        message = result.get('message', 'Unable to generate timetable.')
        flash_category = 'success' if status == 'success' else 'warning' if status == 'warning' else 'danger'
        flash(message, flash_category)
    cursor.close()
    return render_template(
        'admin/generate.html',
        courses=courses,
        classes=classes,
        divisions=divisions,
        form_state=form_state,
        generation_result=generation_result,
        selected_course=selected_course,
        selected_class=selected_class,
        selected_division=selected_division,
    )

# --- View & Manage Timetable ---
@timetable_bp.route('/', methods=['GET', 'POST'])
@has_permission('timetable_change')
def timetable_manage():
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    # Lookup lists
    cursor.execute("SELECT id, name FROM courses ORDER BY name"); courses = cursor.fetchall()
    cursor.execute("SELECT id, name FROM classes ORDER BY name"); classes = cursor.fetchall()
    cursor.execute("SELECT id, name FROM divisions ORDER BY name"); divisions = cursor.fetchall()

    # Current selection
    course_id = request.values.get('course') or ''
    class_id = request.values.get('class') or ''
    division_id = request.values.get('division') or ''

    # Initialize variables that will be used in template
    sessions = []
    subjects = []
    rooms = []
    time_pairs = []
    grid_rows = []

    # Add session via POST
    if request.method == 'POST' and request.form.get('action') == 'add':
        try:
            day = request.form.get('day_of_week')
            start_time = request.form.get('start_time')
            end_time = request.form.get('end_time')
            subject_id = int(request.form.get('subject_id'))
            faculty_id_input = request.form.get('faculty_id')
            faculty_id = int(faculty_id_input) if faculty_id_input and faculty_id_input.strip() else None
            if not (course_id and class_id and division_id and day and start_time and end_time and subject_id):
                raise ValueError('Missing required fields')
            
            # Auto-assign faculty if not specified
            if not faculty_id:
                cursor.execute(
                    """
                    SELECT fa.faculty_id FROM faculty_allocations fa
                    WHERE fa.class_id = %s AND fa.division_id = %s 
                      AND fa.subject_id = %s
                    LIMIT 1
                    """,
                    (class_id, division_id, subject_id)
                )
                faculty_row = cursor.fetchone()
                if faculty_row:
                    faculty_id = faculty_row['faculty_id']
                else:
                    raise ValueError('No faculty allocated for this subject. Please assign faculty first or select one manually.')
            # Weekly holiday check against course program
            cursor.execute("SELECT program FROM courses WHERE id = %s", (course_id,))
            row_prog = cursor.fetchone()
            program = row_prog['program'] if row_prog else 'UG'
            cursor.execute(
                """
                SELECT 1 FROM institution_holidays
                WHERE is_recurring = 1 AND day_of_week = %s AND (applies_to_program = %s OR applies_to_program = 'Both')
                LIMIT 1
                """,
                (day, program),
            )
            if cursor.fetchone():
                raise ValueError('Cannot add a session on a weekly holiday for this program.')
            # Overlap checks: class/division-level
            cursor.execute(
                """
                SELECT 1 FROM timetable
                WHERE course_id = %s AND class_id = %s AND division_id = %s AND day_of_week = %s
                  AND NOT (end_time <= %s OR start_time >= %s)
                LIMIT 1
                """,
                (course_id, class_id, division_id, day, start_time, end_time),
            )
            if cursor.fetchone():
                raise ValueError('Overlaps with an existing session for this class/division.')
            # Faculty-level overlap
            if faculty_id:
                cursor.execute(
                    """
                    SELECT 1 FROM timetable
                    WHERE faculty_id = %s AND day_of_week = %s
                      AND NOT (end_time <= %s OR start_time >= %s)
                    LIMIT 1
                    """,
                    (faculty_id, day, start_time, end_time),
                )
                if cursor.fetchone():
                    raise ValueError('Selected faculty is busy at that time.')
                # Faculty availability checks (enforce only if availability rows exist for this day)
                cursor.execute(
                    "SELECT COUNT(*) AS cnt FROM faculty_availability WHERE faculty_id = %s AND day_of_week = %s",
                    (faculty_id, day),
                )
                cnt = cursor.fetchone()['cnt']
                if cnt and int(cnt) > 0:
                    # Any explicit unavailability overlapping the slot blocks the add
                    cursor.execute(
                        """
                        SELECT 1 FROM faculty_availability
                        WHERE faculty_id = %s AND day_of_week = %s AND is_available = 0
                          AND NOT (end_time <= %s OR start_time >= %s)
                        LIMIT 1
                        """,
                        (faculty_id, day, start_time, end_time),
                    )
                    if cursor.fetchone():
                        raise ValueError('Faculty is marked unavailable during the selected time.')
                    # Require an available window that fully covers the slot
                    cursor.execute(
                        """
                        SELECT 1 FROM faculty_availability
                        WHERE faculty_id = %s AND day_of_week = %s AND is_available = 1
                          AND start_time <= %s AND end_time >= %s
                        LIMIT 1
                        """,
                        (faculty_id, day, start_time, end_time),
                    )
                    if not cursor.fetchone():
                        raise ValueError("Selected time is outside the faculty's available hours for this day.")
            cursor.execute(
                """
                INSERT INTO timetable (course_id, class_id, division_id, subject_id, faculty_id, day_of_week, start_time, end_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (course_id, class_id, division_id, subject_id, faculty_id, day, start_time, end_time),
            )
            connection.commit()
            flash('Session added to timetable.', 'success')
        except Exception as e:
            connection.rollback()
            current_app.logger.error(f"Add timetable session error: {str(e)}")
            flash(str(e) if isinstance(e, ValueError) else 'Failed to add session. Please check inputs.', 'danger')

    # Delete session via POST
    if request.method == 'POST' and request.form.get('action') == 'delete':
        try:
            tid = int(request.form.get('timetable_id'))
            cursor.execute("DELETE FROM timetable WHERE id = %s", [tid])
            connection.commit()
            flash('Session removed.', 'success')
        except Exception as e:
            connection.rollback()
            current_app.logger.error(f"Delete timetable session error: {str(e)}")
            flash('Failed to delete session.', 'danger')

    # Assign room to session via POST
    if request.method == 'POST' and request.form.get('action') == 'assign_room':
        try:
            timetable_id = int(request.form.get('timetable_id'))
            room_id = int(request.form.get('room_id'))
            
            # Get session details
            cursor.execute("""
                SELECT t.day_of_week, t.start_time, t.end_time, s.theory_practical,
                       (SELECT COUNT(*) FROM students WHERE course_id = t.course_id AND class_id = t.class_id AND division_id = t.division_id) as student_count
                FROM timetable t
                JOIN subjects s ON t.subject_id = s.id
                WHERE t.id = %s
            """, (timetable_id,))
            session = cursor.fetchone()
            if not session:
                raise ValueError('Session not found')
            day, start_time, end_time, subject_type, student_count = session

            # Get room details
            cursor.execute("SELECT room_type, capacity FROM rooms WHERE id = %s", (room_id,))
            room = cursor.fetchone()
            if not room:
                raise ValueError('Room not found')
            room_type, capacity = room

            # Check capacity
            if student_count and capacity and student_count > capacity:
                current_app.logger.warning('Room capacity (%d) less than student count (%d)', capacity, student_count)
                flash('Warning: Room capacity is less than class size', 'warning')

            # Check type compatibility
            subject_needs_lab = subject_type and subject_type.lower().startswith('practical')
            room_is_lab = room_type and ('lab' in room_type.lower() or 'laboratory' in room_type.lower())
            if subject_needs_lab and not room_is_lab:
                current_app.logger.warning('Practical session assigned to non-lab room')
                flash('Warning: Practical session assigned to non-lab room', 'warning')

            # Check for conflicts
            cursor.execute("""
                SELECT t.id, c.name, d.name, s.name, t.start_time, t.end_time
                FROM timetable t
                JOIN classes c ON t.class_id = c.id
                JOIN divisions d ON t.division_id = d.id
                JOIN subjects s ON t.subject_id = s.id
                WHERE t.room_id = %s 
                  AND t.day_of_week = %s
                  AND t.id != %s
                  AND NOT (t.end_time <= %s OR t.start_time >= %s)
            """, (room_id, day, timetable_id, start_time, end_time))
            conflicts = cursor.fetchall()
            if conflicts:
                conflict_details = []
                for c in conflicts:
                    conflict_details.append(
                        f"{c[1]} {c[2]} - {c[3]} ({format_time(c[4])} - {format_time(c[5])})"
                    )
                raise ValueError(f"Room has conflicts:\n" + "\n".join(conflict_details))

            # Assign room
            cursor.execute("UPDATE timetable SET room_id = %s WHERE id = %s", (room_id, timetable_id))
            connection.commit()
            flash('Room assigned successfully.', 'success')
            
        except ValueError as ve:
            connection.rollback()
            flash(str(ve), 'danger')
        except Exception as e:
            connection.rollback()
            current_app.logger.error(f"Error assigning room: {str(e)}")
            flash('Failed to assign room', 'danger')

    # Load timetable entries for selection
    sessions = []
    subjects = []
    # Grid prep structures
    time_pairs = []
    grid_rows = []
    if course_id and class_id and division_id:
        # Try to include room information if timetable has room_id
        try:
            cursor.execute(
                """
                SELECT t.id, t.day_of_week, t.start_time, t.end_time,
                       s.id AS subject_id, s.name AS subject_name,
                       t.faculty_id AS faculty_user_id, COALESCE(f.name,'') AS faculty_name,
                       r.room_number
                FROM timetable t
                JOIN subjects s ON s.id = t.subject_id
                LEFT JOIN faculty f ON f.user_id = t.faculty_id
                LEFT JOIN rooms r ON t.room_id = r.id
                WHERE t.course_id = %s AND t.class_id = %s AND t.division_id = %s
                ORDER BY FIELD(t.day_of_week,'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'), t.start_time
                """,
                (course_id, class_id, division_id),
            )
            fetched = cursor.fetchall()
            has_room = True
        except Exception:
            cursor.execute(
                """
                SELECT t.id, t.day_of_week, t.start_time, t.end_time,
                       s.id AS subject_id, s.name AS subject_name,
                       t.faculty_id AS faculty_user_id, COALESCE(f.name,'') AS faculty_name
                FROM timetable t
                JOIN subjects s ON s.id = t.subject_id
                LEFT JOIN faculty f ON f.user_id = t.faculty_id
                WHERE t.course_id = %s AND t.class_id = %s AND t.division_id = %s
                ORDER BY FIELD(t.day_of_week,'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'), t.start_time
                """,
                (course_id, class_id, division_id),
            )
            fetched = cursor.fetchall()
            has_room = False
        sessions = []
        unique_pairs = set()
        for r in fetched:
            start_str = format_time(r[2]); end_str = format_time(r[3])
            room_num = (r[8] if has_room else None)
            sessions.append({
                'id': r[0], 'day': r[1], 'start_time': start_str, 'end_time': end_str,
                'subject_id': r[4], 'subject': r[5], 'faculty_id': r[6] or '', 'faculty': r[7] or '',
                'room': room_num or ''
            })
            unique_pairs.add((start_str, end_str))
        # Sort time pairs by start then end
        def _to_minutes(tstr):
            hh, mm = tstr.split(':'); return int(hh)*60 + int(mm)
        time_pairs = sorted(list(unique_pairs), key=lambda p: (_to_minutes(p[0]), _to_minutes(p[1])))
        # Build grid rows for Mon-Sat
        days = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday']
        for day in days:
            cells = []
            for (st, et) in time_pairs:
                match = next((s for s in sessions if s['day'] == day and s['start_time'] == st and s['end_time'] == et), None)
                if match:
                    label = match['subject'] + (f" ({match['faculty']})" if match['faculty'] else '')
                    if match.get('room'):
                        label += f" — Room {match['room']}"
                else:
                    label = ''
                cells.append(label)
            grid_rows.append({'day': day, 'cells': cells})

        # Get rooms for assignment modal
        cursor.execute("SELECT id, room_number, room_type, capacity FROM rooms ORDER BY room_type, room_number")
        rooms = [{'id': r[0], 'room_number': r[1], 'room_type': r[2], 'capacity': r[3]} for r in cursor.fetchall()]

        # Subject options for add form
        cursor.execute(
            """
            SELECT id, name FROM subjects
            WHERE course_id = %s AND (class_id IS NULL OR class_id = %s)
            ORDER BY name
            """,
            (course_id, class_id),
        )
        subjects = [{'id': r[0], 'name': r[1]} for r in cursor.fetchall()]

    cursor.close()
    return render_template(
        'admin/timetable_manage.html',
        courses=courses,
        classes=classes,
        divisions=divisions,
        selected_course=course_id,
        selected_class=class_id,
        selected_division=division_id,
        sessions=sessions,
        subjects=subjects,
        rooms=rooms,
        time_columns=[f"{st} - {et}" for (st, et) in time_pairs],
        grid_rows=grid_rows,
    )
