
from flask import Blueprint, render_template, redirect, url_for, session, request, flash, current_app, jsonify, make_response
from functools import wraps
from collections import defaultdict
from datetime import time, timedelta, datetime, date
import math
import os
import random
import secrets

from MySQLdb.cursors import DictCursor

from app import mysql
# import openpyxl
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
from security import get_user_permissions
from forms import InvitationForm

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Allow both Admin and Super Admin to access admin pages
        if 'role' not in session or session['role'] not in ('Admin', 'Super Admin'):
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for('auth.admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Utility functions ---
def format_time(time_obj):
    """Convert time/timedelta to HH:MM string format"""
    if time_obj is None:
        return ''
    if isinstance(time_obj, timedelta):
        total_seconds = int(time_obj.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}"
    elif hasattr(time_obj, 'strftime'):
        return time_obj.strftime('%H:%M')
    else:
        return str(time_obj)

def get_time_ago(timestamp):
    """Convert timestamp to human-readable time ago format"""
    if timestamp is None:
        return 'Unknown'
    now = datetime.now()
    diff = now - timestamp
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return 'Just now'
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f'{minutes} minute{"s" if minutes != 1 else ""} ago'
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f'{hours} hour{"s" if hours != 1 else ""} ago'
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f'{days} day{"s" if days != 1 else ""} ago'
    else:
        return timestamp.strftime('%b %d, %Y')

# --- Helper for Pagination ---
def paginate(query, params, page, per_page=10):
    cursor = mysql.connection.cursor()
    
    # Correctly build the count query by finding the FROM clause in the full query
    from_clause_index = query.upper().find(' FROM ')
    if from_clause_index == -1:
        # This will raise a syntax error on execution anyway, but it's a safeguard.
        raise ValueError("Query for pagination must include a FROM clause.")
        
    count_query = f"SELECT COUNT(*) {query[from_clause_index:]}"

    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]
    total_pages = math.ceil(total / per_page)
    
    offset = (page - 1) * per_page
    data_query = f"{query} LIMIT %s OFFSET %s"
    cursor.execute(data_query, params + (per_page, offset))
    results = cursor.fetchall()
    cursor.close()
    return results, total_pages

# --- Timetable Logic ---

