"""Admin timetable generate and manage. The connection stays open."""

from datetime import date, datetime

from flask import current_app, flash

from academic_rules.availability import manual_add_availability_block
from academic_rules.holidays import recurring_holiday_blocks_day
from data_access.lecture_sessions import count_slot_sessions
from data_access.admin_timetable import (
    assign_timetable_room,
    deactivate_timetable_session,
    delete_timetable_session,
    fetch_allocated_faculty,
    fetch_class_overlap,
    fetch_classes,
    fetch_course_program,
    fetch_courses,
    fetch_divisions,
    fetch_faculty_overlap,
    fetch_room_conflicts,
    fetch_room_type,
    fetch_rooms,
    fetch_session_for_room,
    fetch_subject_choices,
    fetch_timetable_with_rooms,
    fetch_timetable_without_rooms,
    insert_timetable_session,
)
from extensions import get_db_connection
from services.timetable.generator import WEEKDAY_ORDER, generate_timetable_for_class
from utils.dates import format_hhmm


def _cursor():
    connection = get_db_connection()
    return connection, connection.cursor(dictionary=True)


def prepare_generate_page(method, form, user_id):
    """Load the generate page and run a saved generation on POST. The connection stays open."""
    connection, cursor = _cursor()
    current_app.logger.debug('Entered generate_timetable endpoint; method=%s', method)
    courses = fetch_courses(cursor)
    classes = fetch_classes(cursor)
    divisions = fetch_divisions(cursor)
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

    if method == 'POST':
        try:
            current_app.logger.info('generate_timetable POST received; form keys: %s', list(form.keys()))
        except Exception:
            current_app.logger.exception('Failed to log generate_timetable form keys')
        course_id = form.get('course')
        class_id = form.get('class')
        division_id = form.get('division')
        selected_course = course_id
        selected_class = class_id
        selected_division = division_id

        default_lecture_minutes = default_config['lecture_minutes']
        if course_id:
            course_row = fetch_course_program(cursor, course_id)
            if course_row:
                program = course_row['program'] if course_row['program'] else 'UG'
                default_lecture_minutes = 60 if program == 'PG' else 45

        form_state['week_start_date'] = form.get('week_start_date') or ''
        form_state['day_start'] = form.get('day_start') or default_config['day_start']
        form_state['day_end'] = form.get('day_end') or default_config['day_end']
        form_state['lecture_minutes'] = int(form.get('lecture_minutes') or default_lecture_minutes)
        form_state['break_start'] = form.get('break_start') or ''
        form_state['break_duration'] = int(form.get('break_duration') or 0)
        form_state['working_days'] = form.getlist('working_days') or default_config['working_days']

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
                candidate_count=7,
                created_by=user_id,
            )
            duration = (datetime.now() - start_ts).total_seconds()
            current_app.logger.info('Timetable generation finished in %.2fs; status=%s', duration, result.get('status') if isinstance(result, dict) else type(result))
            generation_result = result
        except Exception as exc:
            current_app.logger.exception('Exception during timetable generation: %s', str(exc))
            generation_result = {'status': 'error', 'message': 'Internal error during generation. See server logs.'}
        if isinstance(generation_result, dict):
            generation_result.setdefault('assigned', [])
            generation_result.setdefault('unassigned', [])
            generation_result.setdefault('proxy_suggestions', [])
            generation_result.setdefault('skipped_holidays', [])
        status = generation_result.get('status', 'error') if isinstance(generation_result, dict) else 'error'
        message = generation_result.get('message', 'Unable to generate timetable.') if isinstance(generation_result, dict) else 'Unable to generate timetable.'
        flash_category = 'success' if status == 'success' else 'warning' if status == 'warning' else 'danger'
        flash(message, flash_category)
    cursor.close()
    return {
        'courses': courses,
        'classes': classes,
        'divisions': divisions,
        'form_state': form_state,
        'generation_result': generation_result,
        'selected_course': selected_course,
        'selected_class': selected_class,
        'selected_division': selected_division,
    }


