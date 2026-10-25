from flask import Blueprint, current_app
from collections import defaultdict
from datetime import time, timedelta,datetime, date
from uuid import uuid4
import math
import os
import random
import secrets

from database import get_db_connection
from services.timetable_quality_service import score_timetable_candidate

timetable_algorithm_bp = Blueprint('timetable_algorithm', __name__, url_prefix='/admin')

# --- Timetable Logic ---

WEEKDAY_ORDER = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def _parse_time(value: str, field: str) -> time:
    if isinstance(value, time):
        return value
    if hasattr(value, 'hour') and hasattr(value, 'minute'):
        return time(value.hour, value.minute)
    try:
        return datetime.strptime(value, '%H:%M').time()
    except (TypeError, ValueError):
        raise ValueError(f"Invalid {field}. Please use HH:MM format.")


def _time_to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _times_overlap(a_start: time, a_end: time, b_start: time, b_end: time) -> bool:
    return _time_to_minutes(a_start) < _time_to_minutes(b_end) and _time_to_minutes(a_end) > _time_to_minutes(b_start)


def build_time_slots(day_start: time, day_end: time, lecture_minutes: int, break_window=None):
    """Generate contiguous slots for the academic day while respecting a single break window."""
    if lecture_minutes <= 0:
        raise ValueError('Lecture duration must be greater than zero.')

    slots = []
    base_date = date.today()
    current = datetime.combine(base_date, day_start)
    end_dt = datetime.combine(base_date, day_end)

    break_start_dt = break_end_dt = None
    if break_window and break_window.get('start') and break_window.get('duration', 0) > 0:
        break_start_dt = datetime.combine(base_date, break_window['start'])
        break_end_dt = break_start_dt + timedelta(minutes=break_window['duration'])

    while current < end_dt:
        slot_end = current + timedelta(minutes=lecture_minutes)
        
        # Check if this slot would end after day end
        if slot_end > end_dt:
            break
        
        # Check if current time is during break - skip to end of break
        if break_start_dt and break_start_dt <= current < break_end_dt:
            current = break_end_dt
            continue
        
        # Check if this slot would overlap with break
        if break_start_dt and current < break_start_dt < slot_end:
            # Skip to after break and continue
            current = break_end_dt
            continue

        # Add normal slot
        slots.append((current.time(), slot_end.time()))
        current = slot_end

    return slots


