"""
Faculty Shift Management Routes
Manages faculty work shifts and availability patterns for timetable generation
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from security import has_permission
import mysql.connector
from config import Config

shift_bp = Blueprint('shifts', __name__, url_prefix='/admin/shifts')

def get_db_connection():
    """Get database connection"""
    return mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB
    )

# ============================================================================
# SHIFT PATTERNS MANAGEMENT
# ============================================================================

@shift_bp.route('/')
@has_permission('shifts_view')
def manage_shifts():
    """Display Shift Management Dashboard"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get all shift patterns
        cursor.execute("""
            SELECT sp.*, 
                   COUNT(DISTINCT fa.faculty_id) as faculty_count
            FROM shift_patterns sp
            LEFT JOIN faculty_availability fa ON sp.id = fa.shift_pattern_id
            GROUP BY sp.id
            ORDER BY sp.shift_order
        """)
        shift_patterns = cursor.fetchall()
        
        # Get statistics
        cursor.execute("SELECT COUNT(*) as count FROM shift_patterns WHERE is_active = TRUE")
        active_shifts_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(DISTINCT faculty_id) as count FROM faculty_availability")
        faculty_with_shifts_count = cursor.fetchone()['count']
        
        return render_template('admin/manage_shifts.html',
                             shift_patterns=shift_patterns,
                             active_shifts_count=active_shifts_count,
                             faculty_with_shifts_count=faculty_with_shifts_count)
    
    finally:
        cursor.close()
        connection.close()