WEEKDAY_ORDER = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def _parse_time(value: str, field: str) -> time:
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

    cursor = mysql.connection.cursor(DictCursor)
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

        # Faculty workload and availability
        cursor.execute(
            """
            SELECT faculty_id, day_of_week, start_time, end_time
            FROM timetable
            WHERE faculty_id IS NOT NULL
        """
        )
        faculty_busy: dict[int, dict[str, list[tuple[time, time]]]] = defaultdict(lambda: defaultdict(list))
        for row in cursor.fetchall():
            busy_start = _coerce_time_value(row['start_time'])
            busy_end = _coerce_time_value(row['end_time'])
            faculty_busy[row['faculty_id']][row['day_of_week']].append((busy_start, busy_end))

        cursor.execute(
            """
            SELECT faculty_id, day_of_week, start_time, end_time, is_available
            FROM faculty_availability
        """
        )
        availability_map: dict[int, dict[str, list[dict[str, object]]]] = defaultdict(lambda: defaultdict(list))
        for row in cursor.fetchall():
            availability_map[row['faculty_id']][row['day_of_week']].append(
                {
                    'start': _coerce_time_value(row['start_time']),
                    'end': _coerce_time_value(row['end_time']),
                    'is_available': bool(row['is_available']),
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
            cur2 = mysql.connection.cursor()
            cur2.execute("SHOW COLUMNS FROM timetable LIKE 'room_id'")
            has_room_column = cur2.fetchone() is not None
            cur2.close()

            # Load rooms if table exists
            cur3 = mysql.connection.cursor(DictCursor)
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
                cur4 = mysql.connection.cursor(DictCursor)
                cur4.execute("""
                    SELECT day_of_week, start_time, end_time, room_id
                    FROM timetable
                    WHERE room_id IS NOT NULL
                """)
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

        assigned_entries: list[dict[str, object]] = []
        unassigned_slots: list[dict[str, object]] = []
        proxy_suggestions: list[dict[str, object]] = []
        # Sessions assigned but missing a room (fallback list) — these require post-generation room allocation
        needs_room_entries: list[dict[str, object]] = []

        def faculty_is_available(faculty_id: int, day_name: str, slot_group: list[tuple[time, time]], day_date: date) -> tuple[bool, str | None]:
            if (faculty_id, day_date) in faculty_absences:
                return False, 'absent'

            for busy_start, busy_end in faculty_busy.get(faculty_id, {}).get(day_name, []):
                if any(_times_overlap(busy_start, busy_end, start, end) for start, end in slot_group):
                    return False, 'conflict'

            availability = availability_map.get(faculty_id, {}).get(day_name)
            if availability:
                # Ensure there is at least one available window covering the slot group and no explicit unavailability
                for start, end in slot_group:
                    # Check for explicit unavailability (is_available=0)
                    blocked = any(
                        not window['is_available'] and _times_overlap(window['start'], window['end'], start, end)
                        for window in availability
                    )
                    if blocked:
                        return False, 'not_available'
                    
                    # Check if any available window (is_available=1) covers this slot
                    # Allow multiple windows throughout the day
                    allowed = any(
                        window['is_available'] and window['start'] <= start and window['end'] >= end
                        for window in availability
                    )
                    if not allowed:
                        return False, 'not_available'
            # If no availability records exist for this faculty+day, treat as fully available

            return True, None

        # Sort sessions for balanced distribution across subjects
        # Group by subject_id to count sessions per subject, then distribute evenly
        from collections import Counter
        subject_session_counts = Counter(s['subject_id'] for s in sessions)
        
        # Create session distribution order: round-robin through subjects
        # This ensures each subject gets sessions distributed evenly across the week
        subject_order = sorted(subject_session_counts.keys())
        distributed_sessions = []
        max_sessions = max(subject_session_counts.values())
        
        for session_index in range(max_sessions):
            for subject_id in subject_order:
                subject_sessions = [s for s in sessions if s['subject_id'] == subject_id]
                if session_index < len(subject_sessions):
                    distributed_sessions.append(subject_sessions[session_index])
        
        sessions = distributed_sessions

        # Determine expected group size for capacity matching
        required_capacity = 0
        try:
            curcap = mysql.connection.cursor()
            curcap.execute(
                "SELECT COUNT(*) FROM students WHERE course_id = %s AND class_id = %s AND division_id = %s",
                (course_id, class_id, division_id),
            )
            required_capacity = int(curcap.fetchone()[0] or 0)
            curcap.close()
        except Exception:
            required_capacity = 0

        # Helper: find available room for the given slot span and type
        def find_available_room(required_type: str, day_name: str, slot_start: time, slot_end: time, assigned_room_usage_day: dict[int, list[tuple[time, time]]]):
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
                for (st, et) in existing_room_usage.get(day_name, {}).get(room['id'], []):
                    times.append((st, et))
                # Already assigned in this run
                for (st, et) in assigned_room_usage_day.get(room['id'], []):
                    times.append((st, et))
                if any(overlaps(st, et, slot_start, slot_end) for (st, et) in times):
                    continue
                return room
            return None

        for day_name, day_date in days_with_dates:
            current_app.logger.info('Scheduling for day %s (%s)', day_name, day_date)
            used_subjects_for_day: set[int] = set()
            # Track last 2 scheduled subjects to prevent 3+ consecutive sessions of same subject
            last_scheduled_subjects = []  # List of (subject_id, slot_index) tuples
            slot_index = 0
            iterations = 0
            assigned_today = 0
            # Track assigned room usage per day for conflict checks among new assignments
            assigned_room_usage_day: dict[int, list[tuple[time, time]]] = defaultdict(list)
            while slot_index < len(slots) and assigned_today < max_lectures_per_day:
                iterations += 1
                if iterations > 2000:
                    current_app.logger.error('Scheduling loop exceeded max iterations on day %s; aborting to avoid infinite loop', day_name)
                    break
                # log progress at each slot for debugging (throttle by small days)
                current_app.logger.debug('Day %s: processing slot_index=%d assigned_today=%d/%d', day_name, slot_index, assigned_today, max_lectures_per_day)
                session_chosen = None
                candidate_faculty = None
                proxy_info = None
                paired_session = None

                for session in sessions:
                    block_slots = session['block_slots']
                    if block_slots > len(slots) - slot_index:
                        continue
                    slot_span = [slots[slot_index + i] for i in range(block_slots)]

                    # NOTE: Removed used_subjects_for_day restriction to allow same subject multiple times per day
                    # This enables proper scheduling when subjects have 4+ lectures per week
                    
                    # NEW: Limit consecutive sessions per subject to max 2 sessions
                    # Check if last 2 scheduled slots were the same subject
                    subject_id = session['subject_id']
                    
                    # Count consecutive sessions of this subject at current position
                    consecutive_count = 0
                    for subj_id, slot_idx in reversed(last_scheduled_subjects):
                        if slot_idx == slot_index - consecutive_count - 1 and subj_id == subject_id:
                            consecutive_count += 1
                        else:
                            break
                    
                    if consecutive_count >= 2:
                        # Skip - already have 2 consecutive sessions of this subject
                        current_app.logger.debug('Skipping %s (subject %s) - already %d consecutive sessions', 
                                                session['subject_name'], subject_id, consecutive_count)
                        continue

                    for faculty in session['faculty_candidates']:
                        is_available, reason = faculty_is_available(faculty['faculty_id'], day_name, slot_span, day_date)
                        if is_available:
                            # Try to pair Theory+Practical as continuous if both single-slot and available
                            pair_attempted = False
                            if session['type'] == 'Theory':
                                # look for a 1-slot Practical for same subject
                                for other in sessions:
                                    if other is session:
                                        continue
                                    if other['subject_id'] == session['subject_id'] and other['type'] == 'Practical' and int(other['block_slots']) == 1:
                                        # check next slot availability and daily cap
                                        next_index = slot_index + block_slots
                                        if next_index < len(slots) and (assigned_today + 2) <= max_lectures_per_day:
                                            next_slot_span = [slots[next_index]]
                                            is_avail_both, reason2 = faculty_is_available(faculty['faculty_id'], day_name, next_slot_span, day_date)
                                            if is_avail_both:
                                                # Room assignment: Theory uses Classroom, Practical uses Laboratory
                                                room1 = room2 = None
                                                if rooms_by_type:
                                                    room1 = find_available_room('Theory', day_name, slot_span[0][0], slot_span[-1][1], assigned_room_usage_day)  # Theory → Classroom
                                                    room2 = find_available_room('Practical', day_name, next_slot_span[0][0], next_slot_span[0][1], assigned_room_usage_day)  # Practical → Laboratory
                                                    if not room1 or not room2:
                                                        # Rooms not found — we'll still attempt pairing but record that rooms are missing
                                                        current_app.logger.warning('Pairing proceeding without both rooms for subject %s on %s', session['subject_id'], day_name)
                                                        pair_attempted = True
                                                    else:
                                                        pair_attempted = True
                                                else:
                                                    pair_attempted = True
                                                if pair_attempted:
                                                    session_chosen = session
                                                    candidate_faculty = faculty
                                                    proxy_info = None
                                                    paired_session = other
                                                    # Attach preselected rooms into tuple for later use via closure-level vars (may be None)
                                                    chosen_pair_rooms = (room1, room2)
                                                    break
                                        # if can't pair, continue to try single assignment below
                                if session_chosen and paired_session:
                                    break
                            # If no pairing or not applicable, accept single assignment for this faculty
                            if not session_chosen:
                                session_chosen = session
                                candidate_faculty = faculty
                                proxy_info = None
                                paired_session = None
                                break
                    if session_chosen:
                        break

                    # Gather proxy suggestions when none of the allotted faculty are free
                    alternative_faculty = []
                    for proxy in proxy_faculty_map.get(session['subject_id'], []):
                        if any(option['faculty_id'] == proxy['faculty_id'] for option in session['faculty_candidates']):
                            continue
                        is_available, reason = faculty_is_available(proxy['faculty_id'], day_name, slot_span, day_date)
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
                    current_app.logger.debug('Selected session subject_id=%s type=%s block_slots=%s candidate_faculty=%s', session_chosen.get('subject_id'), session_chosen.get('type'), session_chosen.get('block_slots'), candidate_faculty.get('faculty_id'))
                    # Assign main session (and optional paired next session)
                    def assign_single(session_obj, idx, preselected_room=None):
                        slot_start, slot_end = slots[idx]
                        # Room selection if configured
                        room_assigned = preselected_room
                        if rooms_by_type and not room_assigned:
                            room_assigned = find_available_room(session_obj['type'], day_name, slot_start, slot_end, assigned_room_usage_day)
                            if not room_assigned:
                                # FALLBACK: when rooms exist but none match, allow scheduling without room
                                current_app.logger.warning('No room available for subject %s on %s %s-%s; scheduling without room', session_obj['subject_id'], day_name, slot_start.strftime('%H:%M'), slot_end.strftime('%H:%M'))
                                # Record entry that needs room later
                                needs_room_entries.append({
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
                                })
                                room_assigned = None
                        # Mark faculty busy
                        faculty_busy[candidate_faculty['faculty_id']][day_name].append((slot_start, slot_end))
                        if room_assigned:
                            assigned_room_usage_day[room_assigned['id']].append((slot_start, slot_end))
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
                        current_app.logger.info('Assigned subject %s to faculty %s on %s %s-%s (room=%s)', session_obj['subject_id'], candidate_faculty['faculty_id'], day_name, slot_start.strftime('%H:%M'), slot_end.strftime('%H:%M'), (room_assigned and (room_assigned.get('room_number') if isinstance(room_assigned, dict) else room_assigned)) or None)
                        return True, None, room_assigned

                    # Handle paired assignment (Theory + Practical consecutive) if selected
                    if paired_session:
                        # Use tentative rooms from earlier calculation if available
                        pre_room1 = pre_room2 = None
                        try:
                            pre_room1, pre_room2 = chosen_pair_rooms  # may not exist if rooms disabled
                        except Exception:
                            pre_room1 = pre_room2 = None
                        ok1, err1, r1 = assign_single(session_chosen, slot_index, pre_room1)
                        if not ok1:
                            # fall back: try as single session only
                            paired_session = None
                        else:
                            ok2, err2, r2 = assign_single(paired_session, slot_index + 1, pre_room2)
                            if not ok2:
                                # rollback first assignment in memory (remove entry and busy marks)
                                # remove last assigned entry
                                last = assigned_entries.pop()
                                # remove busy marks and room usage added
                                fb = faculty_busy[candidate_faculty['faculty_id']][day_name]
                                if fb and fb[-1] == (slots[slot_index][0], slots[slot_index][1]):
                                    fb.pop()
                                if r1:
                                    ru = assigned_room_usage_day.get(r1['id'], [])
                                    if ru and ru[-1] == (slots[slot_index][0], slots[slot_index][1]):
                                        ru.pop()
                                paired_session = None
                            else:
                                # Success: remove both sessions
                                sessions.remove(session_chosen)
                                try:
                                    sessions.remove(paired_session)
                                except ValueError:
                                    pass
                                used_subjects_for_day.add(session_chosen['subject_id'])
                                # Track last scheduled subjects for consecutive limit (2 paired sessions)
                                last_scheduled_subjects.append((session_chosen['subject_id'], slot_index))
                                if paired_session:
                                    last_scheduled_subjects.append((paired_session['subject_id'], slot_index + 1))
                                slot_index += 2
                                assigned_today += 2
                                if proxy_info:
                                    proxy_suggestions.append(proxy_info)
                                continue

                    # Single session path
                    block_slots = session_chosen['block_slots']
                    assigned_any = False
                    for offset in range(block_slots):
                        slot_start, slot_end = slots[slot_index + offset]
                        # Room selection for each slot in the block
                        pre_room = None
                        ok, err, room_sel = assign_single(session_chosen, slot_index + offset, pre_room)
                        if not ok:
                            # couldn't assign due to room, mark unassigned for this slot and break the block
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
                        sessions.remove(session_chosen)
                        used_subjects_for_day.add(session_chosen['subject_id'])
                        # Track last scheduled subjects for consecutive limit
                        for i in range(block_slots):
                            last_scheduled_subjects.append((session_chosen['subject_id'], slot_index + i))
                        slot_index += block_slots
                        assigned_today += block_slots
                else:
                    slot_start, slot_end = slots[slot_index]
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

        # Persist timetable if not previewing
        if not preview_only:
            # Archive old timetable to history before deleting
            try:
                cursor.execute("""
                    INSERT INTO timetable_history 
                    (course_id, class_id, division_id, day_of_week, start_time, end_time, 
                     subject_id, faculty_id, room_id, archived_at)
                    SELECT course_id, class_id, division_id, day_of_week, start_time, end_time,
                           subject_id, faculty_id, room_id, NOW()
                    FROM timetable
                    WHERE course_id = %s AND class_id = %s AND division_id = %s
                """, (course_id, class_id, division_id))
                current_app.logger.info('Archived %d old timetable entries to history', cursor.rowcount)
            except Exception as e:
                current_app.logger.warning('Could not archive to timetable_history (table may not exist): %s', str(e))
            
            cursor.execute(
                "DELETE FROM timetable WHERE course_id = %s AND class_id = %s AND division_id = %s",
                (course_id, class_id, division_id),
            )
            for entry in assigned_entries:
                if has_room_column and entry.get('room_id'):
                    cursor.execute(
                        """
                        INSERT INTO timetable (course_id, class_id, division_id, day_of_week, start_time, end_time, subject_id, faculty_id, room_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            course_id,
                            class_id,
                            division_id,
                            entry['day'],
                            entry['start_time'],
                            entry['end_time'],
                            entry['subject_id'],
                            entry['faculty_id'],
                            entry.get('room_id'),
                        ),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO timetable (course_id, class_id, division_id, day_of_week, start_time, end_time, subject_id, faculty_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            course_id,
                            class_id,
                            division_id,
                            entry['day'],
                            entry['start_time'],
                            entry['end_time'],
                            entry['subject_id'],
                            entry['faculty_id'],
                        ),
                    )
            mysql.connection.commit()

        assigned_entries.sort(key=lambda e: (WEEKDAY_ORDER.index(e['day']), e['start_time']))

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
        }
    finally:
        cursor.close()

# --- Admin view of a specific faculty: timetable, availability, absences, proxy log ---
def _is_faculty_free(cursor, faculty_id, day, start_time, end_time):
    cursor.execute(
        """
        SELECT 1
        FROM timetable
        WHERE faculty_id = %s
          AND day_of_week = %s
          AND NOT (end_time <= %s OR start_time >= %s)
        LIMIT 1
        """,
        (faculty_id, day, start_time, end_time),
    )
    return cursor.fetchone() is None


def _admin_find_and_assign_proxy(absent_faculty_id, absence_date):
    """Replicate teacher proxy assignment for admin-triggered absence creation."""
    cursor = mysql.connection.cursor()
    day_of_week = absence_date.strftime('%A')
    cursor.execute(
        "SELECT id, subject_id, start_time, end_time FROM timetable WHERE faculty_id = %s AND day_of_week = %s",
        (absent_faculty_id, day_of_week),
    )
    affected_lectures = cursor.fetchall()

    for lecture in affected_lectures:
        timetable_id, subject_id, start_time, end_time = lecture
        cursor.execute(
            "SELECT faculty_id FROM faculty_allocations WHERE subject_id = %s AND faculty_id != %s",
            (subject_id, absent_faculty_id),
        )
        potential_proxies = cursor.fetchall()
        assigned_proxy_id = next(
            (p[0] for p in potential_proxies if _is_faculty_free(cursor, p[0], day_of_week, start_time, end_time)),
            None,
        )

        status = 'ASSIGNED' if assigned_proxy_id else 'UNASSIGNED'
        cursor.execute(
            """
            INSERT INTO proxy_log (original_faculty_id, proxy_faculty_id, timetable_id, absence_date, status, approval_status, approval_date, approved_by)
            VALUES (%s, %s, %s, %s, %s, 'APPROVED', NOW(), %s)
            """,
            (absent_faculty_id, assigned_proxy_id, timetable_id, absence_date, status, session.get('user_id')),
        )

    mysql.connection.commit()
    cursor.close()


@admin_bp.route('/faculty/<int:faculty_id>/details')
@admin_required
def faculty_details(faculty_id):
    """Details dashboard for a faculty member (timetable, availability, absences, proxy log)."""
    # Basic lookup to show name/email in header
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT name, email FROM faculty WHERE id = %s", [faculty_id])
    fac = cursor.fetchone()
    cursor.close()
    if not fac:
        flash('Faculty not found.', 'danger')
        return redirect(url_for('admin.manage_faculty'))
    return render_template('admin/faculty_details.html', faculty_id=faculty_id, faculty_name=fac[0], faculty_email=fac[1])


@admin_bp.route('/faculty/<int:faculty_id>/timetable/data')
@admin_required
def faculty_timetable_data(faculty_id):
    cursor = mysql.connection.cursor()
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


@admin_bp.route('/faculty/<int:faculty_id>/timetable/download')
@admin_required
def faculty_timetable_download(faculty_id):
    cursor = mysql.connection.cursor()
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
        day, start_t, end_t, subj, cls, div = row[0], row[1], row[2], row[3], row[4], row[5]
        room = row[6] if has_room else ''
        writer.writerow([day, format_time(start_t), format_time(end_t), subj, cls, div, room])

    resp = make_response(output.getvalue())
    resp.headers['Content-Disposition'] = f'attachment; filename=faculty_{faculty_id}_timetable.csv'
    resp.headers['Content-Type'] = 'text/csv'
    return resp


@admin_bp.route('/faculty/<int:faculty_id>/availability', methods=['GET', 'POST'])
@admin_required
def faculty_availability_admin(faculty_id):
    cursor = mysql.connection.cursor()
    if request.method == 'POST':
        # Support both JSON (new multi-slot format) and form data (legacy single-slot format)
        json_data = request.get_json(silent=True)
        
        cursor.execute("DELETE FROM faculty_availability WHERE faculty_id = %s", [faculty_id])
        
        if json_data and 'availability' in json_data:
            # New format: multiple slots per day
            availability_slots = json_data.get('availability', [])
            for slot in availability_slots:
                day = slot.get('day')
                start_time = slot.get('start_time')
                end_time = slot.get('end_time')
                is_available = slot.get('is_available', True)
                
                if day and start_time and end_time:
                    cursor.execute(
                        """
                        INSERT INTO faculty_availability (faculty_id, day_of_week, start_time, end_time, is_available)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (faculty_id, day, start_time, end_time, 1 if is_available else 0),
                    )
            mysql.connection.commit()
            cursor.close()
            return jsonify({'ok': True, 'message': 'Availability updated with multiple time slots.'})
        else:
            # Legacy format: one slot per day from form data
            days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
            for day in days:
                is_avail = request.form.get(f'{day}-available') == 'on'
                start_t = request.form.get(f'{day}-start') or '00:00'
                end_t = request.form.get(f'{day}-end') or '00:00'
                cursor.execute(
                    """
                    INSERT INTO faculty_availability (faculty_id, day_of_week, start_time, end_time, is_available)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (faculty_id, day, start_t, end_t, 1 if is_avail else 0),
                )
            mysql.connection.commit()
            cursor.close()
            flash('Availability updated.', 'success')
            return redirect(url_for('admin.faculty_details', faculty_id=faculty_id))

    # GET handler - return all slots grouped by day (supports multiple slots)
    cursor.execute(
        """SELECT day_of_week, start_time, end_time, is_available 
           FROM faculty_availability 
           WHERE faculty_id = %s
           ORDER BY day_of_week, start_time""",
        [faculty_id],
    )
    
    avail_by_day = {}
    for day, st, et, avail_flag in cursor.fetchall():
        if day not in avail_by_day:
            avail_by_day[day] = []
        avail_by_day[day].append({
            'start_time': format_time(st),
            'end_time': format_time(et),
            'is_available': bool(avail_flag),
        })
    
    cursor.close()
    return jsonify(avail_by_day)


@admin_bp.route('/faculty/<int:faculty_id>/absences', methods=['GET', 'POST'])
@admin_required
def faculty_absences_admin(faculty_id):
    cursor = mysql.connection.cursor()
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
    mysql.connection.commit()
    _admin_find_and_assign_proxy(faculty_id, ad)
    cursor.close()
    return jsonify({'ok': True})


@admin_bp.route('/faculty/<int:faculty_id>/absences/<int:absence_id>', methods=['DELETE'])
@admin_required
def faculty_absence_delete_admin(faculty_id, absence_id):
    cursor = mysql.connection.cursor()
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
    mysql.connection.commit()
    cursor.close()
    return jsonify({'ok': True})


@admin_bp.route('/faculty/<int:faculty_id>/absences/<int:absence_id>/approve', methods=['POST'])
@admin_required
def faculty_absence_approve_admin(faculty_id, absence_id):
    cursor = mysql.connection.cursor()
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
    mysql.connection.commit()
    cursor.close()
    # trigger proxy assignment
    _admin_find_and_assign_proxy(faculty_id, absence_date if hasattr(absence_date, 'strftime') else datetime.strptime(str(absence_date), '%Y-%m-%d').date())
    flash('Absence approved and proxies assigned.', 'success')
    return jsonify({'ok': True})


@admin_bp.route('/faculty/<int:faculty_id>/absences/<int:absence_id>/reject', methods=['POST'])
@admin_required
def faculty_absence_reject_admin(faculty_id, absence_id):
    cursor = mysql.connection.cursor()
    cursor.execute(
        "UPDATE faculty_absences SET status = 'REJECTED' WHERE id = %s AND faculty_id = %s AND status != 'PROCESSED'",
        (absence_id, faculty_id),
    )
    mysql.connection.commit()
    cursor.close()
    flash('Absence request rejected.', 'warning')
    return jsonify({'ok': True})


@admin_bp.route('/faculty/<int:faculty_id>/proxy-log')
@admin_required
def faculty_proxy_log_admin(faculty_id):
    cursor = mysql.connection.cursor()
    cursor.execute(
        """
        SELECT p.id, p.absence_date, p.status, p.approval_status, t.day_of_week, t.start_time, t.end_time, 
               s.id AS subject_id, s.name AS subject_name,
               ofc.id AS original_id, ofc.name AS original_name, 
               pfc.id AS proxy_id, pfc.name AS proxy_name
        FROM proxy_log p
        JOIN timetable t ON p.timetable_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        JOIN faculty ofc ON ofc.id = p.original_faculty_id
        LEFT JOIN faculty pfc ON pfc.id = p.proxy_faculty_id
        WHERE p.original_faculty_id = %s OR p.proxy_faculty_id = %s
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


@admin_bp.route('/faculty/<int:faculty_id>/proxy-log/<int:proxy_id>/approve', methods=['POST'])
@admin_required
def faculty_proxy_approve_admin(faculty_id, proxy_id):
    cursor = mysql.connection.cursor()
    
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
    mysql.connection.commit()
    cursor.close()
    
    flash('Proxy request approved successfully.', 'success')
    return jsonify({'ok': True, 'proxy_faculty_id': proxy_faculty_id})


@admin_bp.route('/faculty/<int:faculty_id>/proxy-log/<int:proxy_id>/reject', methods=['POST'])
@admin_required
def faculty_proxy_reject_admin(faculty_id, proxy_id):
    cursor = mysql.connection.cursor()
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
    mysql.connection.commit()
    cursor.close()
    flash('Proxy request rejected.', 'warning')
    return jsonify({'ok': True})

# --- Holiday Management ---
@admin_bp.route('/holidays')
@admin_required
def holidays_index():
    """List holidays and show add form."""
    cursor = mysql.connection.cursor()
    cursor.execute(
        """
        SELECT id, holiday_date, day_of_week, name, applies_to_program, is_recurring
        FROM institution_holidays
        ORDER BY is_recurring DESC,
                 CASE WHEN holiday_date IS NULL THEN 1 ELSE 0 END,
                 holiday_date ASC,
                 FIELD(day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')
        """
    )
    rows = cursor.fetchall()
    cursor.close()
    items = []
    for rid, hdate, dow, name, program, is_rec in rows:
        items.append({
            'id': rid,
            'holiday_date': hdate.strftime('%Y-%m-%d') if hdate and hasattr(hdate, 'strftime') else (hdate or ''),
            'day_of_week': dow or '',
            'name': name,
            'applies_to_program': program,
            'is_recurring': bool(is_rec),
        })
    return render_template('admin/holidays.html', holidays=items)


@admin_bp.route('/holidays/add', methods=['POST'])
@admin_required
def holidays_add():
    """Add a date-specific or recurring weekly holiday."""
    name = (request.form.get('name') or '').strip()
    applies_to_program = request.form.get('applies_to_program') or 'Both'
    holiday_type = request.form.get('holiday_type') or 'date'
    holiday_date = (request.form.get('holiday_date') or '').strip()
    day_of_week = request.form.get('day_of_week') or None

    if not name:
        flash('Holiday name is required.', 'danger')
        return redirect(url_for('admin.holidays_index'))

    if applies_to_program not in ('UG', 'PG', 'Both'):
        flash('Invalid program selection.', 'danger')
        return redirect(url_for('admin.holidays_index'))

    is_recurring = 1 if holiday_type == 'weekly' else 0

    # Validate fields by type
    if is_recurring:
        if day_of_week not in ('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'):
            flash('Please select a valid day of week for recurring holiday.', 'danger')
            return redirect(url_for('admin.holidays_index'))
        insert_sql = (
            "INSERT INTO institution_holidays (holiday_date, day_of_week, name, applies_to_program, is_recurring)"
            " VALUES (NULL, %s, %s, %s, 1)"
        )
        params = (day_of_week, name, applies_to_program)
    else:
        if not holiday_date:
            flash('Please select a holiday date.', 'danger')
            return redirect(url_for('admin.holidays_index'))
        insert_sql = (
            "INSERT INTO institution_holidays (holiday_date, day_of_week, name, applies_to_program, is_recurring)"
            " VALUES (%s, NULL, %s, %s, 0)"
        )
        params = (holiday_date, name, applies_to_program)

    cursor = mysql.connection.cursor()
    try:
        # Avoid duplicates for weekly recurring: same day/program
        if is_recurring:
            cursor.execute(
                "SELECT id FROM institution_holidays WHERE is_recurring = 1 AND day_of_week = %s AND applies_to_program = %s",
                (day_of_week, applies_to_program),
            )
            if cursor.fetchone():
                flash('A recurring holiday for this day and program already exists.', 'warning')
                cursor.close()
                return redirect(url_for('admin.holidays_index'))

        cursor.execute(insert_sql, params)
        mysql.connection.commit()
        flash('Holiday added.', 'success')
    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f"Error adding holiday: {str(e)}")
        flash('Failed to add holiday.', 'danger')
    finally:
        cursor.close()
    return redirect(url_for('admin.holidays_index'))


@admin_bp.route('/holidays/delete/<int:holiday_id>', methods=['POST'])
@admin_required
def holidays_delete(holiday_id):
    cursor = mysql.connection.cursor()
    try:
        cursor.execute("DELETE FROM institution_holidays WHERE id = %s", (holiday_id,))
        mysql.connection.commit()
        flash('Holiday deleted.', 'success')
    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f"Error deleting holiday: {str(e)}")
        flash('Failed to delete holiday.', 'danger')
    finally:
        cursor.close()
    return redirect(url_for('admin.holidays_index'))

@admin_bp.route('/holidays/edit/<int:holiday_id>', methods=['POST'])
@admin_required
def holidays_edit(holiday_id):
    """Edit an existing holiday (name/program/type-specific fields)."""
    name = (request.form.get('name') or '').strip()
    applies_to_program = request.form.get('applies_to_program') or 'Both'
    holiday_type = request.form.get('holiday_type') or 'date'
    holiday_date = (request.form.get('holiday_date') or '').strip()
    day_of_week = request.form.get('day_of_week') or None

    if not name:
        flash('Holiday name is required.', 'danger')
        return redirect(url_for('admin.holidays_index'))

    if applies_to_program not in ('UG', 'PG', 'Both'):
        flash('Invalid program selection.', 'danger')
        return redirect(url_for('admin.holidays_index'))

    is_recurring = 1 if holiday_type == 'weekly' else 0

    cursor = mysql.connection.cursor()
    try:
        # Validate by type and build update
        if is_recurring:
            if day_of_week not in ('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'):
                flash('Please select a valid day of week for recurring holiday.', 'danger')
                cursor.close()
                return redirect(url_for('admin.holidays_index'))

            # Avoid duplicates: same day/program but different id
            cursor.execute(
                """
                SELECT id FROM institution_holidays
                WHERE is_recurring = 1 AND day_of_week = %s AND applies_to_program = %s AND id != %s
                """,
                (day_of_week, applies_to_program, holiday_id),
            )
            if cursor.fetchone():
                flash('Another recurring holiday exists for this day and program.', 'warning')
                cursor.close()
                return redirect(url_for('admin.holidays_index'))

            cursor.execute(
                """
                UPDATE institution_holidays
                SET name = %s,
                    applies_to_program = %s,
                    is_recurring = 1,
                    day_of_week = %s,
                    holiday_date = NULL
                WHERE id = %s
                """,
                (name, applies_to_program, day_of_week, holiday_id),
            )
        else:
            if not holiday_date:
                flash('Please provide a holiday date.', 'danger')
                cursor.close()
                return redirect(url_for('admin.holidays_index'))

            cursor.execute(
                """
                UPDATE institution_holidays
                SET name = %s,
                    applies_to_program = %s,
                    is_recurring = 0,
                    holiday_date = %s,
                    day_of_week = NULL
                WHERE id = %s
                """,
                (name, applies_to_program, holiday_date, holiday_id),
            )

        mysql.connection.commit()
        flash('Holiday updated.', 'success')
    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f"Error editing holiday: {str(e)}")
        flash('Failed to update holiday.', 'danger')
    finally:
        cursor.close()
    return redirect(url_for('admin.holidays_index'))