def generate_timetable_for_class(
    course_id,
    class_id,
    division_id,
    *,
    week_start_date: str | None = None,
    day_start: str = '09:00',
    day_end: str = '15:00',
    lecture_minutes: int = 45,
    break_start: str | None = None,
    break_duration: int = 0,
    working_days: list[str] | None = None,
    preview_only: bool = False,
    candidate_count: int = 7,
    created_by: int | None = None,
):
    """Generate a weekly timetable for the given class/division respecting availability, holidays, and proxies."""

    working_days = working_days or WEEKDAY_ORDER[:6]
    working_days_set = {day for day in working_days if day in WEEKDAY_ORDER}
    if not working_days_set:
        return {'status': 'error', 'message': 'Please select at least one working day.'}

    try:
        start_time = _parse_time(day_start, 'start time')
        end_time = _parse_time(day_end, 'end time')
        if start_time >= end_time:
            return {'status': 'error', 'message': 'Day start time must be before end time.'}
        break_window = None
        if break_start and break_duration:
            break_window = {'start': _parse_time(break_start, 'break start time'), 'duration': int(break_duration)}
    except ValueError as exc:
        return {'status': 'error', 'message': str(exc)}

    try:
        lecture_minutes = int(lecture_minutes)
    except (TypeError, ValueError):
        return {'status': 'error', 'message': 'Lecture duration must be a number.'}

    try:
        course_id = int(course_id)
        class_id = int(class_id)
        division_id = int(division_id)
    except (TypeError, ValueError):
        return {'status': 'error', 'message': 'Invalid course, class, or division selection.'}

    # Determine the start date of the scheduling window (defaults to upcoming Monday)
    if week_start_date:
        if isinstance(week_start_date, date):
            week_start = week_start_date
        else:
            try:
                week_start = datetime.strptime(week_start_date, '%Y-%m-%d').date()
            except ValueError:
                return {'status': 'error', 'message': 'Week start date must be in YYYY-MM-DD format.'}
    else:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())

    week_end = week_start + timedelta(days=6)

    slots = build_time_slots(start_time, end_time, lecture_minutes, break_window)
    if not slots:
        return {'status': 'error', 'message': 'Unable to derive lecture slots with the provided timings.'}
    
    # Set max lectures per day based on actual available slots (not hardcoded)
    max_lectures_per_day = len(slots)
    min_lectures_per_day = min(3, max_lectures_per_day)

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, name, program, department_id FROM courses WHERE id = %s", (course_id,))
        course_row = cursor.fetchone()
        if not course_row:
            return {'status': 'error', 'message': 'Course not found.'}
        program = course_row['program'] or 'UG'
        course_department_id = course_row.get('department_id')

        # Resolve academic days (exclude holidays)
        cursor.execute(
            """
            SELECT day_of_week, holiday_date, name, is_recurring
            FROM institution_holidays
            WHERE (is_recurring = 1 AND day_of_week IS NOT NULL AND (applies_to_program = %s OR applies_to_program = 'Both'))
               OR (holiday_date BETWEEN %s AND %s AND (applies_to_program = %s OR applies_to_program = 'Both'))
            """,
            (program, week_start, week_end, program),
        )
        holiday_rows = cursor.fetchall()
        weekly_holidays = {row['day_of_week'] for row in holiday_rows if row['day_of_week'] and row['is_recurring']}
        date_holidays = {row['holiday_date']: row['name'] for row in holiday_rows if row['holiday_date']}

        days_with_dates: list[tuple[str, date]] = []
        skipped_holidays: list[dict[str, str]] = []
        for offset in range(7):
            current_date = week_start + timedelta(days=offset)
            day_name = current_date.strftime('%A')
            if day_name not in working_days_set:
                continue
            if day_name in weekly_holidays:
                skipped_holidays.append({'day': day_name, 'date': current_date.isoformat(), 'name': 'Weekly Holiday'})
                continue
            if current_date in date_holidays:
                skipped_holidays.append({'day': day_name, 'date': current_date.isoformat(), 'name': date_holidays[current_date]})
                continue
            days_with_dates.append((day_name, current_date))

        if not days_with_dates:
            return {'status': 'error', 'message': 'All selected days fall on holidays for the chosen week.'}

        # Gather subject requirements
        cursor.execute(
            """
            SELECT DISTINCT
                s.id,
                s.name,
                s.theory_practical,
                COALESCE(s.lectures_per_week, 0) AS lectures_per_week,
                COALESCE(s.practical_hours_per_week, 0) AS practical_hours_per_week
            FROM subjects s
            JOIN faculty_allocations fa ON fa.subject_id = s.id
            WHERE s.course_id = %s
              AND (fa.class_id IS NULL OR fa.class_id = %s)
              AND (fa.division_id IS NULL OR fa.division_id = %s)
            ORDER BY s.name
            """,
            (course_id, class_id, division_id),
        )
        subject_rows = cursor.fetchall()
        current_app.logger.info('Fetched %d subject_rows for generation', len(subject_rows or []))
        if not subject_rows:
            return {'status': 'error', 'message': 'No subjects are allocated to the selected class/division.'}

        subject_ids = [row['id'] for row in subject_rows]
        placeholder = ','.join(['%s'] * len(subject_ids))

        cursor.execute(
            f"""
            SELECT fa.subject_id, fa.faculty_id, COALESCE(fa.is_primary, 1) AS is_primary,
                   f.name AS faculty_name, f.department_id
            FROM faculty_allocations fa
            JOIN faculty f ON f.user_id = fa.faculty_id
            WHERE fa.subject_id IN ({placeholder})
              AND (fa.class_id IS NULL OR fa.class_id = %s)
              AND (fa.division_id IS NULL OR fa.division_id = %s)
            ORDER BY fa.subject_id, is_primary DESC, f.name
            """,
            (*subject_ids, class_id, division_id),
        )
        allocation_rows = cursor.fetchall()
        current_app.logger.info('Fetched %d allocation_rows for %d subjects', len(allocation_rows or []), len(subject_ids))

        subject_faculty_map: dict[int, list[dict[str, int | str]]] = defaultdict(list)
        for row in allocation_rows:
            subject_faculty_map[row['subject_id']].append(
                {
                    'faculty_id': row['faculty_id'],
                    'name': row['faculty_name'],
                    'is_primary': bool(row['is_primary']),
                }
            )

        if not all(subject_faculty_map.get(sub_id) for sub_id in subject_ids):
            missing = [row['name'] for row in subject_rows if not subject_faculty_map.get(row['id'])]
            return {
                'status': 'error',
                'message': (
                    f"Faculty allocations missing for: {', '.join(missing)}. "
                    "Please assign faculty before generating the timetable. "
                    "Tip: ensure the allocation matches the selected Class and Division."
                ),
            }

        # Additional pool of faculty who can teach the subject (for proxy suggestions)
        cursor.execute(
            f"""
            SELECT fa.subject_id, fa.faculty_id, COALESCE(fa.is_primary, 1) AS is_primary,
                   f.name AS faculty_name
            FROM faculty_allocations fa
            JOIN faculty f ON f.user_id = fa.faculty_id
            WHERE fa.subject_id IN ({placeholder})
            ORDER BY fa.subject_id, is_primary DESC, f.name
            """,
            tuple(subject_ids),
        )
        proxy_pool_rows = cursor.fetchall()
        current_app.logger.info('Fetched %d proxy_pool_rows', len(proxy_pool_rows or []))
        proxy_faculty_map: dict[int, list[dict[str, int | str]]] = defaultdict(list)
        for row in proxy_pool_rows:
            proxy_faculty_map[row['subject_id']].append(
                {
                    'faculty_id': row['faculty_id'],
                    'name': row['faculty_name'],
                    'is_primary': bool(row['is_primary']),
                }
            )

        # Build session requirements per subject
        sessions: list[dict[str, object]] = []
        for subject in subject_rows:
            subject_faculties = subject_faculty_map[subject['id']]
            theory_sessions = int(subject['lectures_per_week'] or 0)
            for _ in range(theory_sessions):
                sessions.append(
                    {
                        'subject_id': subject['id'],
                        'subject_name': subject['name'],
                        'type': 'Theory',
                        'block_slots': 1,
                        'faculty_candidates': subject_faculties,
                    }
                )

            practical_hours = float(subject['practical_hours_per_week'] or 0)
            if practical_hours > 0:
                # For PG (60 min) and UG (45 min): Each practical hour = 1 session
                # Create individual 1-hour practical sessions instead of grouping into blocks
                # This allows flexible scheduling while respecting the 2-hour consecutive limit
                num_practical_sessions = int(practical_hours)  # 4 hours = 4 sessions
                for _ in range(num_practical_sessions):
                    sessions.append(
                        {
                            'subject_id': subject['id'],
                            'subject_name': subject['name'],
                            'type': 'Practical',
                            'block_slots': 1,  # Each practical is 1 session (1 hour for PG, 45 min for UG)
                            'faculty_candidates': subject_faculties,
                        }
                    )

        if not sessions:
            return {'status': 'error', 'message': 'No lecture or practical requirements configured for this class.'}
        current_app.logger.info('Built %d session requirements (theory/practical blocks) to schedule', len(sessions))

        # Helper to coerce MySQL TIME values (which may arrive as timedelta) to time
        def _coerce_time_value(v):
            if isinstance(v, timedelta):
                total_seconds = int(v.total_seconds())
                hours, remainder = divmod(total_seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                try:
                    return time(hour=hours % 24, minute=minutes)
                except Exception:
                    # Fallback: 00:00 on failure
                    return time(0, 0)
            # If it's a datetime.time already
            if isinstance(v, time):
                return v
            # If it's a datetime/datetime-like
            if hasattr(v, 'strftime') and hasattr(v, 'hour'):
                try:
                    return time(hour=v.hour, minute=v.minute, second=getattr(v, 'second', 0))
                except Exception:
                    return time(0, 0)
            # If it's a string like 'HH:MM[:SS]'
            if isinstance(v, str):
                for fmt in ('%H:%M:%S', '%H:%M'):
                    try:
                        return datetime.strptime(v, fmt).time()
                    except Exception:
                        continue
            return v

        has_is_active_column = False
        try:
            active_col_cursor = connection.cursor()
            active_col_cursor.execute("SHOW COLUMNS FROM timetable LIKE 'is_active'")
            has_is_active_column = active_col_cursor.fetchone() is not None
            active_col_cursor.close()
        except Exception:
            has_is_active_column = False

        # Faculty workload and availability
        faculty_busy_query = """
            SELECT faculty_id, day_of_week, start_time, end_time
            FROM timetable
            WHERE faculty_id IS NOT NULL
              AND NOT (course_id = %s AND class_id = %s AND division_id = %s)
        """
        if has_is_active_column:
            faculty_busy_query += "\n              AND COALESCE(is_active, 1) = 1"
        cursor.execute(faculty_busy_query, (course_id, class_id, division_id))
        faculty_busy: dict[int, dict[str, list[tuple[time, time]]]] = defaultdict(lambda: defaultdict(list))
        for row in cursor.fetchall():
            busy_start = _coerce_time_value(row['start_time'])
            busy_end = _coerce_time_value(row['end_time'])
            faculty_busy[row['faculty_id']][row['day_of_week']].append((busy_start, busy_end))

        # Fetch faculty availability with shift patterns
        cursor.execute(
            """
            SELECT fa.faculty_id, fa.day_of_week, fa.is_available,
                   sp.start_time, sp.end_time, sp.shift_name
            FROM faculty_availability fa
            LEFT JOIN shift_patterns sp ON fa.shift_pattern_id = sp.id
            WHERE sp.is_active = 1 OR fa.shift_pattern_id IS NULL
        """
        )
        availability_map: dict[int, dict[str, list[dict[str, object]]]] = defaultdict(lambda: defaultdict(list))
        
        # Convert day_of_week integer (1-7) to day name
        day_number_to_name = {1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday', 5: 'Friday', 6: 'Saturday', 7: 'Sunday'}
        
        for row in cursor.fetchall():
            day_name = day_number_to_name.get(row['day_of_week'])
            if not day_name:
                continue
                
            # Only add availability window if shift pattern is assigned
            if row['start_time'] and row['end_time']:
                availability_map[row['faculty_id']][day_name].append(
                    {
                        'start': _coerce_time_value(row['start_time']),
                        'end': _coerce_time_value(row['end_time']),
                        'is_available': bool(row['is_available']),
                        'shift_name': row['shift_name'],
                    }
                )
            elif not row['is_available']:
                # Faculty marked as not available without shift assignment - block entire day
                availability_map[row['faculty_id']][day_name].append(
                    {
                        'start': time(0, 0),
                        'end': time(23, 59),
                        'is_available': False,
                        'shift_name': 'Not Available',
                    }
                )

        cursor.execute(
            """
            SELECT faculty_id, absence_date
            FROM faculty_absences
            WHERE absence_date BETWEEN %s AND %s
        """,
            (week_start, week_end),
        )
        absence_rows = cursor.fetchall()
        faculty_absences = {(row['faculty_id'], row['absence_date']) for row in absence_rows}

        # Rooms support (optional). Try to load available rooms and detect timetable.room_id column
        rooms_by_type: dict[str, list[dict[str, object]]] = defaultdict(list)
        has_room_column = False
        existing_room_usage: dict[str, dict[int, list[tuple[time, time]]]] = defaultdict(lambda: defaultdict(list))
        try:
            # Detect room_id column
            cur2 = connection.cursor()
            cur2.execute("SHOW COLUMNS FROM timetable LIKE 'room_id'")
            has_room_column = cur2.fetchone() is not None
            cur2.close()

            # Load rooms if table exists
            cur3 = connection.cursor(dictionary=True)
            try:
                # Try with capacity and department_id if available
                try:
                    cur3.execute("SELECT id, room_number, room_type, capacity, department_id FROM rooms")
                    include_dept = True
                except Exception:
                    cur3.execute("SELECT id, room_number, room_type, capacity FROM rooms")
                    include_dept = False
                for r in cur3.fetchall():
                    rt = (r.get('room_type') or '').strip() or 'Room'
                    room_entry = {
                        'id': r['id'],
                        'room_number': r.get('room_number'),
                        'room_type': rt,
                        'capacity': r.get('capacity'),
                    }
                    if include_dept:
                        room_entry['department_id'] = r.get('department_id')
                    rooms_by_type[rt].append(room_entry)
                current_app.logger.info('Loaded rooms_by_type keys: %s', list(rooms_by_type.keys()))
            finally:
                cur3.close()

            # Build existing room usage to avoid conflicts with already saved timetable
            if has_room_column:
                cur4 = connection.cursor(dictionary=True)
                room_usage_query = """
                    SELECT day_of_week, start_time, end_time, room_id
                    FROM timetable
                    WHERE room_id IS NOT NULL
                      AND NOT (course_id = %s AND class_id = %s AND division_id = %s)
                """
                if has_is_active_column:
                    room_usage_query += "\n                      AND COALESCE(is_active, 1) = 1"
                cur4.execute(room_usage_query, (course_id, class_id, division_id))
                for r in cur4.fetchall():
                    if not r['room_id']:
                        continue
                    day = r['day_of_week']
                    rs = _coerce_time_value(r['start_time'])
                    re = _coerce_time_value(r['end_time'])
                    existing_room_usage[day][int(r['room_id'])].append((rs, re))
                cur4.close()
        except Exception:
            # If any room-related metadata fails, proceed without room assignment
            rooms_by_type = defaultdict(list)
            has_room_column = False
            existing_room_usage = defaultdict(lambda: defaultdict(list))

        def faculty_is_available(
            faculty_id: int,
            day_name: str,
            slot_group: list[tuple[time, time]],
            day_date: date,
            faculty_busy_state: dict[int, dict[str, list[tuple[time, time]]]],
        ) -> tuple[bool, str | None]:
            # Check if faculty is absent on this date
            if (faculty_id, day_date) in faculty_absences:
                return False, 'absent'

            # Check for scheduling conflicts with already assigned classes
            for busy_start, busy_end in faculty_busy_state.get(faculty_id, {}).get(day_name, []):
                if any(_times_overlap(busy_start, busy_end, start, end) for start, end in slot_group):
                    return False, 'conflict'

            # Check availability/shift patterns
            availability = availability_map.get(faculty_id, {}).get(day_name)
            if availability:
                # Only block if faculty is EXPLICITLY marked as unavailable
                # Shift patterns are treated as preferences, not hard restrictions
                # This allows faculty to teach both UG (morning) and PG (afternoon) courses
                for start, end in slot_group:
                    # Check for explicit unavailability (is_available=0)
                    blocked = any(
                        not window['is_available'] and _times_overlap(window['start'], window['end'], start, end)
                        for window in availability
                    )
                    if blocked:
                        return False, 'not_available'
                    
                    # NOTE: We do NOT enforce shift time windows strictly
                    # Faculty can teach outside their primary shift if allocated to the subject
                    # This enables flexibility for faculty teaching multiple courses (UG + PG)
            # If no availability records or no explicit blocks, treat as available

            return True, None

        def build_distributed_sessions(candidate_sessions: list[dict[str, object]], seed_value: int) -> list[dict[str, object]]:
            # Round-robin by subject with seed-driven shuffle for candidate diversity.
            from collections import Counter

            randomizer = random.Random(seed_value)
            for item in candidate_sessions:
                randomizer.shuffle(item['faculty_candidates'])

            subject_session_counts = Counter(s['subject_id'] for s in candidate_sessions)
            subject_order = sorted(subject_session_counts.keys())
            randomizer.shuffle(subject_order)

            subject_buckets: dict[int, list[dict[str, object]]] = defaultdict(list)
            for item in candidate_sessions:
                subject_buckets[item['subject_id']].append(item)
            for subject_id in subject_buckets:
                randomizer.shuffle(subject_buckets[subject_id])

            distributed: list[dict[str, object]] = []
            max_sessions = max(subject_session_counts.values())
            for session_index in range(max_sessions):
                for subject_id in subject_order:
                    subject_sessions = subject_buckets[subject_id]
                    if session_index < len(subject_sessions):
                        distributed.append(subject_sessions[session_index])
            return distributed

        # Determine expected group size for capacity matching
        required_capacity = 0
        try:
            curcap = connection.cursor()
            curcap.execute(
                "SELECT COUNT(*) FROM students WHERE course_id = %s AND class_id = %s AND division_id = %s",
                (course_id, class_id, division_id),
            )
            required_capacity = int(curcap.fetchone()[0] or 0)
            curcap.close()
        except Exception:
            required_capacity = 0

        # Helper: find available room for the given slot span and type
        def find_available_room(
            required_type: str,
            day_name: str,
            slot_start: time,
            slot_end: time,
            assigned_room_usage_day: dict[int, list[tuple[time, time]]],
            persisted_room_usage: dict[str, dict[int, list[tuple[time, time]]]],
        ):
            # Flexible mapping of required_type to available room_type keys in rooms_by_type
            want_practical = (required_type or '').lower().startswith('practical')
            # Candidate buckets: prefer matching labels (lab, laboratory) for practical; (room, classroom, class) for theory
            matched_candidates = []
            for key, room_list in rooms_by_type.items():
                kl = (key or '').lower()
                if want_practical and ('lab' in kl or 'labor' in kl):
                    matched_candidates.extend(room_list)
                if not want_practical and ('room' in kl or 'class' in kl or 'lecture' in kl):
                    matched_candidates.extend(room_list)
            # If no direct matches, fall back to any available room list
            candidates = list(matched_candidates) if matched_candidates else [r for lst in rooms_by_type.values() for r in lst]
            if not candidates:
                current_app.logger.debug('No rooms available in rooms_by_type for required_type=%s', required_type)
                return None
            # Prefer candidates meeting capacity and same department (when available)
            def rank(room):
                cap = room.get('capacity') or 0
                meets_cap = 1 if (required_capacity and cap >= required_capacity) else 0
                same_dept = 1 if (course_department_id and room.get('department_id') == course_department_id) else 0
                # higher is better; break ties by smaller capacity surplus
                surplus = (cap - required_capacity) if (required_capacity and cap) else 9999
                return (same_dept, meets_cap, -surplus)
            try:
                candidates.sort(key=rank, reverse=True)
            except Exception:
                pass
            def overlaps(a_start, a_end, b_start, b_end):
                return _times_overlap(a_start, a_end, b_start, b_end)
            for room in candidates:
                times = []
                # Existing persisted usage
                for (st, et) in persisted_room_usage.get(day_name, {}).get(room['id'], []):
                    times.append((st, et))
                # Already assigned in this run
                for (st, et) in assigned_room_usage_day.get(room['id'], []):
                    times.append((st, et))
                if any(overlaps(st, et, slot_start, slot_end) for (st, et) in times):
                    continue
                return room
            return None

        def clone_faculty_busy_state(source: dict[int, dict[str, list[tuple[time, time]]]]):
            cloned: dict[int, dict[str, list[tuple[time, time]]]] = defaultdict(lambda: defaultdict(list))
            for faculty_id, day_map in source.items():
                for day_name, spans in day_map.items():
                    cloned[faculty_id][day_name] = list(spans)
            return cloned

        def clone_room_usage_state(source: dict[str, dict[int, list[tuple[time, time]]]]):
            cloned: dict[str, dict[int, list[tuple[time, time]]]] = defaultdict(lambda: defaultdict(list))
            for day_name, room_map in source.items():
                for room_id, spans in room_map.items():
                    cloned[day_name][room_id] = list(spans)
            return cloned

        base_faculty_busy = clone_faculty_busy_state(faculty_busy)
        base_existing_room_usage = clone_room_usage_state(existing_room_usage)
        slots_per_day = {day_name: len(slots) for day_name, _ in days_with_dates}

        candidate_count = max(5, min(10, int(candidate_count or 7)))
        if preview_only:
            candidate_count = min(candidate_count, 7)

        def run_candidate(candidate_index: int):
            candidate_seed = int(secrets.randbelow(1_000_000) + candidate_index)
            candidate_sessions = [
                {
                    **session,
                    'faculty_candidates': list(session['faculty_candidates']),
                }
                for session in sessions
            ]
            candidate_sessions = build_distributed_sessions(candidate_sessions, candidate_seed)

            faculty_busy_state = clone_faculty_busy_state(base_faculty_busy)
            room_usage_state = clone_room_usage_state(base_existing_room_usage)
            assigned_entries: list[dict[str, object]] = []
            unassigned_slots: list[dict[str, object]] = []
            proxy_suggestions: list[dict[str, object]] = []
            needs_room_entries: list[dict[str, object]] = []

            for day_name, day_date in days_with_dates:
                current_app.logger.info(
                    'Candidate %d scheduling for day %s (%s) - %d sessions remaining',
                    candidate_index,
                    day_name,
                    day_date,
                    len(candidate_sessions),
                )
                used_subjects_for_day: set[int] = set()
                last_scheduled_subjects = []
                slot_index = 0
                iterations = 0
                assigned_today = 0
                assigned_room_usage_day: dict[int, list[tuple[time, time]]] = defaultdict(list)

                while slot_index < len(slots) and assigned_today < max_lectures_per_day:
                    iterations += 1
                    if iterations > 2000:
                        current_app.logger.error(
                            'Scheduling loop exceeded max iterations on day %s; candidate=%d',
                            day_name,
                            candidate_index,
                        )
                        break

                    session_chosen = None
                    candidate_faculty = None
                    proxy_info = None
                    paired_session = None

                    for session in candidate_sessions:
                        block_slots = session['block_slots']
                        if block_slots > len(slots) - slot_index:
                            continue
                        slot_span = [slots[slot_index + i] for i in range(block_slots)]
                        subject_id = session['subject_id']

                        consecutive_count = 0
                        for subj_id, slot_idx in reversed(last_scheduled_subjects):
                            if slot_idx == slot_index - consecutive_count - 1 and subj_id == subject_id:
                                consecutive_count += 1
                            else:
                                break

                        if consecutive_count >= 2:
                            continue

                        for faculty in session['faculty_candidates']:
                            is_available, _ = faculty_is_available(
                                faculty['faculty_id'],
                                day_name,
                                slot_span,
                                day_date,
                                faculty_busy_state,
                            )
                            if is_available:
                                pair_attempted = False
                                if session['type'] == 'Theory':
                                    for other in candidate_sessions:
                                        if other is session:
                                            continue
                                        if (
                                            other['subject_id'] == session['subject_id']
                                            and other['type'] == 'Practical'
                                            and int(other['block_slots']) == 1
                                        ):
                                            next_index = slot_index + block_slots
                                            if next_index < len(slots) and (assigned_today + 2) <= max_lectures_per_day:
                                                next_slot_span = [slots[next_index]]
                                                is_avail_both, _ = faculty_is_available(
                                                    faculty['faculty_id'],
                                                    day_name,
                                                    next_slot_span,
                                                    day_date,
                                                    faculty_busy_state,
                                                )
                                                if is_avail_both:
                                                    room1 = room2 = None
                                                    if rooms_by_type:
                                                        room1 = find_available_room(
                                                            'Theory',
                                                            day_name,
                                                            slot_span[0][0],
                                                            slot_span[-1][1],
                                                            assigned_room_usage_day,
                                                            room_usage_state,
                                                        )
                                                        room2 = find_available_room(
                                                            'Practical',
                                                            day_name,
                                                            next_slot_span[0][0],
                                                            next_slot_span[0][1],
                                                            assigned_room_usage_day,
                                                            room_usage_state,
                                                        )
                                                        pair_attempted = True
                                                    else:
                                                        pair_attempted = True
                                                    if pair_attempted:
                                                        session_chosen = session
                                                        candidate_faculty = faculty
                                                        paired_session = other
                                                        chosen_pair_rooms = (room1, room2)
                                                        break
                                    if session_chosen and paired_session:
                                        break
                                if not session_chosen:
                                    session_chosen = session
                                    candidate_faculty = faculty
                                    paired_session = None
                                    break
                        if session_chosen:
                            break

                        alternative_faculty = []
                        for proxy in proxy_faculty_map.get(session['subject_id'], []):
                            if any(option['faculty_id'] == proxy['faculty_id'] for option in session['faculty_candidates']):
                                continue
                            is_available, _ = faculty_is_available(
                                proxy['faculty_id'],
                                day_name,
                                slot_span,
                                day_date,
                                faculty_busy_state,
                            )
                            if is_available:
                                alternative_faculty.append(proxy)

                        if alternative_faculty:
                            session_chosen = session
                            candidate_faculty = alternative_faculty[0]
                            proxy_info = {
                                'day': day_name,
                                'date': day_date.isoformat(),
                                'time': f"{slot_span[0][0].strftime('%H:%M')} - {slot_span[-1][1].strftime('%H:%M')}",
                                'subject_name': session['subject_name'],
                                'primary_faculty': session['faculty_candidates'][0]['name'],
                                'replacement_faculty': candidate_faculty['name'],
                                'reason': 'Allocated faculty unavailable',
                            }
                            break

                    if session_chosen and candidate_faculty:
                        def assign_single(session_obj, idx, preselected_room=None):
                            slot_start, slot_end = slots[idx]
                            room_assigned = preselected_room
                            if rooms_by_type and not room_assigned:
                                room_assigned = find_available_room(
                                    session_obj['type'],
                                    day_name,
                                    slot_start,
                                    slot_end,
                                    assigned_room_usage_day,
                                    room_usage_state,
                                )
                                if not room_assigned:
                                    current_app.logger.warning(
                                        'No room available for subject %s on %s %s-%s; scheduling without room',
                                        session_obj['subject_id'],
                                        day_name,
                                        slot_start.strftime('%H:%M'),
                                        slot_end.strftime('%H:%M'),
                                    )
                                    needs_room_entries.append(
                                        {
                                            'day': day_name,
                                            'date': day_date.isoformat(),
                                            'start_time': slot_start.strftime('%H:%M'),
                                            'end_time': slot_end.strftime('%H:%M'),
                                            'subject_id': session_obj['subject_id'],
                                            'subject_name': session_obj.get('subject_name'),
                                            'faculty_id': candidate_faculty['faculty_id'],
                                            'faculty_name': candidate_faculty['name'],
                                            'session_type': session_obj['type'],
                                            'reason': 'No room available',
                                        }
                                    )
                                    room_assigned = None

                            faculty_busy_state[candidate_faculty['faculty_id']][day_name].append((slot_start, slot_end))
                            if room_assigned:
                                assigned_room_usage_day[room_assigned['id']].append((slot_start, slot_end))
                                room_usage_state[day_name][room_assigned['id']].append((slot_start, slot_end))

                            assigned_entries.append(
                                {
                                    'day': day_name,
                                    'date': day_date.isoformat(),
                                    'start_time': slot_start.strftime('%H:%M'),
                                    'end_time': slot_end.strftime('%H:%M'),
                                    'subject_id': session_obj['subject_id'],
                                    'subject_name': session_obj['subject_name'],
                                    'faculty_id': candidate_faculty['faculty_id'],
                                    'faculty_name': candidate_faculty['name'],
                                    'session_type': session_obj['type'],
                                    'room_id': (room_assigned and room_assigned['id']) or None,
                                    'room_number': (room_assigned and room_assigned.get('room_number')) or None,
                                    'is_proxy': not any(
                                        option['faculty_id'] == candidate_faculty['faculty_id']
                                        for option in session_obj['faculty_candidates']
                                    ),
                                }
                            )
                            return True, None, room_assigned

                        if paired_session:
                            pre_room1 = pre_room2 = None
                            try:
                                pre_room1, pre_room2 = chosen_pair_rooms
                            except Exception:
                                pre_room1 = pre_room2 = None
                            ok1, _, r1 = assign_single(session_chosen, slot_index, pre_room1)
                            if not ok1:
                                paired_session = None
                            else:
                                ok2, _, _ = assign_single(paired_session, slot_index + 1, pre_room2)
                                if not ok2:
                                    assigned_entries.pop()
                                    fb = faculty_busy_state[candidate_faculty['faculty_id']][day_name]
                                    if fb and fb[-1] == (slots[slot_index][0], slots[slot_index][1]):
                                        fb.pop()
                                    if r1:
                                        ru = assigned_room_usage_day.get(r1['id'], [])
                                        if ru and ru[-1] == (slots[slot_index][0], slots[slot_index][1]):
                                            ru.pop()
                                        persisted_ru = room_usage_state.get(day_name, {}).get(r1['id'], [])
                                        if persisted_ru and persisted_ru[-1] == (slots[slot_index][0], slots[slot_index][1]):
                                            persisted_ru.pop()
                                    paired_session = None
                                else:
                                    candidate_sessions.remove(session_chosen)
                                    try:
                                        candidate_sessions.remove(paired_session)
                                    except ValueError:
                                        pass
                                    used_subjects_for_day.add(session_chosen['subject_id'])
                                    last_scheduled_subjects.append((session_chosen['subject_id'], slot_index))
                                    if paired_session:
                                        last_scheduled_subjects.append((paired_session['subject_id'], slot_index + 1))
                                    slot_index += 2
                                    assigned_today += 2
                                    if proxy_info:
                                        proxy_suggestions.append(proxy_info)
                                    continue

                        block_slots = session_chosen['block_slots']
                        assigned_any = False
                        for offset in range(block_slots):
                            slot_start, slot_end = slots[slot_index + offset]
                            ok, err, _ = assign_single(session_chosen, slot_index + offset, None)
                            if not ok:
                                unassigned_slots.append(
                                    {
                                        'day': day_name,
                                        'date': day_date.isoformat(),
                                        'start_time': slot_start.strftime('%H:%M'),
                                        'end_time': slot_end.strftime('%H:%M'),
                                        'reason': err or 'No available faculty',
                                    }
                                )
                                break
                            assigned_any = True
                        if assigned_any:
                            if proxy_info:
                                proxy_suggestions.append(proxy_info)
                            candidate_sessions.remove(session_chosen)
                            used_subjects_for_day.add(session_chosen['subject_id'])
                            for i in range(block_slots):
                                last_scheduled_subjects.append((session_chosen['subject_id'], slot_index + i))
                            slot_index += block_slots
                            assigned_today += block_slots
                    else:
                        slot_start, slot_end = slots[slot_index]
                        if candidate_sessions:
                            remaining_subjects = {}
                            for sess in candidate_sessions:
                                subject_name = sess['subject_name']
                                remaining_subjects[subject_name] = remaining_subjects.get(subject_name, 0) + 1
                            current_app.logger.warning(
                                'No faculty available for candidate=%d on %s at %s-%s. Remaining: %s',
                                candidate_index,
                                day_name,
                                slot_start.strftime('%H:%M'),
                                slot_end.strftime('%H:%M'),
                                remaining_subjects,
                            )
                        unassigned_slots.append(
                            {
                                'day': day_name,
                                'date': day_date.isoformat(),
                                'start_time': slot_start.strftime('%H:%M'),
                                'end_time': slot_end.strftime('%H:%M'),
                                'reason': 'No available faculty',
                            }
                        )
                        slot_index += 1

            assigned_entries.sort(key=lambda e: (WEEKDAY_ORDER.index(e['day']), e['start_time']))

            score_info = None
            warnings = []
            quality_score = 0.0
            baseline_quality_score = 0.0
            model_source = 'rule_fallback'
            feature_snapshot = {}
            score_breakdown = {
                'clash_risk': 1.0,
                'faculty_fatigue': 1.0,
                'room_overuse': 1.0,
                'student_load_imbalance': 1.0,
            }
            try:
                score_info = score_timetable_candidate(
                    assigned=assigned_entries,
                    unassigned=unassigned_slots,
                    proxy_suggestions=proxy_suggestions,
                    needs_room=needs_room_entries,
                    slots_per_day=slots_per_day,
                )
                quality_score = float(score_info.get('quality_score', 0.0))
                baseline_quality_score = float(score_info.get('baseline_quality_score', quality_score))
                model_source = str(score_info.get('model_source', model_source))
                feature_snapshot = score_info.get('features', {}) if isinstance(score_info.get('features'), dict) else {}
                score_breakdown = score_info.get('score_breakdown', score_breakdown)
                warnings = score_info.get('warnings', [])
            except Exception as scoring_error:
                current_app.logger.warning(
                    'Timetable quality scoring failed for candidate %d: %s',
                    candidate_index,
                    str(scoring_error),
                )
                warnings = ['Quality scoring failed; using baseline candidate ranking fallback.']

            return {
                'candidate_index': candidate_index,
                'candidate_seed': candidate_seed,
                'assigned': assigned_entries,
                'unassigned': unassigned_slots,
                'proxy_suggestions': proxy_suggestions,
                'needs_room': needs_room_entries,
                'quality_score': round(quality_score, 2),
                'baseline_quality_score': round(baseline_quality_score, 2),
                'score_breakdown': score_breakdown,
                'warnings': warnings,
                'model_source': model_source,
                'features': feature_snapshot,
            }

        candidate_results = [run_candidate(index + 1) for index in range(candidate_count)]
        candidate_results.sort(
            key=lambda item: (
                float(item.get('quality_score') or 0.0),
                -len(item.get('unassigned') or []),
                -len(item.get('needs_room') or []),
            ),
            reverse=True,
        )

        best_candidate = candidate_results[0]
        assigned_entries = best_candidate['assigned']
        unassigned_slots = best_candidate['unassigned']
        proxy_suggestions = best_candidate['proxy_suggestions']
        needs_room_entries = best_candidate['needs_room']
        current_app.logger.info(
            'Selected candidate=%s quality_score=%.2f baseline=%.2f model_source=%s',
            best_candidate.get('candidate_index', 1),
            float(best_candidate.get('quality_score') or 0.0),
            float(best_candidate.get('baseline_quality_score') or 0.0),
            best_candidate.get('model_source', 'unknown'),
        )

        top_candidates = []
        for item in candidate_results[:3]:
            top_candidates.append(
                {
                    'candidate_index': item['candidate_index'],
                    'quality_score': item['quality_score'],
                    'assigned_count': len(item.get('assigned') or []),
                    'unassigned_count': len(item.get('unassigned') or []),
                    'needs_room_count': len(item.get('needs_room') or []),
                }
            )

        # Persist timetable if not previewing
        if not preview_only:
            # Archive the currently active timetable version before replacement.
            archive_scope_clause = "course_id = %s AND class_id = %s AND division_id = %s"
            archive_params = (course_id, class_id, division_id)
            if has_is_active_column:
                archive_scope_clause += " AND COALESCE(is_active, 1) = 1"
            try:
                cursor.execute(f"""
                    INSERT INTO timetable_history 
                    (course_id, class_id, division_id, day_of_week, start_time, end_time, 
                     subject_id, faculty_id, room_id, archived_at)
                    SELECT course_id, class_id, division_id, day_of_week, start_time, end_time,
                           subject_id, faculty_id, room_id, NOW()
                    FROM timetable
                    WHERE {archive_scope_clause}
                """, archive_params)
                current_app.logger.info('Archived %d old timetable entries to history', cursor.rowcount)
            except Exception as e:
                current_app.logger.warning('Could not archive to timetable_history (table may not exist): %s', str(e))

            if has_is_active_column:
                cursor.execute(
                    """
                    UPDATE timetable
                    SET is_active = 0
                    WHERE course_id = %s AND class_id = %s AND division_id = %s
                      AND COALESCE(is_active, 1) = 1
                    """,
                    (course_id, class_id, division_id),
                )
                current_app.logger.info('Retired %d active timetable entries', cursor.rowcount)
            else:
                cursor.execute(
                    "DELETE FROM timetable WHERE course_id = %s AND class_id = %s AND division_id = %s",
                    (course_id, class_id, division_id),
                )

            for entry in assigned_entries:
                insert_columns = [
                    'course_id',
                    'class_id',
                    'division_id',
                    'day_of_week',
                    'start_time',
                    'end_time',
                    'subject_id',
                    'faculty_id',
                ]
                insert_values = [
                    course_id,
                    class_id,
                    division_id,
                    entry['day'],
                    entry['start_time'],
                    entry['end_time'],
                    entry['subject_id'],
                    entry['faculty_id'],
                ]

                if has_room_column and entry.get('room_id'):
                    insert_columns.append('room_id')
                    insert_values.append(entry.get('room_id'))
                if has_is_active_column:
                    insert_columns.append('is_active')
                    insert_values.append(1)

                column_sql = ', '.join(insert_columns)
                placeholder_sql = ', '.join(['%s'] * len(insert_values))
                cursor.execute(
                    f"INSERT INTO timetable ({column_sql}) VALUES ({placeholder_sql})",
                    tuple(insert_values),
                )
            connection.commit()

            # Persist quality scoring metadata for phase-2 ML data.
            try:
                run_id = str(uuid4())
                cursor.execute(
                    """
                    INSERT INTO timetable_quality_runs
                    (
                        run_id,
                        course_id,
                        class_id,
                        division_id,
                        week_start,
                        quality_score,
                        clash_risk,
                        faculty_fatigue,
                        room_overuse,
                        student_load_imbalance,
                        candidate_count,
                        selected_candidate_index,
                        created_by,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (
                        run_id,
                        course_id,
                        class_id,
                        division_id,
                        week_start,
                        best_candidate.get('quality_score', 0.0),
                        best_candidate.get('score_breakdown', {}).get('clash_risk', 1.0),
                        best_candidate.get('score_breakdown', {}).get('faculty_fatigue', 1.0),
                        best_candidate.get('score_breakdown', {}).get('room_overuse', 1.0),
                        best_candidate.get('score_breakdown', {}).get('student_load_imbalance', 1.0),
                        candidate_count,
                        best_candidate.get('candidate_index', 1),
                        created_by,
                    ),
                )

                for item in candidate_results:
                    candidate_breakdown = item.get('score_breakdown', {}) if isinstance(item.get('score_breakdown'), dict) else {}
                    cursor.execute(
                        """
                        INSERT INTO timetable_quality_candidates
                        (
                            run_id,
                            candidate_index,
                            is_selected,
                            quality_score,
                            clash_risk,
                            faculty_fatigue,
                            room_overuse,
                            student_load_imbalance,
                            assigned_count,
                            unassigned_count,
                            needs_room_count,
                            created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        """,
                        (
                            run_id,
                            int(item.get('candidate_index') or 0),
                            1 if int(item.get('candidate_index') or 0) == int(best_candidate.get('candidate_index') or 0) else 0,
                            float(item.get('quality_score') or 0.0),
                            float(candidate_breakdown.get('clash_risk', 1.0) or 1.0),
                            float(candidate_breakdown.get('faculty_fatigue', 1.0) or 1.0),
                            float(candidate_breakdown.get('room_overuse', 1.0) or 1.0),
                            float(candidate_breakdown.get('student_load_imbalance', 1.0) or 1.0),
                            len(item.get('assigned') or []),
                            len(item.get('unassigned') or []),
                            len(item.get('needs_room') or []),
                        ),
                    )
                connection.commit()
            except Exception as quality_save_error:
                current_app.logger.warning('Could not persist timetable_quality_runs metadata: %s', str(quality_save_error))

        message = f"Scheduled {len(assigned_entries)} session(s) across {len(days_with_dates)} day(s)."
        if unassigned_slots:
            message += f" {len(unassigned_slots)} slot(s) could not be assigned."

        return {
            'status': 'success' if assigned_entries else 'warning',
            'message': message,
            'assigned': assigned_entries,
            'unassigned': unassigned_slots,
            'proxy_suggestions': proxy_suggestions,
            'skipped_holidays': skipped_holidays,
            'needs_room': needs_room_entries,
            'quality_score': best_candidate.get('quality_score', 0.0),
            'baseline_quality_score': best_candidate.get('baseline_quality_score', best_candidate.get('quality_score', 0.0)),
            'model_source': best_candidate.get('model_source', 'rule_fallback'),
            'score_breakdown': best_candidate.get('score_breakdown', {}),
            'warnings': best_candidate.get('warnings', []),
            'candidate_count': candidate_count,
            'selected_candidate_index': best_candidate.get('candidate_index', 1),
            'top_candidates': top_candidates,
        }
    finally:

        cursor.close()

        connection.close()