def _to_minutes(tstr):
    hh, mm = tstr.split(':')
    return int(hh) * 60 + int(mm)


def manage_timetable(method, form, values):
    """Apply timetable edits and return the manage page. The connection stays open."""
    connection, cursor = _cursor()
    courses = fetch_courses(cursor, ordered=True)
    classes = fetch_classes(cursor, ordered=True)
    divisions = fetch_divisions(cursor, ordered=True)

    course_id = values.get('course') or ''
    class_id = values.get('class') or ''
    division_id = values.get('division') or ''

    sessions = []
    subjects = []
    rooms = []
    time_pairs = []
    grid_rows = []

    if method == 'POST' and form.get('action') == 'add':
        try:
            day = form.get('day_of_week')
            start_time = form.get('start_time')
            end_time = form.get('end_time')
            subject_id = int(form.get('subject_id'))
            faculty_id_input = form.get('faculty_id')
            faculty_id = int(faculty_id_input) if faculty_id_input and faculty_id_input.strip() else None
            if not (course_id and class_id and division_id and day and start_time and end_time and subject_id):
                raise ValueError('Missing required fields')

            if not faculty_id:
                faculty_row = fetch_allocated_faculty(cursor, class_id, division_id, subject_id)
                if faculty_row:
                    faculty_id = faculty_row['faculty_id']
                else:
                    raise ValueError('No faculty allocated for this subject. Please assign faculty first or select one manually.')
            row_prog = fetch_course_program(cursor, course_id)
            program = row_prog['program'] if row_prog else 'UG'
            if recurring_holiday_blocks_day(cursor, program, day):
                raise ValueError('Cannot add a session on a weekly holiday for this program.')
            if fetch_class_overlap(cursor, course_id, class_id, division_id, day, start_time, end_time):
                raise ValueError('Overlaps with an existing session for this class/division.')
            if faculty_id:
                if fetch_faculty_overlap(cursor, faculty_id, day, start_time, end_time):
                    raise ValueError('Selected faculty is busy at that time.')
                message = manual_add_availability_block(cursor, faculty_id, day, start_time, end_time)
                if message:
                    raise ValueError(message)
            insert_timetable_session(cursor, (
                course_id, class_id, division_id, subject_id, faculty_id, day, start_time, end_time,
            ))
            connection.commit()
            flash('Session added to timetable.', 'success')
        except Exception as exc:
            connection.rollback()
            current_app.logger.error(f"Add timetable session error: {str(exc)}")
            flash(str(exc) if isinstance(exc, ValueError) else 'Failed to add session. Please check inputs.', 'danger')

    if method == 'POST' and form.get('action') == 'delete':
        try:
            tid = int(form.get('timetable_id'))
            try:
                deactivate_timetable_session(cursor, tid)
                if cursor.rowcount == 0:
                    flash('Session not found or already removed.', 'warning')
                else:
                    flash('Session removed.', 'success')
            except Exception:
                # A slot with recorded lectures is retired, never deleted: deleting would erase its attendance history.
                if count_slot_sessions(cursor, tid):
                    cursor.execute('UPDATE timetable SET is_active = 0 WHERE id = %s', (tid,))
                    flash('Session retired. It has recorded lectures, so it was kept for attendance history.', 'warning')
                else:
                    delete_timetable_session(cursor, tid)
                    flash('Session removed.', 'success')
            connection.commit()
        except Exception as exc:
            connection.rollback()
            current_app.logger.error(f"Delete timetable session error: {str(exc)}")
            if '1451' in str(exc):
                flash('Cannot delete this session because attendance records already exist for it.', 'danger')
            else:
                flash('Failed to delete session.', 'danger')

    if method == 'POST' and form.get('action') == 'assign_room':
        try:
            timetable_id = int(form.get('timetable_id'))
            room_id = int(form.get('room_id'))

            session = fetch_session_for_room(cursor, timetable_id)
            if not session:
                raise ValueError('Session not found')
            day, start_time, end_time, subject_type, student_count = session

            room = fetch_room_type(cursor, room_id)
            if not room:
                raise ValueError('Room not found')
            room_type, capacity = room

            if student_count and capacity and student_count > capacity:
                current_app.logger.warning('Room capacity (%d) less than student count (%d)', capacity, student_count)
                flash('Warning: Room capacity is less than class size', 'warning')

            subject_needs_lab = subject_type and subject_type.lower().startswith('practical')
            room_is_lab = room_type and ('lab' in room_type.lower() or 'laboratory' in room_type.lower())
            if subject_needs_lab and not room_is_lab:
                current_app.logger.warning('Practical session assigned to non-lab room')
                flash('Warning: Practical session assigned to non-lab room', 'warning')

            conflicts = fetch_room_conflicts(cursor, room_id, day, timetable_id, start_time, end_time)
            if conflicts:
                conflict_details = []
                for item in conflicts:
                    conflict_details.append(
                        f"{item['class_name']} {item['division_name']} - {item['subject_name']} ({format_hhmm(item['start_time'])} - {format_hhmm(item['end_time'])})"
                    )
                raise ValueError(f"Room has conflicts:\n" + "\n".join(conflict_details))

            assign_timetable_room(cursor, room_id, timetable_id)
            connection.commit()
            flash('Room assigned successfully.', 'success')

        except ValueError as exc:
            connection.rollback()
            flash(str(exc), 'danger')
        except Exception as exc:
            connection.rollback()
            current_app.logger.error(f"Error assigning room: {str(exc)}")
            flash('Failed to assign room', 'danger')

    sessions = []
    subjects = []
    time_pairs = []
    grid_rows = []
    if course_id and class_id and division_id:
        try:
            fetched = fetch_timetable_with_rooms(cursor, course_id, class_id, division_id)
            has_room = True
        except Exception:
            fetched = fetch_timetable_without_rooms(cursor, course_id, class_id, division_id)
            has_room = False
        sessions = []
        unique_pairs = set()
        for row in fetched:
            start_str = format_hhmm(row['start_time'])
            end_str = format_hhmm(row['end_time'])
            room_num = (row['room_number'] if has_room else None)
            sessions.append({
                'id': row['id'], 'day': row['day_of_week'], 'start_time': start_str, 'end_time': end_str,
                'subject_id': row['subject_id'], 'subject': row['subject_name'], 'faculty_id': row['faculty_user_id'] or '', 'faculty': row['faculty_name'] or '',
                'room': room_num or ''
            })
            unique_pairs.add((start_str, end_str))
        time_pairs = sorted(list(unique_pairs), key=lambda pair: (_to_minutes(pair[0]), _to_minutes(pair[1])))
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        for day_name in days:
            cells = []
            for (st, et) in time_pairs:
                match = next((item for item in sessions if item['day'] == day_name and item['start_time'] == st and item['end_time'] == et), None)
                if match:
                    label = match['subject'] + (f" ({match['faculty']})" if match['faculty'] else '')
                    if match.get('room'):
                        label += f" — Room {match['room']}"
                else:
                    label = ''
                cells.append(label)
            grid_rows.append({'day': day_name, 'cells': cells})

        rooms = [{'id': row['id'], 'room_number': row['room_number'], 'room_type': row['room_type'], 'capacity': row['capacity']} for row in fetch_rooms(cursor)]
        subjects = [{'id': row['id'], 'name': row['name']} for row in fetch_subject_choices(cursor, course_id, class_id)]

    cursor.close()
    return {
        'courses': courses,
        'classes': classes,
        'divisions': divisions,
        'selected_course': course_id,
        'selected_class': class_id,
        'selected_division': division_id,
        'sessions': sessions,
        'subjects': subjects,
        'rooms': rooms,
        'time_columns': [f"{st} - {et}" for (st, et) in time_pairs],
        'grid_rows': grid_rows,
    }