# --- Dashboard & Core ---
@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    cursor = mysql.connection.cursor()
    
    # Basic stats
    cursor.execute("SELECT COUNT(id) FROM students WHERE is_active = 1"); total_students = int(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(id) FROM faculty WHERE is_active = 1"); total_faculty = int(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(id) FROM courses WHERE is_active = 1"); total_courses = int(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(id) FROM departments WHERE is_active = 1"); total_departments = int(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(id) FROM rooms"); total_rooms = int(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(id) FROM course_batches WHERE is_active = 1"); total_batches = int(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(id) FROM subjects"); total_subjects = int(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(id) FROM faculty_allocations"); total_allocations = int(cursor.fetchone()[0])
    
    # Room breakdown
    cursor.execute("SELECT room_type, COUNT(*) FROM rooms GROUP BY room_type")
    room_breakdown = {row[0]: int(row[1]) for row in cursor.fetchall()}
    
    # Weekly schedule load (classes per day)
    cursor.execute("""
        SELECT day_of_week, COUNT(*) as class_count
        FROM timetable
        GROUP BY day_of_week
        ORDER BY FIELD(day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday')
    """)
    weekly_load = {row[0]: int(row[1]) for row in cursor.fetchall()}
    
    # Session type distribution
    cursor.execute("""
        SELECT s.theory_practical, COUNT(t.id) as count
        FROM timetable t
        JOIN subjects s ON t.subject_id = s.id
        GROUP BY s.theory_practical
    """)
    session_types = {row[0]: int(row[1]) for row in cursor.fetchall()}
    total_sessions = sum(session_types.values()) or 1
    session_percentages = {k: float(round((int(v)/total_sessions)*100, 1)) for k, v in session_types.items()}
    
    # Today's active classes
    today = datetime.now().strftime('%A')
    cursor.execute("""
        SELECT t.start_time, t.end_time, s.name as subject_name, 
               f.name as faculty_name, r.room_number,
               c.name as class_name, d.name as division_name,
               s.theory_practical
        FROM timetable t
        JOIN subjects s ON t.subject_id = s.id
        JOIN faculty f ON t.faculty_id = f.user_id
        JOIN rooms r ON t.room_id = r.id
        JOIN classes c ON t.class_id = c.id
        JOIN divisions d ON t.division_id = d.id
        WHERE t.day_of_week = %s
        ORDER BY t.start_time
        LIMIT 10
    """, (today,))
    today_classes = []
    for row in cursor.fetchall():
        today_classes.append({
            'start_time': format_time(row[0]),
            'end_time': format_time(row[1]),
            'subject_name': row[2],
            'faculty_name': row[3],
            'room_number': row[4],
            'class_name': row[5],
            'division_name': row[6],
            'type': row[7]
        })
    
    # Recent activity log
    cursor.execute("""
        SELECT ual.activity_type, ual.description, ual.created_at, u.username
        FROM user_activity_log ual
        JOIN users u ON ual.user_id = u.id
        ORDER BY ual.created_at DESC
        LIMIT 10
    """)
    recent_updates = []
    for row in cursor.fetchall():
        recent_updates.append({
            'activity': row[0],
            'description': row[1],
            'time_ago': get_time_ago(row[2]),
            'username': row[3]
        })
    
    # Faculty workload summary
    cursor.execute("""
        SELECT f.name, COUNT(t.id) as class_count, 
               SUM(TIMESTAMPDIFF(MINUTE, t.start_time, t.end_time)) as total_minutes
        FROM faculty f
        LEFT JOIN timetable t ON f.user_id = t.faculty_id
        WHERE f.is_active = 1
        GROUP BY f.id, f.name
        ORDER BY class_count DESC
        LIMIT 5
    """)
    top_faculty = []
    for row in cursor.fetchall():
        top_faculty.append({
            'name': row[0],
            'class_count': int(row[1] or 0),
            'hours': float(round((float(row[2] or 0)) / 60, 1))
        })
    
    stats = {
        'total_students': total_students,
        'total_faculty': total_faculty,
        'total_courses': total_courses,
        'total_departments': total_departments,
        'total_rooms': total_rooms,
        'total_batches': total_batches,
        'total_subjects': total_subjects,
        'total_allocations': total_allocations,
        'room_breakdown': room_breakdown,
        'weekly_load': weekly_load,
        'session_types': session_types,
        'session_percentages': session_percentages,
        'today_classes': today_classes,
        'recent_updates': recent_updates,
        'top_faculty': top_faculty,
        'today_day': today
    }
    
    # Data for modals
    cursor.execute("SELECT id, name FROM courses ORDER BY name"); courses = cursor.fetchall()
    cursor.execute("SELECT id, name FROM classes ORDER BY name"); classes = cursor.fetchall()
    cursor.execute("SELECT id, name FROM divisions ORDER BY name"); divisions = cursor.fetchall()
    cursor.execute("SELECT id, name FROM departments ORDER BY name"); departments = cursor.fetchall()

    cursor.close()
    return render_template('admin/dashboard.html', stats=stats, courses=courses, classes=classes, divisions=divisions, departments=departments)


@admin_bp.route('/generate_timetable', methods=['GET', 'POST'])
@admin_required
def generate_timetable():
    cursor = mysql.connection.cursor()
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
@admin_bp.route('/timetable', methods=['GET', 'POST'])
@admin_required
def timetable_manage():
    cursor = mysql.connection.cursor()
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
                    faculty_id = faculty_row[0]
                else:
                    raise ValueError('No faculty allocated for this subject. Please assign faculty first or select one manually.')
            # Weekly holiday check against course program
            cursor.execute("SELECT program FROM courses WHERE id = %s", (course_id,))
            row_prog = cursor.fetchone()
            program = row_prog[0] if row_prog else 'UG'
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
                    "SELECT COUNT(*) FROM faculty_availability WHERE faculty_id = %s AND day_of_week = %s",
                    (faculty_id, day),
                )
                cnt = cursor.fetchone()[0]
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
            mysql.connection.commit()
            flash('Session added to timetable.', 'success')
        except Exception as e:
            mysql.connection.rollback()
            current_app.logger.error(f"Add timetable session error: {str(e)}")
            flash(str(e) if isinstance(e, ValueError) else 'Failed to add session. Please check inputs.', 'danger')

    # Delete session via POST
    if request.method == 'POST' and request.form.get('action') == 'delete':
        try:
            tid = int(request.form.get('timetable_id'))
            cursor.execute("DELETE FROM timetable WHERE id = %s", [tid])
            mysql.connection.commit()
            flash('Session removed.', 'success')
        except Exception as e:
            mysql.connection.rollback()
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
            mysql.connection.commit()
            flash('Room assigned successfully.', 'success')
            
        except ValueError as ve:
            mysql.connection.rollback()
            flash(str(ve), 'danger')
        except Exception as e:
            mysql.connection.rollback()
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

