from flask import session, request, redirect, url_for, flash, render_template
from database import get_db_connection
from .teacher import teacher_bp, teacher_required, format_time

# --- Availability ---
@teacher_bp.route('/availability', methods=['GET', 'POST'])
@teacher_required
def availability():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    faculty_id = session.get('faculty_id')
    
    # Get user_id for this faculty (faculty_availability uses user_id as faculty_id)
    cursor.execute("SELECT user_id FROM faculty WHERE id = %s", (faculty_id,))
    faculty_record = cursor.fetchone()
    if not faculty_record:
        flash("Faculty profile not found. Please contact administrator.", "danger")
        return redirect(url_for('teacher.dashboard'))
    
    faculty_user_id = faculty_record['user_id']
    
    if request.method == 'POST':
        try:
            # Delete existing availability (using user_id)
            cursor.execute("DELETE FROM faculty_availability WHERE faculty_id = %s", [faculty_user_id])
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
                        
                        if not start_time or not end_time:
                            break
                        
                        # Store each time slot (using user_id)
                        cursor.execute(
                            """
                            INSERT INTO faculty_availability 
                            (faculty_id, day_of_week, is_available, start_time, end_time, notes)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (faculty_user_id, day_num, 1, start_time, end_time, notes),
                        )
                        slot_index += 1
                    
                    # If no slots were added, add a default unavailable entry (using user_id)
                    if slot_index == 0:
                        cursor.execute(
                            """
                            INSERT INTO faculty_availability 
                            (faculty_id, day_of_week, is_available, start_time, end_time, notes)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (faculty_user_id, day_num, 0, None, None, ''),
                        )
                else:
                    # Mark as unavailable (using user_id)
                    cursor.execute(
                        """
                        INSERT INTO faculty_availability 
                        (faculty_id, day_of_week, is_available, start_time, end_time, notes)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (faculty_user_id, day_num, 0, None, None, ''),
                    )
            
            connection.commit()
            cursor.close()
            connection.close()
            flash('Availability updated successfully.', 'success')
            return redirect(url_for('teacher.availability'))
        except Exception as e:
            connection.rollback()
            cursor.close()
            connection.close()
            flash(f'Error updating availability: {str(e)}', 'danger')
            return redirect(url_for('teacher.availability'))

    # GET - Fetch ALL availability slots with shift patterns (using user_id)
    cursor.execute("""
        SELECT fa.day_of_week, fa.is_available, fa.start_time, fa.end_time, fa.notes,
               fa.shift_pattern_id, sp.shift_name, sp.shift_code,
               sp.start_time as shift_start, sp.end_time as shift_end
        FROM faculty_availability fa
        LEFT JOIN shift_patterns sp ON fa.shift_pattern_id = sp.id
        WHERE fa.faculty_id = %s
        ORDER BY fa.day_of_week, fa.start_time
    """, [faculty_user_id])
    
    # Map day numbers to names
    day_names = {1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday', 5: 'Friday', 6: 'Saturday'}
    
    # Collect ALL slots per day (not just first)
    avail_all_slots = {day: [] for day in day_names.values()}
    for row in cursor.fetchall():
        day_name = day_names.get(row['day_of_week'])
        if day_name:
            slot_data = {
                'is_available': bool(row['is_available']),
                'start_time': format_time(row['start_time']) if row['start_time'] else None,
                'end_time': format_time(row['end_time']) if row['end_time'] else None,
                'notes': row['notes'] or '',
                'shift_pattern_id': row['shift_pattern_id'],
                'shift_name': row['shift_name'],
                'shift_code': row['shift_code'],
                'shift_start': format_time(row['shift_start']) if row['shift_start'] else None,
                'shift_end': format_time(row['shift_end']) if row['shift_end'] else None
            }
            avail_all_slots[day_name].append(slot_data)
    
    cursor.close()
    return render_template('teacher/availability.html', avail_all_slots=avail_all_slots)