@shift_bp.route('/add', methods=['POST'])
@has_permission('shifts_add')
def add_shift():
    """Add new shift pattern"""
    shift_name = request.form.get('shift_name')
    shift_code = request.form.get('shift_code')
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    shift_order = request.form.get('shift_order', 1)
    description = request.form.get('description', '')
    is_active = 1 if request.form.get('is_active') else 0
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO shift_patterns 
            (shift_name, shift_code, start_time, end_time, shift_order, description, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (shift_name, shift_code, start_time, end_time, shift_order, description, is_active))
        
        connection.commit()
        flash(f'Shift pattern "{shift_name}" added successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error adding shift pattern: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('shifts.manage_shifts'))

@shift_bp.route('/edit/<int:id>', methods=['POST'])
@has_permission('shifts_change')
def edit_shift(id):
    """Edit shift pattern"""
    shift_name = request.form.get('shift_name')
    shift_code = request.form.get('shift_code')
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    shift_order = request.form.get('shift_order')
    description = request.form.get('description', '')
    is_active = 1 if request.form.get('is_active') else 0
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        cursor.execute("""
            UPDATE shift_patterns 
            SET shift_name = %s, shift_code = %s, start_time = %s, end_time = %s,
                shift_order = %s, description = %s, is_active = %s
            WHERE id = %s
        """, (shift_name, shift_code, start_time, end_time, shift_order, description, is_active, id))
        
        connection.commit()
        flash(f'Shift pattern "{shift_name}" updated successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error updating shift pattern: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('shifts.manage_shifts'))

@shift_bp.route('/delete/<int:id>', methods=['POST'])
@has_permission('shifts_delete')
def delete_shift(id):
    """Delete shift pattern"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Check if shift is being used
        cursor.execute("""
            SELECT COUNT(*) as count FROM faculty_availability 
            WHERE shift_pattern_id = %s
        """, (id,))
        usage_count = cursor.fetchone()['count']
        
        if usage_count > 0:
            flash(f'Cannot delete shift pattern: it is assigned to {usage_count} faculty member(s)', 'danger')
        else:
            cursor.execute("DELETE FROM shift_patterns WHERE id = %s", (id,))
            connection.commit()
            flash('Shift pattern deleted successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error deleting shift pattern: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('shifts.manage_shifts'))

# ============================================================================
# FACULTY AVAILABILITY MANAGEMENT
# ============================================================================

@shift_bp.route('/faculty-availability')
@has_permission('shifts_view')
def faculty_availability():
    """Manage faculty availability and shift assignments"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get all faculty with their department info
        cursor.execute("""
            SELECT f.id, f.user_id, f.name, f.email, f.department_id, d.name as department_name
            FROM faculty f
            LEFT JOIN departments d ON f.department_id = d.id
            WHERE f.is_active = TRUE
            ORDER BY d.name, f.name
        """)
        faculty_list = cursor.fetchall()
        
        # Get all faculty availability records (including custom time slots)
        cursor.execute("""
            SELECT fa.faculty_id, fa.day_of_week, fa.is_available,
                   fa.shift_pattern_id, fa.start_time, fa.end_time, fa.notes,
                   sp.shift_code, sp.shift_name, sp.start_time as shift_start, sp.end_time as shift_end
            FROM faculty_availability fa
            LEFT JOIN shift_patterns sp ON fa.shift_pattern_id = sp.id
        """)
        availability_records = cursor.fetchall()
        
        # Helper function to format timedelta to HH:MM string
        def format_time_td(td):
            if td is None:
                return None
            if isinstance(td, str):
                return td[:5]  # Already a string
            # Convert timedelta to HH:MM
            total_seconds = int(td.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours:02d}:{minutes:02d}"
        
        # Build availability map: faculty_id -> {day_of_week -> [availability_data]}
        # Group by faculty_id and day, keeping ALL slots (not just one per day)
        availability_map = {}
        for record in availability_records:
            faculty_id = record['faculty_id']
            day = record['day_of_week']
            
            if faculty_id not in availability_map:
                availability_map[faculty_id] = {}
            
            if day not in availability_map[faculty_id]:
                availability_map[faculty_id][day] = []
            
            # Determine display info: prefer shift pattern, fallback to custom times
            if record['shift_pattern_id']:
                display_text = record['shift_code']
                shift_start_str = format_time_td(record['shift_start'])
                shift_end_str = format_time_td(record['shift_end'])
                time_range = f"{shift_start_str} - {shift_end_str}" if shift_start_str else ''
            elif record['start_time'] and record['end_time']:
                start_str = format_time_td(record['start_time'])
                end_str = format_time_td(record['end_time'])
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
        
        # Build final faculty list with availability (use first slot for summary)
        faculty_with_availability = []
        for faculty in faculty_list:
            user_availability = availability_map.get(faculty['user_id'], {})
            # For template compatibility, provide first slot per day
            day_summary = {}
            for day, slots in user_availability.items():
                if slots:
                    day_summary[day] = slots[0]  # Show first slot in dropdown
                    day_summary[day]['all_slots'] = slots  # Keep all slots for tooltip
            
            faculty_with_availability.append({
                'faculty': faculty,
                'availability': day_summary
            })
        
        # Get active shift patterns
        cursor.execute("""
            SELECT id, shift_name, shift_code, start_time, end_time, 
                   shift_order, description, is_active
            FROM shift_patterns 
            WHERE is_active = TRUE 
            ORDER BY shift_order
        """)
        shift_patterns = cursor.fetchall()
        
        # Get departments for filter
        cursor.execute("SELECT id, name FROM departments WHERE is_active = TRUE ORDER BY name")
        departments = cursor.fetchall()
        
        return render_template('admin/faculty_availability.html',
                             faculty_list=faculty_with_availability,
                             shift_patterns=shift_patterns,
                             departments=departments)
    
    finally:
        cursor.close()
        connection.close()

@shift_bp.route('/set-availability', methods=['POST'])
@has_permission('shifts_change')
def set_faculty_availability():
    """Set or update faculty availability for a specific day"""
    data = request.get_json()
    faculty_user_id = data.get('faculty_id')  # Template sends user_id (faculty_availability uses user_id)
    day_of_week = data.get('day_of_week')  # 1=Monday, 7=Sunday
    is_available = 1 if data.get('is_available') else 0
    shift_pattern_id = data.get('shift_pattern_id') if 'shift_pattern_id' in data else None
    notes = data.get('notes', '')
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Check if availability record exists (faculty_availability.faculty_id stores user_id)
        cursor.execute("""
            SELECT id, shift_pattern_id, notes FROM faculty_availability 
            WHERE faculty_id = %s AND day_of_week = %s
        """, (faculty_user_id, day_of_week))
        
        existing = cursor.fetchone()
        
        if existing:
            # Update existing record - preserve shift_pattern_id if not provided
            update_shift_id = shift_pattern_id if 'shift_pattern_id' in data else existing['shift_pattern_id']
            update_notes = notes if notes else existing['notes']
            
            cursor.execute("""
                UPDATE faculty_availability 
                SET is_available = %s, shift_pattern_id = %s, notes = %s
                WHERE id = %s
            """, (is_available, update_shift_id, update_notes, existing['id']))
        else:
            # Insert new record
            cursor.execute("""
                INSERT INTO faculty_availability 
                (faculty_id, day_of_week, is_available, shift_pattern_id, notes)
                VALUES (%s, %s, %s, %s, %s)
            """, (faculty_user_id, day_of_week, is_available, shift_pattern_id, notes))
        
        connection.commit()
        
        return jsonify({
            'success': True,
            'message': 'Availability updated successfully'
        })
    
    except Exception as e:
        connection.rollback()
        return jsonify({
            'success': False,
            'message': f'Error updating availability: {str(e)}'
        }), 500
    
    finally:
        cursor.close()
        connection.close()

@shift_bp.route('/bulk-set-availability', methods=['POST'])
@has_permission('shifts_change')
def bulk_set_availability():
    """Set availability for multiple faculty and days at once"""
    faculty_user_ids = request.form.getlist('faculty_ids')  # List of user_ids (faculty_availability uses user_id)
    shift_pattern_id = request.form.get('shift_pattern_id') or None
    days = request.form.getlist('days')  # List of day numbers
    is_available = 1 if request.form.get('is_available') else 0
    notes = request.form.get('notes', '')
    
    if not faculty_user_ids or not days:
        flash('Please select at least one faculty member and one day.', 'warning')
        return redirect(url_for('shifts.faculty_availability'))
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        updated_count = 0
        for faculty_user_id in faculty_user_ids:
            for day in days:
                # Check if exists (faculty_availability.faculty_id stores user_id)
                cursor.execute("""
                    SELECT id FROM faculty_availability 
                    WHERE faculty_id = %s AND day_of_week = %s
                """, (faculty_user_id, day))
                
                existing = cursor.fetchone()
                
                if existing:
                    cursor.execute("""
                        UPDATE faculty_availability 
                        SET is_available = %s, shift_pattern_id = %s, notes = %s
                        WHERE id = %s
                    """, (is_available, shift_pattern_id, notes, existing[0]))
                else:
                    cursor.execute("""
                        INSERT INTO faculty_availability 
                        (faculty_id, day_of_week, is_available, shift_pattern_id, notes)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (faculty_user_id, day, is_available, shift_pattern_id, notes))
                updated_count += 1
        
        connection.commit()
        flash(f'Bulk availability updated successfully! ({updated_count} assignments)', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error updating bulk availability: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('shifts.faculty_availability'))

# ============================================================================
# API ENDPOINTS
# ============================================================================

@shift_bp.route('/api/faculty/<int:faculty_user_id>/availability')
@has_permission('shifts_view')
def get_faculty_availability_api(faculty_user_id):
    """Get faculty availability for timetable generation (uses user_id)"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Query faculty_availability using user_id (faculty_availability.faculty_id stores user_id)
        cursor.execute("""
            SELECT fa.day_of_week, fa.is_available, 
                   sp.start_time, sp.end_time, sp.shift_name
            FROM faculty_availability fa
            LEFT JOIN shift_patterns sp ON fa.shift_pattern_id = sp.id
            WHERE fa.faculty_id = %s AND fa.is_available = TRUE
            ORDER BY fa.day_of_week
        """, (faculty_user_id,))
        
        availability = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'availability': availability
        })
    
    finally:
        cursor.close()
        connection.close()

@shift_bp.route('/api/shift-patterns')
@has_permission('shifts_view')
def get_shift_patterns_api():
    """Get all active shift patterns"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT id, shift_name, shift_code, start_time, end_time, 
                   shift_order, is_active
            FROM shift_patterns 
            WHERE is_active = TRUE
            ORDER BY shift_order
        """)
        patterns = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'patterns': patterns
        })
    
    finally:
        cursor.close()
        connection.close()