# --- Room Management ---
@admin_bp.route('/rooms')
@admin_required
def rooms_index():
    """List rooms and show add/edit modal."""
    cursor = mysql.connection.cursor()
    
    # Get all departments for filters
    cursor.execute("SELECT id, name FROM departments ORDER BY name")
    departments = [{'id': row[0], 'name': row[1]} for row in cursor.fetchall()]
    
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
            'id': row[0],
            'room_number': row[1],
            'room_type': row[2],
            'capacity': row[3],
            'department_id': row[4],
            'department_name': row[5],
        })

    cursor.close()
    return render_template('admin/manage_rooms.html', rooms=rooms, departments=departments)


@admin_bp.route('/rooms/<int:room_id>')
@admin_required
def get_room(room_id):
    """Get room details for editing."""
    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT id, room_number, room_type, capacity, department_id
        FROM rooms WHERE id = %s
    """, (room_id,))
    row = cursor.fetchone()
    cursor.close()
    if not row:
        return jsonify({'ok': False, 'error': 'Room not found'}), 404
    return jsonify({
        'id': row[0],
        'room_number': row[1],
        'room_type': row[2],
        'capacity': row[3],
        'department_id': row[4],
    })


@admin_bp.route('/rooms', methods=['POST'])
@admin_required
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

    cursor = mysql.connection.cursor()
    try:
        cursor.execute("SELECT 1 FROM rooms WHERE room_number = %s", (room_number,))
        if cursor.fetchone():
            return jsonify({'ok': False, 'error': 'Room number already exists.'}), 400

        cursor.execute(
            "INSERT INTO rooms (room_number, room_type, capacity, department_id) VALUES (%s, %s, %s, %s)",
            (room_number, room_type, capacity, department_id)
        )
        mysql.connection.commit()
        flash('Room added successfully.', 'success')
        return jsonify({'ok': True})
    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f"Error creating room: {str(e)}")
        return jsonify({'ok': False, 'error': 'Failed to create room.'}), 500
    finally:
        cursor.close()


@admin_bp.route('/rooms/<int:room_id>', methods=['PUT'])
@admin_required
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

    cursor = mysql.connection.cursor()
    try:
        # Check if number exists but not this room
        cursor.execute("SELECT 1 FROM rooms WHERE room_number = %s AND id != %s", (room_number, room_id))
        if cursor.fetchone():
            return jsonify({'ok': False, 'error': 'Room number already exists.'}), 400

        cursor.execute(
            "UPDATE rooms SET room_number = %s, room_type = %s, capacity = %s, department_id = %s WHERE id = %s",
            (room_number, room_type, capacity, department_id, room_id)
        )
        mysql.connection.commit()
        flash('Room updated successfully.', 'success')
        return jsonify({'ok': True})
    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f"Error updating room: {str(e)}")
        return jsonify({'ok': False, 'error': 'Failed to update room.'}), 500
    finally:
        cursor.close()


@admin_bp.route('/rooms/<int:room_id>', methods=['DELETE'])
@admin_required
def delete_room(room_id):
    """Delete a room if it has no timetable entries."""
    cursor = mysql.connection.cursor()
    try:
        # Check if room is in use
        cursor.execute("SELECT 1 FROM timetable WHERE room_id = %s LIMIT 1", (room_id,))
        if cursor.fetchone():
            return jsonify({'ok': False, 'error': 'Cannot delete room: it is used in timetable entries.'}), 400

        cursor.execute("DELETE FROM rooms WHERE id = %s", (room_id,))
        mysql.connection.commit()
        flash('Room deleted successfully.', 'success')
        return jsonify({'ok': True})
    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f"Error deleting room: {str(e)}")
        return jsonify({'ok': False, 'error': 'Failed to delete room.'}), 500
    finally:
        cursor.close()


@admin_bp.route('/rooms/<int:room_id>/schedule')
@admin_required
def room_schedule(room_id):
    """Get the schedule for a specific room (all assigned slots)."""
    cursor = mysql.connection.cursor()
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
                'day': row[0],
                'start_time': format_time(row[1]),
                'end_time': format_time(row[2]),
                'subject_name': row[3],
                'class_name': row[4],
                'division_name': row[5],
                'faculty_name': row[6] or '',
            })
        return jsonify({'ok': True, 'schedule': schedule})
    except Exception as e:
        current_app.logger.error(f"Error fetching room schedule: {str(e)}")
        return jsonify({'ok': False, 'error': 'Failed to fetch schedule.'}), 500
    finally:
        cursor.close()


@admin_bp.route('/proxy_log')
@admin_required
def proxy_log():
    """Display comprehensive proxy log with faculty absence and proxy assignment details"""
    cursor = mysql.connection.cursor()
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    
    # Get filter parameters
    status_filter = request.args.get('status', '', type=str)
    approval_filter = request.args.get('approval_status', '', type=str)
    date_from = request.args.get('date_from', '', type=str)
    date_to = request.args.get('date_to', '', type=str)
    
    # Build the main query
    query = """
        SELECT 
            pl.id,
            pl.absence_date,
            pl.status,
            pl.approval_status,
            pl.approval_date,
            pl.approval_notes,
            
            -- Original faculty details
            orig_f.name AS original_faculty_name,
            orig_f.employee_id AS original_employee_id,
            
            -- Proxy faculty details (nullable)
            proxy_f.name AS proxy_faculty_name,
            proxy_f.employee_id AS proxy_employee_id,
            
            -- Timetable and subject details
            t.day_of_week,
            t.start_time,
            t.end_time,
            s.name AS subject_name,
            
            -- Class and division details
            c.name AS class_name,
            d.name AS division_name,
            
            -- Department details
            dept.name AS department_name,
            
            -- Approved by details
            approver.username AS approved_by_username
            
        FROM proxy_log pl
        JOIN timetable t ON pl.timetable_id = t.id
        JOIN faculty orig_f ON pl.original_faculty_id = orig_f.user_id
        LEFT JOIN faculty proxy_f ON pl.proxy_faculty_id = proxy_f.user_id
        JOIN subjects s ON t.subject_id = s.id
        JOIN classes c ON t.class_id = c.id
        JOIN divisions d ON t.division_id = d.id
        LEFT JOIN departments dept ON orig_f.department_id = dept.id
        LEFT JOIN users approver ON pl.approved_by = approver.id
        WHERE 1=1
    """
    
    params = []
    
    # Apply filters
    if status_filter:
        query += " AND pl.status = %s"
        params.append(status_filter)
    
    if approval_filter:
        query += " AND pl.approval_status = %s"
        params.append(approval_filter)
    
    if date_from:
        query += " AND pl.absence_date >= %s"
        params.append(date_from)
    
    if date_to:
        query += " AND pl.absence_date <= %s"
        params.append(date_to)
    
    # Get total count for pagination
    count_query = f"SELECT COUNT(*) {query[query.find('FROM'):query.rfind('ORDER BY') if 'ORDER BY' in query else len(query)]}"
    cursor.execute(count_query, params)
    total_count = cursor.fetchone()[0]
    
    # Add ordering and pagination
    query += " ORDER BY pl.absence_date DESC, t.start_time ASC"
    query += " LIMIT %s OFFSET %s"
    params.extend([per_page, offset])
    
    # Execute main query
    cursor.execute(query, params)
    proxy_logs = []
    
    for row in cursor.fetchall():
        log_entry = {
            'id': row[0],
            'absence_date': row[1],
            'status': row[2],
            'approval_status': row[3],
            'approval_date': row[4],
            'approval_notes': row[5],
            'original_faculty_name': row[6],
            'original_employee_id': row[7],
            'proxy_faculty_name': row[8],
            'proxy_employee_id': row[9],
            'day_of_week': row[10],
            'start_time': row[11],
            'end_time': row[12],
            'subject_name': row[13],
            'class_name': row[14],
            'division_name': row[15],
            'department_name': row[16],
            'approved_by_username': row[17]
        }
        proxy_logs.append(log_entry)
    
    # Get summary statistics
    cursor.execute("""
        SELECT 
            COUNT(*) as total_records,
            SUM(CASE WHEN pl.status = 'ASSIGNED' THEN 1 ELSE 0 END) as assigned_count,
            SUM(CASE WHEN pl.status = 'UNASSIGNED' THEN 1 ELSE 0 END) as unassigned_count,
            SUM(CASE WHEN pl.approval_status = 'PENDING' THEN 1 ELSE 0 END) as pending_approval,
            SUM(CASE WHEN pl.approval_status = 'APPROVED' THEN 1 ELSE 0 END) as approved_count,
            SUM(CASE WHEN pl.approval_status = 'REJECTED' THEN 1 ELSE 0 END) as rejected_count
        FROM proxy_log pl
    """)
    stats = cursor.fetchone()
    summary_stats = {
        'total_records': stats[0],
        'assigned_count': stats[1],
        'unassigned_count': stats[2],
        'pending_approval': stats[3],
        'approved_count': stats[4],
        'rejected_count': stats[5]
    }
    
    cursor.close()
    
    # Pagination info
    total_pages = math.ceil(total_count / per_page)
    has_prev = page > 1
    has_next = page < total_pages
    prev_num = page - 1 if has_prev else None
    next_num = page + 1 if has_next else None
    
    pagination = {
        'page': page,
        'per_page': per_page,
        'total': total_count,
        'total_pages': total_pages,
        'has_prev': has_prev,
        'has_next': has_next,
        'prev_num': prev_num,
        'next_num': next_num
    }
    
    return render_template('admin/proxy_log.html', 
                         proxy_logs=proxy_logs,
                         summary_stats=summary_stats,
                         pagination=pagination,
                         status_filter=status_filter,
                         approval_filter=approval_filter,
                         date_from=date_from,
                         date_to=date_to)


@admin_bp.route('/my-permissions')
@admin_required
def my_permissions():
    user_id = session.get('user_id')
    perms = get_user_permissions(user_id)
    # perms is list of tuples (name, description, module)
    perm_names = [p[0] for p in perms]
    return jsonify({'role': session.get('role'), 'permissions': perm_names})

# --- Student Management (CRUD) ---
@admin_bp.route('/manage_students')
@admin_required
def manage_students():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    course_filter = request.args.get('course_filter', '', type=str)
    per_page = 10
    offset = (page - 1) * per_page
    
    cursor = mysql.connection.cursor()
    
    query_base = "FROM students s LEFT JOIN courses c ON s.course_id = c.id LEFT JOIN classes cl ON s.class_id = cl.id LEFT JOIN divisions d ON s.division_id = d.id"
    count_query = f"SELECT COUNT(s.id) {query_base}"
    data_query = f"SELECT s.id, s.name, s.email, c.name, cl.name, d.name {query_base}"
    
    # Build WHERE clause
    where_conditions = []
    params = []
    
    if search:
        search_term = f"%{search}%"
        where_conditions.append("(s.name LIKE %s OR s.email LIKE %s OR s.admission_id LIKE %s)")
        params.extend([search_term, search_term, search_term])
    
    if course_filter:
        where_conditions.append("s.course_id = %s")
        params.append(course_filter)
    
    if where_conditions:
        where_clause = " WHERE " + " AND ".join(where_conditions)
        count_query += where_clause
        data_query += where_clause

    cursor.execute(count_query, tuple(params))
    total = cursor.fetchone()[0]
    total_pages = math.ceil(total / per_page)
    
    data_query += " ORDER BY s.name LIMIT %s OFFSET %s"
    cursor.execute(data_query, tuple(params) + (per_page, offset))
    students = cursor.fetchall()
    
    cursor.execute("SELECT id, name FROM courses ORDER BY name"); courses = cursor.fetchall()
    cursor.execute("SELECT id, name FROM classes ORDER BY display_order, name"); classes = cursor.fetchall()
    cursor.execute("SELECT id, name FROM divisions ORDER BY name"); divisions = cursor.fetchall()
    cursor.close()
    
    return render_template('admin/manage_students.html', students=students, courses=courses, classes=classes, divisions=divisions, page=page, total_pages=total_pages, search=search)

@admin_bp.route('/student/get/<int:student_id>')
@admin_required
def get_student(student_id):
    cursor = mysql.connection.cursor()
    # Join with users table to get username
    cursor.execute("""
        SELECT s.name, s.email, s.course_id, s.class_id, s.division_id, u.username
        FROM students s
        JOIN users u ON s.user_id = u.id
        WHERE s.id = %s
    """, [student_id])
    student = cursor.fetchone()
    cursor.close()
    if student:
        return jsonify({
            'name': student[0], 'email': student[1], 'course_id': student[2],
            'class_id': student[3], 'division_id': student[4], 'username': student[5]
        })
    return jsonify({'error': 'Student not found'}), 404

@admin_bp.route('/student/update/<int:student_id>', methods=['POST'])
@admin_required
def update_student(student_id):
    # Logic to update student details in DB
    flash('Student updated successfully.', 'success')
    return redirect(url_for('admin.manage_students'))
    
@admin_bp.route('/students/bulk_delete', methods=['POST'])
@admin_required
def bulk_delete_students():
    ids_to_delete = request.form.getlist('student_ids')
    if not ids_to_delete:
        flash('No students selected for deletion.', 'warning')
        return redirect(url_for('admin.manage_students'))
    
    cursor = mysql.connection.cursor()
    try:
        # Get user_ids for the students to be deleted
        format_strings = ','.join(['%s'] * len(ids_to_delete))
        cursor.execute(f"SELECT user_id FROM students WHERE id IN ({format_strings})", tuple(ids_to_delete))
        user_ids = [row[0] for row in cursor.fetchall()]
        
        # Delete students first (FK constraint)
        cursor.execute(f"DELETE FROM students WHERE id IN ({format_strings})", tuple(ids_to_delete))
        
        # Delete corresponding user accounts
        if user_ids:
            user_format_strings = ','.join(['%s'] * len(user_ids))
            cursor.execute(f"DELETE FROM users WHERE id IN ({user_format_strings})", tuple(user_ids))
        
        mysql.connection.commit()
        flash(f'{len(ids_to_delete)} students deleted successfully.', 'success')
    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f"Error deleting students: {str(e)}")
        flash('Error deleting students. Please try again.', 'danger')
    finally:
        cursor.close()
    return redirect(url_for('admin.manage_students'))


# --- Faculty Management (NEW CRUD) ---
@admin_bp.route('/manage_faculty')
@admin_required
def manage_faculty():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    department_filter = request.args.get('department_filter', '', type=str)
    
    query_base = "FROM faculty f LEFT JOIN departments d ON f.department_id = d.id"
    
    # Build WHERE clause
    where_conditions = []
    params = []
    
    if search:
        search_term = f"%{search}%"
        where_conditions.append("(f.name LIKE %s OR f.email LIKE %s OR f.employee_id LIKE %s)")
        params.extend([search_term, search_term, search_term])
    
    if department_filter:
        where_conditions.append("f.department_id = %s")
        params.append(department_filter)
    
    if where_conditions:
        query_base += " WHERE " + " AND ".join(where_conditions)

    faculty, total_pages = paginate(f"SELECT f.id, f.name, f.email, d.name {query_base}", tuple(params), page)
    
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT id, name FROM departments ORDER BY name")
    departments = cursor.fetchall()
    cursor.close()
    return render_template('admin/manage_faculty.html', faculty=faculty, departments=departments, page=page, total_pages=total_pages, search=search)

@admin_bp.route('/faculty/add', methods=['POST'])
@admin_required
def add_faculty():
    username = request.form.get('username')
    password = request.form.get('password')
    name = request.form.get('name')
    email = request.form.get('email')
    department_id = request.form.get('department_id')

    if not username or not password or not name:
        flash('Username, password, and name are required.', 'danger')
        return redirect(url_for('admin.manage_faculty'))

    cursor = mysql.connection.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE username = %s", [username])
        if cursor.fetchone():
            flash('Username already exists.', 'danger')
            return redirect(url_for('admin.manage_faculty'))

        cursor.execute("SELECT id FROM faculty WHERE email = %s", [email])
        if cursor.fetchone():
            flash('Email already registered for a faculty member.', 'danger')
            return redirect(url_for('admin.manage_faculty'))

        hashed = generate_password_hash(password)
        cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, 'Teacher')", (username, hashed))
        user_id = cursor.lastrowid
        
        # Generate unique employee_id (e.g., EMP202500001)
        from datetime import datetime
        employee_id = f"EMP{datetime.now().year}{user_id:06d}"
        
        cursor.execute(
            "INSERT INTO faculty (id, user_id, name, email, department_id, employee_id) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, user_id, name, email, department_id, employee_id)
        )
        mysql.connection.commit()
        flash('Faculty member added successfully.', 'success')
    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f"Error adding faculty: {str(e)}")
        flash('Error adding faculty. Please try again.', 'danger')
    finally:
        cursor.close()
    return redirect(url_for('admin.manage_faculty'))


@admin_bp.route('/students/add', methods=['POST'])
@admin_required
def add_student():
    # Admin endpoint to add a new student (used by Manage Students modal)
    username = request.form.get('username')
    password = request.form.get('password')
    name = request.form.get('name')
    email = request.form.get('email')
    course_id = request.form.get('course_id')
    class_id = request.form.get('class_id')
    division_id = request.form.get('division_id')

    if not username or not password or not name:
        flash('Username, password, and name are required.', 'danger')
        return redirect(url_for('admin.manage_students'))

    cursor = mysql.connection.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE username = %s", [username])
        if cursor.fetchone():
            flash('Username already exists.', 'danger')
            return redirect(url_for('admin.manage_students'))

        cursor.execute("SELECT id FROM students WHERE email = %s", [email])
        if cursor.fetchone():
            flash('Email already registered for a student.', 'danger')
            return redirect(url_for('admin.manage_students'))

        hashed = generate_password_hash(password)
        cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, 'Student')", (username, hashed))
        user_id = cursor.lastrowid
        
        # Generate unique admission_id (e.g., ADM202500001)
        from datetime import datetime
        admission_id = f"ADM{datetime.now().year}{user_id:06d}"
        
        cursor.execute(
            "INSERT INTO students (id, user_id, name, email, course_id, class_id, division_id, admission_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (user_id, user_id, name, email, course_id, class_id, division_id, admission_id)
        )
        mysql.connection.commit()
        flash('Student added successfully.', 'success')
    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f"Error adding student: {str(e)}")
        flash('Error adding student. Please try again.', 'danger')
    finally:
        cursor.close()
    return redirect(url_for('admin.manage_students'))

@admin_bp.route('/students/bulk-invite', methods=['GET', 'POST'])
@admin_required
def bulk_invite_students():
    """Bulk student invitation via CSV/Excel upload or form"""
    if request.method == 'POST':
        import pandas as pd
        import io
        from werkzeug.security import generate_password_hash
        
        success_count = 0
        error_count = 0
        errors = []
        
        cursor = mysql.connection.cursor()
        try:
            # Check if file was uploaded
            if 'file' in request.files and request.files['file'].filename:
                file = request.files['file']
                filename = file.filename.lower()
                
                # Read file based on extension
                if filename.endswith('.csv'):
                    df = pd.read_csv(io.StringIO(file.stream.read().decode('utf-8')))
                elif filename.endswith(('.xlsx', '.xls')):
                    df = pd.read_excel(file)
                else:
                    flash('Invalid file format. Please upload CSV or Excel file.', 'danger')
                    return redirect(url_for('admin.bulk_invite_students'))
                
                # Expected columns: name, email, username, course_id (required)
                required_cols = ['name', 'email', 'username', 'course_id']
                if not all(col in df.columns for col in required_cols):
                    flash(f'CSV must contain columns: {", ".join(required_cols)}', 'danger')
                    return redirect(url_for('admin.bulk_invite_students'))
                
                # Generate default password or use column if provided
                default_password = request.form.get('default_password', 'Student@123')
                
                for idx, row in df.iterrows():
                    try:
                        name = str(row['name']).strip()
                        email = str(row['email']).strip()
                        username = str(row['username']).strip()
                        
                        # course_id is required (NOT NULL in database)
                        course_id = int(row['course_id']) if pd.notna(row.get('course_id')) else None
                        if not course_id:
                            errors.append(f"Row {idx+2}: course_id is required")
                            error_count += 1
                            continue
                        
                        # Optional fields
                        class_id = int(row['class_id']) if pd.notna(row.get('class_id')) else None
                        division_id = int(row['division_id']) if pd.notna(row.get('division_id')) else None
                        password = row.get('password', default_password) if pd.notna(row.get('password')) else default_password
                        
                        # Check if username exists
                        cursor.execute("SELECT id FROM users WHERE username = %s", [username])
                        if cursor.fetchone():
                            errors.append(f"Row {idx+2}: Username '{username}' already exists")
                            error_count += 1
                            continue
                        
                        # Check if email exists
                        cursor.execute("SELECT id FROM students WHERE email = %s", [email])
                        if cursor.fetchone():
                            errors.append(f"Row {idx+2}: Email '{email}' already registered")
                            error_count += 1
                            continue
                        
                        # Create user account
                        hashed = generate_password_hash(password)
                        cursor.execute(
                            "INSERT INTO users (username, password, role, email, status) VALUES (%s, %s, 'Student', %s, 'active')",
                            (username, hashed, email)
                        )
                        user_id = cursor.lastrowid
                        
                        # Generate unique admission_id
                        from datetime import datetime
                        admission_id = f"ADM{datetime.now().year}{user_id:06d}"
                        
                        # Create student record (id must match user_id)
                        cursor.execute(
                            "INSERT INTO students (id, user_id, name, email, course_id, class_id, division_id, admission_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                            (user_id, user_id, name, email, course_id, class_id, division_id, admission_id)
                        )
                        
                        success_count += 1
                        
                    except Exception as e:
                        errors.append(f"Row {idx+2}: {str(e)}")
                        error_count += 1
                        continue
                
                mysql.connection.commit()
                
            else:
                # Form-based bulk invitation (manual entry)
                students_data = request.form.get('students_data', '')
                default_password = request.form.get('default_password', 'Student@123')
                default_course = request.form.get('default_course_id')
                default_class = request.form.get('default_class_id')
                default_division = request.form.get('default_division_id')
                
                if not students_data:
                    flash('Please provide student data', 'warning')
                    return redirect(url_for('admin.bulk_invite_students'))
                
                if not default_course:
                    flash('Please select a default course (course_id is required)', 'danger')
                    return redirect(url_for('admin.bulk_invite_students'))
                
                # Parse students data (format: name, email, username per line)
                lines = students_data.strip().split('\n')
                for idx, line in enumerate(lines):
                    if not line.strip():
                        continue
                    
                    try:
                        parts = [p.strip() for p in line.split(',')]
                        if len(parts) < 3:
                            errors.append(f"Line {idx+1}: Invalid format. Expected: name, email, username")
                            error_count += 1
                            continue
                        
                        name, email, username = parts[0], parts[1], parts[2]
                        
                        # Check username
                        cursor.execute("SELECT id FROM users WHERE username = %s", [username])
                        if cursor.fetchone():
                            errors.append(f"Line {idx+1}: Username '{username}' already exists")
                            error_count += 1
                            continue
                        
                        # Check email
                        cursor.execute("SELECT id FROM students WHERE email = %s", [email])
                        if cursor.fetchone():
                            errors.append(f"Line {idx+1}: Email '{email}' already registered")
                            error_count += 1
                            continue
                        
                        # Create user
                        hashed = generate_password_hash(default_password)
                        cursor.execute(
                            "INSERT INTO users (username, password, role, email, status) VALUES (%s, %s, 'Student', %s, 'active')",
                            (username, hashed, email)
                        )
                        user_id = cursor.lastrowid
                        
                        # Generate unique admission_id
                        from datetime import datetime
                        admission_id = f"ADM{datetime.now().year}{user_id:06d}"
                        
                        # Create student (id must match user_id)
                        cursor.execute(
                            "INSERT INTO students (id, user_id, name, email, course_id, class_id, division_id, admission_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                            (user_id, user_id, name, email, default_course, default_class, default_division, admission_id)
                        )
                        
                        success_count += 1
                        
                    except Exception as e:
                        errors.append(f"Line {idx+1}: {str(e)}")
                        error_count += 1
                        continue
                
                mysql.connection.commit()
            
            # Show results
            if success_count > 0:
                flash(f'Successfully invited {success_count} student(s)', 'success')
            if error_count > 0:
                flash(f'{error_count} error(s) occurred. Check details below.', 'warning')
                for error in errors[:10]:  # Show first 10 errors
                    flash(error, 'danger')
            
            return redirect(url_for('admin.manage_students'))
            
        except Exception as e:
            mysql.connection.rollback()
            current_app.logger.error(f"Bulk invitation error: {str(e)}")
            flash(f'Error processing bulk invitation: {str(e)}', 'danger')
        finally:
            cursor.close()
    
    # GET request - show form
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT id, name FROM courses ORDER BY name")
    courses = cursor.fetchall()
    cursor.execute("SELECT id, name FROM classes ORDER BY display_order, name")
    classes = cursor.fetchall()
    cursor.execute("SELECT id, name FROM divisions ORDER BY name")
    divisions = cursor.fetchall()
    cursor.close()
    
    return render_template('admin/bulk_invite_students.html', 
                         courses=courses, classes=classes, divisions=divisions)

@admin_bp.route('/faculty/get/<int:faculty_id>')
@admin_required
def get_faculty(faculty_id):
    cursor = mysql.connection.cursor()
    # Without user_id FK, we can't join to users table
    cursor.execute("SELECT f.name, f.email, f.department_id FROM faculty f WHERE f.id = %s", [faculty_id])
    faculty_member = cursor.fetchone()
    cursor.close()
    if faculty_member:
        return jsonify({'name': faculty_member[0], 'email': faculty_member[1], 'department_id': faculty_member[2], 'username': ''})
    return jsonify({'error': 'Faculty not found'}), 404

@admin_bp.route('/faculty/update/<int:faculty_id>', methods=['POST'])
@admin_required
def update_faculty(faculty_id):
    name, email, department_id, password = request.form.get('name'), request.form.get('email'), request.form.get('department_id'), request.form.get('password')
    cursor = mysql.connection.cursor()
    cursor.execute("UPDATE faculty SET name=%s, email=%s, department_id=%s WHERE id=%s", (name, email, department_id, faculty_id))
    # Without user_id FK, we can't update user password from here
    # Password update would need separate logic to find the user account
    mysql.connection.commit()
    cursor.close()
    flash('Faculty member updated successfully.', 'success')
    return redirect(url_for('admin.manage_faculty'))

@admin_bp.route('/faculty/bulk_delete', methods=['POST'])
@admin_required
def bulk_delete_faculty():
    ids_to_delete = request.form.getlist('faculty_ids')
    if ids_to_delete:
        cursor = mysql.connection.cursor()
        format_strings = ','.join(['%s'] * len(ids_to_delete))
        # Without user_id FK, just delete faculty records
        cursor.execute(f"DELETE FROM faculty WHERE id IN ({format_strings})", tuple(ids_to_delete))
        mysql.connection.commit()
        flash(f'{len(ids_to_delete)} faculty members deleted.', 'success')
        cursor.close()
    return redirect(url_for('admin.manage_faculty'))

# --- Academic Management (Redirected to separate module) ---
@admin_bp.route('/manage_academics')
@admin_required
def manage_academics():
    """Redirect to new academic management module"""
    return redirect(url_for('academic.manage_academics'))

# --- Basic Department/Course/Subject Management (kept for backward compatibility) ---
@admin_bp.route('/department/add', methods=['POST'])
@admin_required
def add_department():
    name = request.form.get('name')
    cursor = mysql.connection.cursor()
    cursor.execute("INSERT INTO departments (name) VALUES (%s)", [name])
    mysql.connection.commit()
    cursor.close()
    flash('Department added successfully.', 'success')
    return redirect(url_for('academic.manage_academics'))

@admin_bp.route('/department/update/<int:dept_id>', methods=['POST'])
@admin_required
def update_department(dept_id):
    name = request.form.get('name')
    cursor = mysql.connection.cursor()
    cursor.execute("UPDATE departments SET name = %s WHERE id = %s", (name, dept_id))
    mysql.connection.commit()
    cursor.close()
    flash('Department updated successfully.', 'success')
    return redirect(url_for('academic.manage_academics'))

@admin_bp.route('/department/delete/<int:dept_id>', methods=['POST'])
@admin_required
def delete_department(dept_id):
    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM departments WHERE id = %s", [dept_id])
    mysql.connection.commit()
    cursor.close()
    flash('Department deleted successfully. Associated courses and subjects were also removed.', 'success')
    return redirect(url_for('academic.manage_academics'))

# --- Course CRUD ---
@admin_bp.route('/course/add', methods=['POST'])
@admin_required
def add_course():
    name, program, dept_id = request.form.get('name'), request.form.get('program'), request.form.get('department_id')
    cursor = mysql.connection.cursor()
    cursor.execute("INSERT INTO courses (name, program, department_id) VALUES (%s, %s, %s)", (name, program, dept_id))
    mysql.connection.commit()
    cursor.close()
    flash('Course added successfully.', 'success')
    return redirect(url_for('academic.manage_academics'))

@admin_bp.route('/course/delete/<int:course_id>', methods=['POST'])
@admin_required
def delete_course(course_id):
    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM courses WHERE id = %s", [course_id])
    mysql.connection.commit()
    cursor.close()
    flash('Course deleted successfully.', 'success')
    return redirect(url_for('academic.manage_academics'))

# --- Subject CRUD (Basic) ---
@admin_bp.route('/subject/add', methods=['POST'])
@admin_required
def add_subject():
    name, course_id, class_id = request.form.get('name'), request.form.get('course_id'), request.form.get('class_id')
    cursor = mysql.connection.cursor()
    cursor.execute("INSERT INTO subjects (name, course_id, class_id) VALUES (%s, %s, %s)", (name, course_id, class_id))
    mysql.connection.commit()
    cursor.close()
    flash('Subject added successfully.', 'success')
    return redirect(url_for('academic.manage_academics'))

@admin_bp.route('/subject/delete/<int:subject_id>', methods=['POST'])
@admin_required
def delete_subject(subject_id):
    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM subjects WHERE id = %s", [subject_id])
    mysql.connection.commit()
    cursor.close()
    flash('Subject deleted successfully.', 'success')
    return redirect(url_for('academic.manage_academics'))

# --- Allocation CRUD ---
@admin_bp.route('/allocation/add', methods=['POST'])
@admin_required
def add_allocation():
    faculty_id, subject_id, class_id, division_id = request.form.values()
    cursor = mysql.connection.cursor()
    cursor.execute("INSERT INTO faculty_allocations (faculty_id, subject_id, class_id, division_id) VALUES (%s, %s, %s, %s)", (faculty_id, subject_id, class_id, division_id))
    mysql.connection.commit()
    cursor.close()
    flash('Faculty allocation saved successfully.', 'success')
    return redirect(url_for('academic.manage_academics'))

@admin_bp.route('/allocation/delete/<int:alloc_id>', methods=['POST'])
@admin_required
def delete_allocation(alloc_id):
    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM faculty_allocations WHERE id = %s", [alloc_id])
    mysql.connection.commit()
    cursor.close()
    flash('Allocation removed successfully.', 'success')
    return redirect(url_for('academic.manage_academics'))


# --- Enhanced API endpoints for AJAX ---
@admin_bp.route('/api/classes')
@admin_required
def api_classes():
    course_id = request.args.get('course_id')
    cursor = mysql.connection.cursor()
    rows = []
    # If course_id provided, try to filter by that; otherwise return all classes.
    if course_id:
        try:
            cid = int(course_id)
            try:
                cursor.execute("SELECT id, name FROM classes WHERE course_id = %s ORDER BY name", [cid])
                rows = cursor.fetchall()
            except Exception:
                # Fallback when classes.course_id column doesn't exist
                cursor.execute("SELECT id, name FROM classes ORDER BY name")
                rows = cursor.fetchall()
        except ValueError:
            cursor.execute("SELECT id, name FROM classes ORDER BY name")
            rows = cursor.fetchall()
    else:
        cursor.execute("SELECT id, name FROM classes ORDER BY name")
        rows = cursor.fetchall()
    cursor.close()
    items = [{'id': r[0], 'name': r[1]} for r in rows]
    return jsonify(items)

@admin_bp.route('/api/divisions')
@admin_required
def api_divisions():
    class_id = request.args.get('class_id')
    cursor = mysql.connection.cursor()
    rows = []
    # If class_id provided, try to filter; if column doesn't exist, or no class_id provided, return all
    if class_id:
        try:
            clid = int(class_id)
            try:
                cursor.execute("SELECT id, name FROM divisions WHERE class_id = %s ORDER BY name", [clid])
                rows = cursor.fetchall()
            except Exception:
                cursor.execute("SELECT id, name FROM divisions ORDER BY name")
                rows = cursor.fetchall()
        except ValueError:
            cursor.execute("SELECT id, name FROM divisions ORDER BY name")
            rows = cursor.fetchall()
    else:
        cursor.execute("SELECT id, name FROM divisions ORDER BY name")
        rows = cursor.fetchall()
    cursor.close()
    items = [{'id': r[0], 'name': r[1]} for r in rows]
    return jsonify(items)


@admin_bp.route('/api/faculty-by-subject')
@admin_required
def api_faculty_by_subject():
    """Get all faculty teaching a specific subject"""
    subject_id = request.args.get('subject_id')
    if not subject_id:
        return jsonify({'error': 'subject_id query parameter required'}), 400
    try:
        sid = int(subject_id)
    except ValueError:
        return jsonify({'error': 'invalid subject_id'}), 400
    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT DISTINCT f.id, f.name, f.email
        FROM faculty f
        JOIN faculty_allocations fa ON f.id = fa.faculty_id
        WHERE fa.subject_id = %s
        ORDER BY f.name
    """, [sid])
    rows = cursor.fetchall()
    cursor.close()
    items = [{'id': r[0], 'name': r[1], 'email': r[2]} for r in rows]
    return jsonify(items)

