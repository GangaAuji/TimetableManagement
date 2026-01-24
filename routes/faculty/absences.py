from flask import session, request, jsonify, redirect, url_for, flash
from database import get_db_connection
from datetime import datetime, date
from .teacher import teacher_bp, teacher_required

# --- Absences JSON (AJAX) ---
@teacher_bp.route('/absences', methods=['GET', 'POST'])
@teacher_required
def absences():
    faculty_id = session.get('faculty_id')
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)

    if request.method == 'GET':
        cursor.execute(
            "SELECT id, absence_date, reason, status FROM faculty_absences WHERE faculty_id = %s ORDER BY absence_date DESC",
            [faculty_id],
        )
        items = [
            {
                'id': row['id'],
                'absence_date': row['absence_date'].strftime('%Y-%m-%d') if isinstance(row['absence_date'], (datetime, date)) else str(row['absence_date']),
                'reason': row['reason'],
                'status': row['status'],
            }
            for row in cursor.fetchall()
        ]
        cursor.close()
        return jsonify({'data': items})

    # POST create
    data = request.get_json(silent=True) or {}
    absence_date_str = data.get('absence_date') or request.form.get('absence_date')
    reason = data.get('reason') or request.form.get('reason')
    if not absence_date_str:
        cursor.close()
        return jsonify({'ok': False, 'error': 'absence_date required'}), 400
    ad = datetime.strptime(absence_date_str, '%Y-%m-%d').date()
    cursor.execute(
        "INSERT INTO faculty_absences (faculty_id, absence_date, reason, status) VALUES (%s, %s, %s, 'UNPROCESSED')",
        (faculty_id, ad, reason),
    )
    connection.commit()
    cursor.close()
    return jsonify({'ok': True})


@teacher_bp.route('/absences/<int:absence_id>', methods=['DELETE'])
@teacher_required
def delete_absence(absence_id):
    faculty_id = session.get('faculty_id')
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    # Only allow deleting UNPROCESSED ones owned by this faculty
    cursor.execute(
        "SELECT status FROM faculty_absences WHERE id = %s AND faculty_id = %s",
        (absence_id, faculty_id),
    )
    row = cursor.fetchone()
    if not row:
        cursor.close()
        return jsonify({'ok': False, 'error': 'Not found'}), 404
    if row['status'] != 'UNPROCESSED':
        cursor.close()
        return jsonify({'ok': False, 'error': 'Cannot delete processed absence'}), 400
    cursor.execute("DELETE FROM faculty_absences WHERE id = %s AND faculty_id = %s", (absence_id, faculty_id))
    connection.commit()
    cursor.close()
    return jsonify({'ok': True})



@teacher_bp.route('/mark_absence', methods=['POST'])
@teacher_required
def mark_absence():
    absence_date_str = request.form.get('absence_date')
    if not absence_date_str:
        flash("Absence date is required.", "danger")
        return redirect(url_for('teacher.dashboard'))

    connection = get_db_connection()


    cursor = connection.cursor(dictionary=True)
    faculty_id = session.get('faculty_id')
    if not faculty_id:
        flash("Faculty profile not found.", "danger")
        return redirect(url_for('auth.logout'))

    absence_date = datetime.strptime(absence_date_str, '%Y-%m-%d').date()
    cursor.execute(
        "INSERT INTO faculty_absences (faculty_id, absence_date, reason, status) VALUES (%s, %s, %s, 'UNPROCESSED')",
        (faculty_id, absence_date, request.form.get('reason')),
    )
    connection.commit()
    cursor.close()
    flash("Absence request submitted for approval.", "success")
    return redirect(url_for('teacher.dashboard'))