# ============================================================================
# SHIFT CHANGE REQUESTS MANAGEMENT
# ============================================================================

@shift_bp.route('/change-requests')
@has_permission('shifts_view')
def view_change_requests():
    """View all shift change requests from faculty"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get all shift change requests with faculty details
        cursor.execute("""
            SELECT scr.id, scr.faculty_id, scr.day_of_week, 
                   scr.current_shift_name, scr.requested_shift_name,
                   scr.reason, scr.status, scr.admin_response,
                   scr.created_at, scr.reviewed_at,
                   f.name as faculty_name, d.name as department_name,
                   u.username as reviewed_by_name
            FROM shift_change_requests scr
            JOIN faculty f ON scr.faculty_id = f.user_id
            LEFT JOIN departments d ON f.department_id = d.id
            LEFT JOIN users u ON scr.reviewed_by = u.id
            ORDER BY 
                CASE scr.status 
                    WHEN 'pending' THEN 1 
                    WHEN 'approved' THEN 2 
                    ELSE 3 
                END,
                scr.created_at DESC
        """)
        requests = cursor.fetchall()
        
        # Count by status
        pending_count = sum(1 for r in requests if r['status'] == 'pending')
        
        return render_template('admin/shift_change_requests.html',
                             requests=requests,
                             pending_count=pending_count)
    
    finally:
        cursor.close()
        connection.close()

@shift_bp.route('/change-requests/<int:request_id>/respond', methods=['POST'])
@has_permission('shifts_change')
def respond_to_change_request(request_id):
    """Approve or reject a shift change request"""
    action = request.form.get('action')  # 'approve' or 'reject'
    admin_response = request.form.get('admin_response', '')
    
    if action not in ['approve', 'reject']:
        flash('Invalid action.', 'danger')
        return redirect(url_for('shifts.view_change_requests'))
    
    status = 'approved' if action == 'approve' else 'rejected'
    user_id = session.get('user_id')
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get request details
        cursor.execute("""
            SELECT faculty_id, day_of_week, requested_shift_name
            FROM shift_change_requests
            WHERE id = %s
        """, (request_id,))
        req = cursor.fetchone()
        
        if not req:
            flash('Request not found.', 'danger')
            return redirect(url_for('shifts.view_change_requests'))
        
        # Update request status
        cursor.execute("""
            UPDATE shift_change_requests
            SET status = %s, admin_response = %s, 
                reviewed_by = %s, reviewed_at = NOW()
            WHERE id = %s
        """, (status, admin_response, user_id, request_id))
        
        # If approved, update faculty availability
        if action == 'approve':
            # Get shift pattern by name (approximate match)
            cursor.execute("""
                SELECT id FROM shift_patterns 
                WHERE shift_name LIKE %s OR shift_code LIKE %s
                LIMIT 1
            """, (f"%{req['requested_shift_name']}%", f"%{req['requested_shift_name']}%"))
            
            shift = cursor.fetchone()
            shift_id = shift['id'] if shift else None
            
            # Update or insert faculty availability
            cursor.execute("""
                INSERT INTO faculty_availability 
                (faculty_id, day_of_week, is_available, shift_pattern_id, notes)
                VALUES (%s, %s, 1, %s, 'Approved shift change request')
                ON DUPLICATE KEY UPDATE
                    shift_pattern_id = VALUES(shift_pattern_id),
                    is_available = 1,
                    notes = 'Approved shift change request'
            """, (req['faculty_id'], req['day_of_week'], shift_id))
        
        connection.commit()
        flash(f'Request {status} successfully!', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error processing request: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('shifts.view_change_requests'))