## Legacy preview removed in favor of unified generator-based preview (see api_generate_preview)


@admin_bp.route('/api/generate_preview', methods=['POST'])
@admin_required
def api_generate_preview():
    """Enhanced preview that uses the same generator in preview-only mode with form parameters."""
    data = request.get_json(silent=True) or request.form
    course_id = data.get('course')
    class_id = data.get('class')
    division_id = data.get('division')
    week_start_date = data.get('week_start_date') or None
    day_start = data.get('day_start') or '09:00'
    day_end = data.get('day_end') or '15:00'
    lecture_minutes = data.get('lecture_minutes') or 45
    break_start = data.get('break_start') or None
    break_duration = data.get('break_duration') or 0
    working_days = data.get('working_days') or data.getlist('working_days') if hasattr(data, 'getlist') else None
    if isinstance(working_days, str):
        try:
            # allow comma-separated
            working_days = [d.strip() for d in working_days.split(',') if d.strip()]
        except Exception:
            working_days = None

    result = generate_timetable_for_class(
        course_id,
        class_id,
        division_id,
        week_start_date=week_start_date,
        day_start=day_start,
        day_end=day_end,
        lecture_minutes=lecture_minutes,
        break_start=break_start,
        break_duration=break_duration,
        working_days=working_days,
        preview_only=True,
    )

    status = result.get('status')
    if status in ('error',):
        return jsonify(result), 400
    return jsonify(result)


@admin_bp.route('/api/eligible_subjects', methods=['GET'])
@admin_required
def api_eligible_subjects():
    """Return eligible subjects for a given course/class/division and which have matching allocations.
    Also returns course subjects that are missing allocations for the selected class/division.
    """
    course_id = request.args.get('course_id')
    class_id = request.args.get('class_id')
    division_id = request.args.get('division_id')

    if not course_id or not class_id or not division_id:
        return jsonify({
            'status': 'error',
            'message': 'course_id, class_id and division_id are required'
        }), 400

    cursor = mysql.connection.cursor(DictCursor)
    try:
        # Eligible subjects (at least one allocation that matches class/division)
        cursor.execute(
            """
            SELECT DISTINCT
                s.id,
                s.name,
                s.course_code,
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
        eligible_rows = cursor.fetchall()

        eligible_subject_ids = [r['id'] for r in eligible_rows]

        faculty_map = {sid: [] for sid in eligible_subject_ids}
        if eligible_subject_ids:
            placeholder = ','.join(['%s'] * len(eligible_subject_ids))
            cursor.execute(
                f"""
                SELECT fa.subject_id, f.name AS faculty_name, COALESCE(fa.is_primary, 1) AS is_primary
                FROM faculty_allocations fa
                JOIN faculty f ON f.user_id = fa.faculty_id
                WHERE fa.subject_id IN ({placeholder})
                  AND (fa.class_id IS NULL OR fa.class_id = %s)
                  AND (fa.division_id IS NULL OR fa.division_id = %s)
                ORDER BY fa.subject_id, is_primary DESC, f.name
                """,
                (*eligible_subject_ids, class_id, division_id),
            )
            for row in cursor.fetchall():
                faculty_map[row['subject_id']].append({
                    'name': row['faculty_name'],
                    'is_primary': bool(row['is_primary']),
                })

        eligible = []
        for r in eligible_rows:
            eligible.append({
                'id': r['id'],
                'name': r['name'],
                'course_code': r['course_code'],
                'theory_practical': r['theory_practical'],
                'lectures_per_week': int(r['lectures_per_week'] or 0),
                'practical_hours_per_week': float(r['practical_hours_per_week'] or 0),
                'faculty': faculty_map.get(r['id'], []),
            })

        # Subjects in this course that are not eligible for this class/division (missing allocation)
        cursor.execute(
            """
            SELECT s.id, s.name, s.course_code
            FROM subjects s
            WHERE s.course_id = %s
              AND (s.class_id IS NULL OR s.class_id = %s)
            ORDER BY s.name
            """,
            (course_id, class_id),
        )
        all_course_subjects = cursor.fetchall()
        missing = [
            {'id': r['id'], 'name': r['name'], 'course_code': r['course_code']}
            for r in all_course_subjects if r['id'] not in eligible_subject_ids
        ]

        return jsonify({
            'status': 'ok',
            'eligible': eligible,
            'missing': missing,
        })
    finally:
        cursor.close()


@admin_bp.route('/rooms/utilization.csv', methods=['GET'])
@admin_required
def rooms_utilization_csv():
    """Export room utilization across the timetable as a CSV.
    Columns: Room, Day, Start, End, Course, Class, Division, Subject, Faculty
    """
    cursor = mysql.connection.cursor()
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


@admin_bp.route('/api/coverage.csv', methods=['GET'])
@admin_required
def coverage_csv():
    """Export coverage for the selected Course/Class/Division.
    Computes required total slots per subject (lectures_per_week + practical hours converted to slots)
    and compares with scheduled count in timetable for that class/division.
    """
    course_id = request.args.get('course_id') or request.args.get('course')
    class_id = request.args.get('class_id') or request.args.get('class')
    division_id = request.args.get('division_id') or request.args.get('division')
    # Default lecture duration for conversion when not otherwise specified
    try:
        lecture_minutes = int(request.args.get('lecture_minutes', 45))
    except Exception:
        lecture_minutes = 45

    if not course_id or not class_id or not division_id:
        return jsonify({'status': 'error', 'message': 'course_id, class_id, division_id are required'}), 400

    cursor = mysql.connection.cursor(DictCursor)
    try:
        # Subjects applicable to this course/class
        cursor.execute(
            """
            SELECT s.id, s.name, COALESCE(s.lectures_per_week,0) AS lpw, COALESCE(s.practical_hours_per_week,0) AS phw
            FROM subjects s
            WHERE s.course_id = %s AND (s.class_id IS NULL OR s.class_id = %s)
            ORDER BY s.name
            """,
            (course_id, class_id),
        )
        subjects = cursor.fetchall()
        subject_ids = [s['id'] for s in subjects]

        scheduled_counts = {}
        if subject_ids:
            placeholder = ','.join(['%s'] * len(subject_ids))
            cursor.execute(
                f"""
                SELECT subject_id, COUNT(*) AS cnt
                FROM timetable
                WHERE course_id = %s AND class_id = %s AND division_id = %s AND subject_id IN ({placeholder})
                GROUP BY subject_id
                """,
                (int(course_id), int(class_id), int(division_id), *subject_ids),
            )
            for row in cursor.fetchall():
                scheduled_counts[int(row['subject_id'])] = int(row['cnt'])
    finally:
        cursor.close()

    import io, csv, math as _math
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Subject', 'Required Slots (est.)', 'Scheduled Slots'])

    for s in subjects:
        lpw = int(s['lpw'] or 0)
        ph_minutes = float(s['phw'] or 0.0) * 60.0
        practical_slots = int(_math.ceil(ph_minutes / max(1, lecture_minutes))) if ph_minutes > 0 else 0
        required_total = lpw + practical_slots
        scheduled = scheduled_counts.get(s['id'], 0)
        writer.writerow([s['name'], required_total, scheduled])

    resp = make_response(output.getvalue())
    resp.headers['Content-Disposition'] = 'attachment; filename=coverage_class_{0}_{1}_{2}.csv'.format(course_id, class_id, division_id)
    resp.headers['Content-Type'] = 'text/csv'
    return resp


# --- Registration Invitation Management ---
@admin_bp.route('/manage_invitations')
@admin_required
def manage_invitations():
    """List and manage registration invitations"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    status_filter = request.args.get('status', '', type=str)
    per_page = 15
    
    # Create form for CSRF protection
    form = InvitationForm()
    
    cursor = mysql.connection.cursor()
    
    query_base = """
        FROM registration_invitations ri
        LEFT JOIN courses c ON ri.course_id = c.id
        LEFT JOIN departments d ON ri.department_id = d.id
        LEFT JOIN users u ON ri.created_by = u.id
    """
    
    conditions = []
    params = []
    
    if search:
        conditions.append("(ri.email LIKE %s OR ri.name LIKE %s)")
        search_term = f"%{search}%"
        params.extend([search_term, search_term])
    
    if status_filter and status_filter in ['pending', 'used', 'expired']:
        conditions.append("ri.status = %s")
        params.append(status_filter)
    
    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    
    count_query = f"SELECT COUNT(ri.id) {query_base}{where_clause}"
    cursor.execute(count_query, tuple(params))
    total = cursor.fetchone()[0]
    total_pages = math.ceil(total / per_page)
    
    offset = (page - 1) * per_page
    data_query = f"""
        SELECT ri.id, ri.token, ri.email, ri.name, ri.role, ri.status,
               ri.created_at, ri.expires_at, ri.used_at,
               c.name as course_name, d.name as dept_name, u.username as created_by_username
        {query_base}{where_clause}
        ORDER BY ri.created_at DESC
        LIMIT %s OFFSET %s
    """
    cursor.execute(data_query, tuple(params) + (per_page, offset))
    invitations = cursor.fetchall()
    
    # Fetch dropdown data for creating new invitations
    cursor.execute("SELECT id, name FROM courses ORDER BY name")
    courses = cursor.fetchall()
    cursor.execute("SELECT id, name FROM classes ORDER BY name")
    classes = cursor.fetchall()
    cursor.execute("SELECT id, name FROM divisions ORDER BY name")
    divisions = cursor.fetchall()
    cursor.execute("SELECT id, name FROM departments ORDER BY name")
    departments = cursor.fetchall()
    
    # Calculate statistics
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN status = 'pending' AND expires_at > NOW() THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN status = 'used' THEN 1 ELSE 0 END) as used,
            SUM(CASE WHEN status = 'expired' OR (status = 'pending' AND expires_at <= NOW()) THEN 1 ELSE 0 END) as expired,
            COUNT(*) as total
        FROM registration_invitations
    """)
    stats_row = cursor.fetchone()
    stats = {
        'pending': stats_row[0] or 0,
        'used': stats_row[1] or 0,
        'expired': stats_row[2] or 0,
        'total': stats_row[3] or 0
    }
    
    cursor.close()
    
    return render_template('admin/manage_invitations.html',
                         form=form,
                         invitations=invitations,
                         courses=courses,
                         classes=classes,
                         divisions=divisions,
                         departments=departments,
                         stats=stats,
                         page=page,
                         total_pages=total_pages,
                         search=search,
                         status_filter=status_filter)


@admin_bp.route('/invitation/create', methods=['POST'])
@admin_required
def create_invitation():
    """Generate a new registration invitation"""
    email = request.form.get('email')
    name = request.form.get('name')
    role = request.form.get('role')
    days_valid = int(request.form.get('days_valid', 7))
    
    if not email or not name or not role:
        flash('Email, name, and role are required.', 'danger')
        return redirect(url_for('admin.manage_invitations'))
    
    cursor = mysql.connection.cursor()
    
    # Check if email already has a pending invitation
    cursor.execute("""
        SELECT id FROM registration_invitations 
        WHERE email = %s AND status = 'pending' AND expires_at > NOW()
    """, (email,))
    if cursor.fetchone():
        flash('A pending invitation already exists for this email.', 'warning')
        cursor.close()
        return redirect(url_for('admin.manage_invitations'))
    
    # Check if email already registered
    if role == 'Student':
        cursor.execute("SELECT id FROM students WHERE email = %s", (email,))
    else:
        cursor.execute("SELECT id FROM faculty WHERE email = %s", (email,))
    
    if cursor.fetchone():
        flash('This email is already registered in the system.', 'warning')
        cursor.close()
        return redirect(url_for('admin.manage_invitations'))
    
    # Generate secure token
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=days_valid)
    
    # Get role-specific data
    course_id = request.form.get('course_id') if role == 'Student' else None
    class_id = request.form.get('class_id') if role == 'Student' else None
    division_id = request.form.get('division_id') if role == 'Student' else None
    department_id = request.form.get('department_id') if role == 'Teacher' else None
    
    try:
        cursor.execute("""
            INSERT INTO registration_invitations 
            (token, email, name, role, course_id, class_id, division_id, department_id, created_by, expires_at, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
        """, (token, email, name, role, course_id, class_id, division_id, department_id, session['user_id'], expires_at))
        mysql.connection.commit()
        
        # Generate registration link
        registration_url = url_for('auth.register', token=token, _external=True)
        flash(f'Invitation created! Registration link: {registration_url}', 'success')
        
    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f"Error creating invitation: {str(e)}")
        flash('Error creating invitation. Please try again.', 'danger')
    
    cursor.close()
    return redirect(url_for('admin.manage_invitations'))


@admin_bp.route('/invitation/revoke/<int:invitation_id>', methods=['POST'])
@admin_required
def revoke_invitation(invitation_id):
    """Revoke/expire an invitation"""
    cursor = mysql.connection.cursor()
    cursor.execute("""
        UPDATE registration_invitations 
        SET status = 'expired' 
        WHERE id = %s AND status = 'pending'
    """, (invitation_id,))
    mysql.connection.commit()
    cursor.close()
    flash('Invitation revoked successfully.', 'success')
    return redirect(url_for('admin.manage_invitations'))


@admin_bp.route('/invitation/resend/<int:invitation_id>', methods=['POST'])
@admin_required
def resend_invitation(invitation_id):
    """Regenerate token and extend expiry for an invitation"""
    cursor = mysql.connection.cursor()
    
    # Get invitation details
    cursor.execute("SELECT email, status FROM registration_invitations WHERE id = %s", (invitation_id,))
    invitation = cursor.fetchone()
    
    if not invitation:
        flash('Invitation not found.', 'danger')
        cursor.close()
        return redirect(url_for('admin.manage_invitations'))
    
    if invitation[1] == 'used':
        flash('Cannot resend a used invitation.', 'warning')
        cursor.close()
        return redirect(url_for('admin.manage_invitations'))
    
    # Generate new token and extend expiry
    new_token = secrets.token_urlsafe(32)
    new_expires_at = datetime.now() + timedelta(days=7)
    
    cursor.execute("""
        UPDATE registration_invitations 
        SET token = %s, expires_at = %s, status = 'pending' 
        WHERE id = %s
    """, (new_token, new_expires_at, invitation_id))
    mysql.connection.commit()
    
    registration_url = url_for('auth.register', token=new_token, _external=True)
    flash(f'Invitation regenerated! New link: {registration_url}', 'success')
    
    cursor.close()
    return redirect(url_for('admin.manage_invitations'))


@admin_bp.route('/invitation/copy_link/<int:invitation_id>')
@admin_required
def copy_invitation_link(invitation_id):
    """Get invitation link for copying"""
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT token FROM registration_invitations WHERE id = %s", (invitation_id,))
    result = cursor.fetchone()
    cursor.close()
    
    if result:
        token = result[0]
        registration_url = url_for('auth.register', token=token, _external=True)
        return jsonify({'url': registration_url})
    
    return jsonify({'error': 'Invitation not found'}), 404