"""
Admin Attendance Management Module
Handles attendance overview, reports, and management for administrators.
"""

from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for, make_response
from database import get_db_connection
from security import has_permission
from datetime import datetime, timedelta
from decimal import Decimal
import csv
import io

attendance_admin_bp = Blueprint('attendance_admin', __name__, url_prefix='/admin/attendance')


def _table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT 1
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        LIMIT 1
        """,
        (table_name,),
    )
    return cursor.fetchone() is not None


def _decimal_to_number(value):
    if isinstance(value, Decimal):
        return int(value) if value == int(value) else float(value)
    return value


def _promote_log_to_attendance(cursor, log_row):
    cursor.execute(
        """
        INSERT INTO attendance (student_id, timetable_id, attendance_date, status, marked_by, remarks)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            status = VALUES(status),
            marked_by = VALUES(marked_by),
            remarks = VALUES(remarks),
            marked_at = NOW(),
            updated_at = NOW()
        """,
        (
            log_row["student_id"],
            log_row["timetable_id"],
            log_row["attendance_date"],
            log_row["status"],
            log_row["marked_by_faculty_id"],
            log_row.get("remarks"),
        ),
    )


def _promote_log_to_faculty_attendance(cursor, log_row):
    cursor.execute(
        """
        INSERT INTO faculty_attendance (
            faculty_id,
            faculty_user_id,
            attendance_date,
            day_of_week,
            shift_key,
            shift_pattern_id,
            shift_name,
            shift_code,
            shift_start_time,
            shift_end_time,
            status,
            marked_by_user_id,
            source,
            captured_at,
            confidence,
            remarks
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'mobile_face', %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            status = VALUES(status),
            marked_by_user_id = VALUES(marked_by_user_id),
            captured_at = VALUES(captured_at),
            confidence = VALUES(confidence),
            remarks = VALUES(remarks),
            source = VALUES(source),
            marked_at = NOW(),
            updated_at = NOW()
        """,
        (
            log_row["faculty_id"],
            log_row["faculty_user_id"],
            log_row["attendance_date"],
            log_row["day_of_week"],
            log_row["shift_key"],
            log_row.get("shift_pattern_id"),
            log_row.get("shift_name"),
            log_row.get("shift_code"),
            log_row.get("shift_start_time"),
            log_row.get("shift_end_time"),
            log_row["status"],
            log_row["marked_by_user_id"],
            log_row.get("captured_at"),
            log_row.get("confidence"),
            log_row.get("remarks"),
        ),
    )


@attendance_admin_bp.route('/')
@has_permission('attendance_view')
def attendance_overview():
    """
    Main attendance dashboard showing overall statistics and recent activity.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get overall statistics
        cursor.execute("""
            SELECT 
                COUNT(DISTINCT student_id) as total_students,
                COUNT(*) as total_records,
                SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) as total_present,
                SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END) as total_late,
                SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) as total_absent,
                ROUND(
                    (SUM(CASE WHEN status IN ('Present', 'Late') THEN 1 ELSE 0 END) / COUNT(*)) * 100, 
                    2
                ) as overall_percentage
            FROM attendance
            WHERE attendance_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        """)
        overall_stats = cursor.fetchone()
        
        # Convert Decimal to float
        if overall_stats:
            overall_stats['total_students'] = int(overall_stats['total_students'] or 0)
            overall_stats['total_records'] = int(overall_stats['total_records'] or 0)
            overall_stats['total_present'] = int(overall_stats['total_present'] or 0)
            overall_stats['total_late'] = int(overall_stats['total_late'] or 0)
            overall_stats['total_absent'] = int(overall_stats['total_absent'] or 0)
            overall_stats['overall_percentage'] = float(overall_stats['overall_percentage'] or 0)
        
        # Get today's attendance summary by class
        cursor.execute("""
            SELECT 
                c.name as course_name,
                cl.name as class_name,
                d.name as division_name,
                COUNT(DISTINCT a.student_id) as students_marked,
                SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present_count,
                SUM(CASE WHEN a.status = 'Late' THEN 1 ELSE 0 END) as late_count,
                SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent_count
            FROM attendance a
            JOIN timetable t ON a.timetable_id = t.id
            JOIN courses c ON t.course_id = c.id
            JOIN classes cl ON t.class_id = cl.id
            JOIN divisions d ON t.division_id = d.id
            WHERE a.attendance_date = CURDATE()
            GROUP BY c.id, cl.id, d.id
            ORDER BY c.name, cl.name, d.name
        """)
        today_by_class = cursor.fetchall()
        
        # Convert to int
        for record in today_by_class:
            record['students_marked'] = int(record['students_marked'] or 0)
            record['present_count'] = int(record['present_count'] or 0)
            record['late_count'] = int(record['late_count'] or 0)
            record['absent_count'] = int(record['absent_count'] or 0)
        
        # Build scalable filters + pagination for recent attendance activity.
        page = request.args.get('page', 1, type=int) or 1
        page = max(page, 1)

        per_page = request.args.get('per_page', 20, type=int) or 20
        if per_page not in (20, 50, 100):
            per_page = 20

        status_filter = (request.args.get('status') or '').strip()
        if status_filter not in ('Present', 'Late', 'Absent'):
            status_filter = ''

        search_query = (request.args.get('q') or '').strip()
        date_from = (request.args.get('date_from') or '').strip()
        date_to = (request.args.get('date_to') or '').strip()

        if date_from:
            try:
                datetime.strptime(date_from, '%Y-%m-%d')
            except ValueError:
                date_from = ''

        if date_to:
            try:
                datetime.strptime(date_to, '%Y-%m-%d')
            except ValueError:
                date_to = ''

        where_clauses = []
        where_params = []

        if status_filter:
            where_clauses.append('a.status = %s')
            where_params.append(status_filter)

        if date_from:
            where_clauses.append('a.attendance_date >= %s')
            where_params.append(date_from)

        if date_to:
            where_clauses.append('a.attendance_date <= %s')
            where_params.append(date_to)

        if search_query:
            like_query = f"%{search_query}%"
            where_clauses.append(
                """
                (
                    st.name LIKE %s
                    OR st.roll_number LIKE %s
                    OR s.name LIKE %s
                    OR c.name LIKE %s
                    OR cl.name LIKE %s
                    OR d.name LIKE %s
                )
                """
            )
            where_params.extend([like_query] * 6)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ''

        cursor.execute(
            f"""
            SELECT COUNT(*) AS total_count
            FROM attendance a
            JOIN students st ON a.student_id = st.id
            JOIN timetable t ON a.timetable_id = t.id
            JOIN subjects s ON t.subject_id = s.id
            JOIN courses c ON t.course_id = c.id
            JOIN classes cl ON t.class_id = cl.id
            JOIN divisions d ON t.division_id = d.id
            {where_sql}
            """,
            tuple(where_params),
        )
        total_count_row = cursor.fetchone() or {}
        total_count = int(total_count_row.get('total_count') or 0)

        total_pages = max((total_count + per_page - 1) // per_page, 1)
        if page > total_pages:
            page = total_pages

        offset = (page - 1) * per_page

        cursor.execute(
            f"""
            SELECT 
                a.attendance_date,
                a.status,
                st.name as student_name,
                st.roll_number,
                s.name as subject_name,
                COALESCE(f.name, 'Unknown') as marked_by,
                a.marked_at,
                CONCAT(c.name, ' - ', cl.name, ' ', d.name) as class_info
            FROM attendance a
            JOIN students st ON a.student_id = st.id
            JOIN timetable t ON a.timetable_id = t.id
            JOIN subjects s ON t.subject_id = s.id
            LEFT JOIN faculty f ON a.marked_by = f.id
            JOIN courses c ON t.course_id = c.id
            JOIN classes cl ON t.class_id = cl.id
            JOIN divisions d ON t.division_id = d.id
            {where_sql}
            ORDER BY a.marked_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple([*where_params, per_page, offset]),
        )
        recent_activity = cursor.fetchall()
        
        # Format dates
        for record in recent_activity:
            if isinstance(record['attendance_date'], datetime):
                record['attendance_date'] = record['attendance_date'].strftime('%d %b %Y')
            elif isinstance(record['attendance_date'], str):
                pass  # Already string
            else:
                record['attendance_date'] = str(record['attendance_date'])
                
            if isinstance(record['marked_at'], datetime):
                record['marked_at'] = record['marked_at'].strftime('%d %b %Y %I:%M %p')
            elif record['marked_at']:
                record['marked_at'] = str(record['marked_at'])
        
        # Get defaulter count (students below 75%)
        cursor.execute("""
            SELECT COUNT(*) as defaulter_count
            FROM student_overall_attendance
            WHERE overall_percentage < 75
        """)
        defaulter_stats = cursor.fetchone()
        defaulter_count = int(defaulter_stats['defaulter_count'] or 0) if defaulter_stats else 0
        
        recent_activity_filters = {
            'status': status_filter,
            'q': search_query,
            'date_from': date_from,
            'date_to': date_to,
            'per_page': per_page,
        }

        recent_activity_pagination = {
            'page': page,
            'per_page': per_page,
            'total_count': total_count,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'start_index': (offset + 1) if total_count > 0 else 0,
            'end_index': min(offset + len(recent_activity), total_count),
        }

        return render_template('admin/attendance/overview.html',
                             overall_stats=overall_stats,
                             today_by_class=today_by_class,
                             recent_activity=recent_activity,
                             defaulter_count=defaulter_count,
                             recent_activity_filters=recent_activity_filters,
                             recent_activity_pagination=recent_activity_pagination)
    
    except Exception as e:
        print(f"Error in attendance overview: {e}")
        import traceback
        traceback.print_exc()
        flash("An error occurred while loading attendance data.", "danger")
        return render_template('admin/attendance/overview.html',
                             overall_stats=None,
                             today_by_class=[],
                             recent_activity=[],
                             defaulter_count=0,
                             recent_activity_filters={
                                 'status': '',
                                 'q': '',
                                 'date_from': '',
                                 'date_to': '',
                                 'per_page': 20,
                             },
                             recent_activity_pagination={
                                 'page': 1,
                                 'per_page': 20,
                                 'total_count': 0,
                                 'total_pages': 1,
                                 'has_prev': False,
                                 'has_next': False,
                                 'start_index': 0,
                                 'end_index': 0,
                             })
    finally:
        cursor.close()
        connection.close()


@attendance_admin_bp.route('/defaulters')
@has_permission('attendance_view_defaulters')
def attendance_defaulters():
    """
    Show students with attendance below threshold (default 75%).
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        threshold = request.args.get('threshold', 75, type=float)
        
        cursor.execute("""
            SELECT 
                st.id as student_id,
                st.name as student_name,
                st.roll_number,
                st.email,
                st.phone,
                CONCAT(c.name, ' - ', cl.name, ' ', d.name) as class_info,
                soa.total_lectures,
                soa.total_present,
                soa.total_late,
                soa.total_absent,
                soa.overall_percentage
            FROM student_overall_attendance soa
            JOIN students st ON soa.student_id = st.id
            JOIN courses c ON st.course_id = c.id
            JOIN classes cl ON st.class_id = cl.id
            JOIN divisions d ON st.division_id = d.id
            WHERE soa.overall_percentage < %s
            ORDER BY soa.overall_percentage ASC, st.roll_number
        """, [threshold])
        
        defaulters = cursor.fetchall()
        
        for record in defaulters:
            record['total_lectures'] = int(record['total_lectures'] or 0)
            record['total_present'] = int(record['total_present'] or 0)
            record['total_late'] = int(record['total_late'] or 0)
            record['total_absent'] = int(record['total_absent'] or 0)
            record['overall_percentage'] = float(record['overall_percentage'] or 0)
        
        return render_template('admin/attendance/defaulters.html',
                             defaulters=defaulters,
                             threshold=threshold)
    
    except Exception as e:
        print(f"Error fetching defaulters: {e}")
        import traceback
        traceback.print_exc()
        flash("An error occurred while loading defaulter list.", "danger")
        return redirect(url_for('attendance_admin.attendance_overview'))
    finally:
        cursor.close()
        connection.close()


@attendance_admin_bp.route('/student/<int:student_id>')
@has_permission('attendance_view_details')
def student_attendance_details(student_id):
    """
    Detailed attendance view for a specific student.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get student info
        cursor.execute("""
            SELECT 
                st.name, st.roll_number, st.email, st.phone,
                CONCAT(c.name, ' - ', cl.name, ' ', d.name) as class_info
            FROM students st
            JOIN courses c ON st.course_id = c.id
            JOIN classes cl ON st.class_id = cl.id
            JOIN divisions d ON st.division_id = d.id
            WHERE st.id = %s
        """, [student_id])
        
        student = cursor.fetchone()
        
        if not student:
            flash("Student not found.", "danger")
            return redirect(url_for('attendance_admin.attendance_overview'))
        
        # Get overall stats
        cursor.execute("""
            SELECT 
                total_lectures, total_present, total_late, total_absent, overall_percentage
            FROM student_overall_attendance
            WHERE student_id = %s
        """, [student_id])
        
        overall_stats = cursor.fetchone()
        if overall_stats:
            overall_stats['total_lectures'] = int(overall_stats['total_lectures'] or 0)
            overall_stats['total_present'] = int(overall_stats['total_present'] or 0)
            overall_stats['total_late'] = int(overall_stats['total_late'] or 0)
            overall_stats['total_absent'] = int(overall_stats['total_absent'] or 0)
            overall_stats['overall_percentage'] = float(overall_stats['overall_percentage'] or 0)
        
        # Get subject-wise stats
        cursor.execute("""
            SELECT 
                subject_name,
                total_lectures_scheduled,
                lectures_attended,
                lectures_late,
                lectures_missed,
                attendance_percentage
            FROM attendance_summary
            WHERE student_id = %s
            ORDER BY subject_name
        """, [student_id])
        
        subject_wise = cursor.fetchall()
        for record in subject_wise:
            record['total_lectures_scheduled'] = int(record['total_lectures_scheduled'] or 0)
            record['lectures_attended'] = int(record['lectures_attended'] or 0)
            record['lectures_late'] = int(record['lectures_late'] or 0)
            record['lectures_missed'] = int(record['lectures_missed'] or 0)
            record['attendance_percentage'] = float(record['attendance_percentage'] or 0)
        
        return render_template('admin/attendance/student_details.html',
                             student=student,
                             overall_stats=overall_stats,
                             subject_wise=subject_wise)
    
    except Exception as e:
        print(f"Error fetching student attendance: {e}")
        import traceback
        traceback.print_exc()
        flash("An error occurred while loading student details.", "danger")
        return redirect(url_for('attendance_admin.attendance_overview'))
    finally:
        cursor.close()
        connection.close()


@attendance_admin_bp.route('/faculty')
@has_permission('attendance_view_faculty')
def faculty_attendance_overview():
    """Faculty attendance dashboard (shift-based)."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        if not _table_exists(cursor, 'faculty_attendance'):
            flash(
                "faculty_attendance table not found. Run add_mobile_faculty_attendance_sync.sql migration first.",
                "warning",
            )
            return render_template(
                'admin/attendance/faculty_overview.html',
                overall_stats={
                    'total_faculty': 0,
                    'total_records': 0,
                    'total_present': 0,
                    'total_late': 0,
                    'total_absent': 0,
                    'overall_percentage': 0.0,
                },
                today_by_shift=[],
                recent_activity=[],
                faculty_summary=[],
                recent_activity_filters={
                    'q': '',
                    'status': '',
                    'date_from': '',
                    'date_to': '',
                    'per_page': 20,
                },
                recent_activity_pagination={
                    'page': 1,
                    'per_page': 20,
                    'total_count': 0,
                    'total_pages': 1,
                    'has_prev': False,
                    'has_next': False,
                    'start_index': 0,
                    'end_index': 0,
                },
            )

        # Recent activity filters + pagination for high-volume attendance logs.
        ra_page = request.args.get('ra_page', 1, type=int) or 1
        ra_page = max(ra_page, 1)

        ra_per_page = request.args.get('ra_per_page', 20, type=int) or 20
        if ra_per_page not in (20, 50, 100):
            ra_per_page = 20

        ra_status = (request.args.get('ra_status') or '').strip()
        if ra_status not in ('Present', 'Late', 'Absent'):
            ra_status = ''

        ra_query = (request.args.get('ra_q') or '').strip()
        ra_date_from = (request.args.get('ra_date_from') or '').strip()
        ra_date_to = (request.args.get('ra_date_to') or '').strip()

        if ra_date_from:
            try:
                datetime.strptime(ra_date_from, '%Y-%m-%d')
            except ValueError:
                ra_date_from = ''

        if ra_date_to:
            try:
                datetime.strptime(ra_date_to, '%Y-%m-%d')
            except ValueError:
                ra_date_to = ''

        ra_where_clauses = ['1=1']
        ra_params = []

        if ra_status:
            ra_where_clauses.append('fa.status = %s')
            ra_params.append(ra_status)

        if ra_date_from:
            ra_where_clauses.append('fa.attendance_date >= %s')
            ra_params.append(ra_date_from)

        if ra_date_to:
            ra_where_clauses.append('fa.attendance_date <= %s')
            ra_params.append(ra_date_to)

        if ra_query:
            like_query = f'%{ra_query}%'
            ra_where_clauses.append(
                """
                (
                    f.name LIKE %s
                    OR f.employee_id LIKE %s
                    OR d.name LIKE %s
                    OR COALESCE(u.username, '') LIKE %s
                    OR COALESCE(fa.shift_name, '') LIKE %s
                    OR COALESCE(fa.shift_code, '') LIKE %s
                )
                """
            )
            ra_params.extend([like_query, like_query, like_query, like_query, like_query, like_query])

        ra_where_sql = ' AND '.join(ra_where_clauses)

        cursor.execute(
            """
            SELECT
                COUNT(DISTINCT faculty_id) AS total_faculty,
                COUNT(*) AS total_records,
                SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS total_present,
                SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END) AS total_late,
                SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) AS total_absent,
                ROUND(
                    (
                        SUM(CASE WHEN status IN ('Present', 'Late') THEN 1 ELSE 0 END)
                        / NULLIF(COUNT(*), 0)
                    ) * 100,
                    2
                ) AS overall_percentage
            FROM faculty_attendance
            WHERE attendance_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            """
        )
        overall_stats = cursor.fetchone() or {}
        overall_stats = {
            'total_faculty': int(overall_stats.get('total_faculty') or 0),
            'total_records': int(overall_stats.get('total_records') or 0),
            'total_present': int(overall_stats.get('total_present') or 0),
            'total_late': int(overall_stats.get('total_late') or 0),
            'total_absent': int(overall_stats.get('total_absent') or 0),
            'overall_percentage': float(overall_stats.get('overall_percentage') or 0),
        }

        cursor.execute(
            """
            SELECT
                COALESCE(NULLIF(shift_name, ''), 'General Availability') AS shift_name,
                COUNT(*) AS total_marked,
                SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS present_count,
                SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END) AS late_count,
                SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) AS absent_count
            FROM faculty_attendance
            WHERE attendance_date = CURDATE()
            GROUP BY shift_key, shift_name
            ORDER BY shift_name
            """
        )
        today_by_shift = cursor.fetchall() or []
        for row in today_by_shift:
            row['total_marked'] = int(row.get('total_marked') or 0)
            row['present_count'] = int(row.get('present_count') or 0)
            row['late_count'] = int(row.get('late_count') or 0)
            row['absent_count'] = int(row.get('absent_count') or 0)

        cursor.execute(
            f"""
            SELECT COUNT(*) AS total_count
            FROM faculty_attendance fa
            JOIN faculty f ON f.id = fa.faculty_id
            LEFT JOIN departments d ON d.id = f.department_id
            LEFT JOIN users u ON u.id = fa.marked_by_user_id
            WHERE {ra_where_sql}
            """,
            tuple(ra_params),
        )
        ra_total_count_row = cursor.fetchone() or {}
        ra_total_count = int(ra_total_count_row.get('total_count') or 0)
        ra_total_pages = max((ra_total_count + ra_per_page - 1) // ra_per_page, 1)
        if ra_page > ra_total_pages:
            ra_page = ra_total_pages
        ra_offset = (ra_page - 1) * ra_per_page

        cursor.execute(
            f"""
            SELECT
                fa.attendance_date,
                fa.status,
                fa.shift_name,
                fa.shift_start_time,
                fa.shift_end_time,
                fa.marked_at,
                fa.source,
                f.id AS faculty_id,
                f.name AS faculty_name,
                f.employee_id,
                d.name AS department_name,
                u.username AS marked_by_username
            FROM faculty_attendance fa
            JOIN faculty f ON f.id = fa.faculty_id
            LEFT JOIN departments d ON d.id = f.department_id
            LEFT JOIN users u ON u.id = fa.marked_by_user_id
            WHERE {ra_where_sql}
            ORDER BY fa.marked_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple([*ra_params, ra_per_page, ra_offset]),
        )
        recent_activity = cursor.fetchall() or []
        for row in recent_activity:
            for key in ('attendance_date', 'marked_at'):
                value = row.get(key)
                if isinstance(value, datetime):
                    if key == 'attendance_date':
                        row[key] = value.strftime('%Y-%m-%d')
                    else:
                        row[key] = value.strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute(
            """
            SELECT
                f.id AS faculty_id,
                f.name AS faculty_name,
                f.employee_id,
                d.name AS department_name,
                COUNT(*) AS total_shifts,
                SUM(CASE WHEN fa.status = 'Present' THEN 1 ELSE 0 END) AS total_present,
                SUM(CASE WHEN fa.status = 'Late' THEN 1 ELSE 0 END) AS total_late,
                SUM(CASE WHEN fa.status = 'Absent' THEN 1 ELSE 0 END) AS total_absent,
                ROUND(
                    (
                        SUM(CASE WHEN fa.status IN ('Present', 'Late') THEN 1 ELSE 0 END)
                        / NULLIF(COUNT(*), 0)
                    ) * 100,
                    2
                ) AS attendance_percentage
            FROM faculty_attendance fa
            JOIN faculty f ON f.id = fa.faculty_id
            LEFT JOIN departments d ON d.id = f.department_id
            WHERE fa.attendance_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            GROUP BY f.id, f.name, f.employee_id, d.name
            ORDER BY attendance_percentage ASC, f.name ASC
            LIMIT 100
            """
        )
        faculty_summary = cursor.fetchall() or []
        for row in faculty_summary:
            row['total_shifts'] = int(row.get('total_shifts') or 0)
            row['total_present'] = int(row.get('total_present') or 0)
            row['total_late'] = int(row.get('total_late') or 0)
            row['total_absent'] = int(row.get('total_absent') or 0)
            row['attendance_percentage'] = float(row.get('attendance_percentage') or 0)

        recent_activity_filters = {
            'q': ra_query,
            'status': ra_status,
            'date_from': ra_date_from,
            'date_to': ra_date_to,
            'per_page': ra_per_page,
        }

        recent_activity_pagination = {
            'page': ra_page,
            'per_page': ra_per_page,
            'total_count': ra_total_count,
            'total_pages': ra_total_pages,
            'has_prev': ra_page > 1,
            'has_next': ra_page < ra_total_pages,
            'start_index': (ra_offset + 1) if ra_total_count > 0 else 0,
            'end_index': min(ra_offset + len(recent_activity), ra_total_count),
        }

        return render_template(
            'admin/attendance/faculty_overview.html',
            overall_stats=overall_stats,
            today_by_shift=today_by_shift,
            recent_activity=recent_activity,
            faculty_summary=faculty_summary,
            recent_activity_filters=recent_activity_filters,
            recent_activity_pagination=recent_activity_pagination,
        )
    except Exception as e:
        print(f"Error in faculty attendance overview: {e}")
        import traceback
        traceback.print_exc()
        flash("An error occurred while loading faculty attendance data.", "danger")
        return render_template(
            'admin/attendance/faculty_overview.html',
            overall_stats={
                'total_faculty': 0,
                'total_records': 0,
                'total_present': 0,
                'total_late': 0,
                'total_absent': 0,
                'overall_percentage': 0.0,
            },
            today_by_shift=[],
            recent_activity=[],
            faculty_summary=[],
            recent_activity_filters={
                'q': '',
                'status': '',
                'date_from': '',
                'date_to': '',
                'per_page': 20,
            },
            recent_activity_pagination={
                'page': 1,
                'per_page': 20,
                'total_count': 0,
                'total_pages': 1,
                'has_prev': False,
                'has_next': False,
                'start_index': 0,
                'end_index': 0,
            },
        )
    finally:
        cursor.close()
        connection.close()


@attendance_admin_bp.route('/faculty/<int:faculty_id>')
@has_permission('attendance_view_faculty')
def faculty_attendance_details(faculty_id):
    """Detailed attendance view for a specific faculty member."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        if not _table_exists(cursor, 'faculty_attendance'):
            flash(
                "faculty_attendance table not found. Run add_mobile_faculty_attendance_sync.sql migration first.",
                "warning",
            )
            return redirect(url_for('attendance_admin.faculty_attendance_overview'))

        cursor.execute(
            """
            SELECT
                f.id,
                f.name,
                f.employee_id,
                f.email,
                f.phone,
                f.designation,
                d.name AS department_name
            FROM faculty f
            LEFT JOIN departments d ON d.id = f.department_id
            WHERE f.id = %s
            """,
            (faculty_id,),
        )
        faculty = cursor.fetchone()

        if not faculty:
            flash("Faculty member not found.", "danger")
            return redirect(url_for('attendance_admin.faculty_attendance_overview'))

        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_shifts,
                SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS total_present,
                SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END) AS total_late,
                SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) AS total_absent,
                ROUND(
                    (
                        SUM(CASE WHEN status IN ('Present', 'Late') THEN 1 ELSE 0 END)
                        / NULLIF(COUNT(*), 0)
                    ) * 100,
                    2
                ) AS overall_percentage
            FROM faculty_attendance
            WHERE faculty_id = %s
            """,
            (faculty_id,),
        )
        overall_stats = cursor.fetchone() or {}
        overall_stats = {
            'total_shifts': int(overall_stats.get('total_shifts') or 0),
            'total_present': int(overall_stats.get('total_present') or 0),
            'total_late': int(overall_stats.get('total_late') or 0),
            'total_absent': int(overall_stats.get('total_absent') or 0),
            'overall_percentage': float(overall_stats.get('overall_percentage') or 0),
        }

        cursor.execute(
            """
            SELECT
                COALESCE(NULLIF(shift_name, ''), 'General Availability') AS shift_name,
                COUNT(*) AS total_shifts,
                SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS present_count,
                SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END) AS late_count,
                SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) AS absent_count,
                ROUND(
                    (
                        SUM(CASE WHEN status IN ('Present', 'Late') THEN 1 ELSE 0 END)
                        / NULLIF(COUNT(*), 0)
                    ) * 100,
                    2
                ) AS attendance_percentage,
                MIN(attendance_date) AS first_marked,
                MAX(attendance_date) AS last_marked
            FROM faculty_attendance
            WHERE faculty_id = %s
            GROUP BY shift_key, shift_name
            ORDER BY shift_name
            """,
            (faculty_id,),
        )
        shift_wise = cursor.fetchall() or []
        for row in shift_wise:
            row['total_shifts'] = int(row.get('total_shifts') or 0)
            row['present_count'] = int(row.get('present_count') or 0)
            row['late_count'] = int(row.get('late_count') or 0)
            row['absent_count'] = int(row.get('absent_count') or 0)
            row['attendance_percentage'] = float(row.get('attendance_percentage') or 0)
            for key in ('first_marked', 'last_marked'):
                value = row.get(key)
                if isinstance(value, datetime):
                    row[key] = value.strftime('%Y-%m-%d')

        cursor.execute(
            """
            SELECT
                fa.attendance_date,
                fa.status,
                fa.shift_name,
                fa.shift_start_time,
                fa.shift_end_time,
                fa.source,
                fa.captured_at,
                fa.confidence,
                fa.remarks,
                fa.marked_at,
                u.username AS marked_by_username
            FROM faculty_attendance fa
            LEFT JOIN users u ON u.id = fa.marked_by_user_id
            WHERE fa.faculty_id = %s
            ORDER BY fa.marked_at DESC
            LIMIT 100
            """,
            (faculty_id,),
        )
        recent_records = cursor.fetchall() or []
        for row in recent_records:
            row['confidence'] = _decimal_to_number(row.get('confidence'))
            for key in ('attendance_date', 'captured_at', 'marked_at'):
                value = row.get(key)
                if isinstance(value, datetime):
                    if key == 'attendance_date':
                        row[key] = value.strftime('%Y-%m-%d')
                    else:
                        row[key] = value.strftime('%Y-%m-%d %H:%M:%S')

        return render_template(
            'admin/attendance/faculty_details.html',
            faculty=faculty,
            overall_stats=overall_stats,
            shift_wise=shift_wise,
            recent_records=recent_records,
        )
    except Exception as e:
        print(f"Error fetching faculty attendance details: {e}")
        import traceback
        traceback.print_exc()
        flash("An error occurred while loading faculty attendance details.", "danger")
        return redirect(url_for('attendance_admin.faculty_attendance_overview'))
    finally:
        cursor.close()
        connection.close()


@attendance_admin_bp.route('/manage')
@has_permission('attendance_manage')
def manage_attendance():
    """
    Attendance records - view, edit, bulk operations.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get filter options
        cursor.execute("SELECT id, name FROM courses ORDER BY name")
        courses = cursor.fetchall()
        
        cursor.execute("SELECT id, name FROM classes ORDER BY name")
        classes = cursor.fetchall()
        
        cursor.execute("SELECT id, name FROM divisions ORDER BY name")
        divisions = cursor.fetchall()
        
        # Get attendance data if filters applied
        attendance_data = None
        filters = {}
        
        if request.args.get('fetch'):
            attendance_date = request.args.get('attendance_date')
            course_id = request.args.get('course_id')
            class_id = request.args.get('class_id')
            division_id = request.args.get('division_id')
            
            filters = {
                'attendance_date': attendance_date,
                'course_id': course_id,
                'class_id': class_id,
                'division_id': division_id
            }
            
            query = """
                SELECT 
                    a.id,
                    a.student_id,
                    s.roll_number as roll_number,
                    s.name as full_name,
                    c.name as course_name,
                    cl.name as class_name,
                    d.name as division_name,
                    DATE_FORMAT(a.attendance_date, '%Y-%m-%d') as attendance_date,
                    a.status,
                    a.remarks
                FROM attendance a
                JOIN students s ON a.student_id = s.id
                JOIN courses c ON s.course_id = c.id
                JOIN classes cl ON s.class_id = cl.id
                JOIN divisions d ON s.division_id = d.id
                WHERE 1=1
            """
            
            params = []
            
            if attendance_date:
                query += " AND a.attendance_date = %s"
                params.append(attendance_date)
            
            if course_id:
                query += " AND s.course_id = %s"
                params.append(course_id)
            
            if class_id:
                query += " AND s.class_id = %s"
                params.append(class_id)
            
            if division_id:
                query += " AND s.division_id = %s"
                params.append(division_id)
            
            query += " ORDER BY s.roll_number"
            
            cursor.execute(query, params)
            attendance_data = cursor.fetchall()
        
        import datetime
        today = datetime.date.today().strftime('%Y-%m-%d')
        
        return render_template('admin/attendance/manage.html',
                             courses=courses,
                             classes=classes,
                             divisions=divisions,
                             records=attendance_data or [],
                             today=today,
                             filters=filters)
    
    finally:
        cursor.close()
        connection.close()


@attendance_admin_bp.route('/manage/update', methods=['POST'])
@has_permission('attendance_manage')
def update_attendance():
    """
    Update attendance record status.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        payload = request.get_json(silent=True) if request.is_json else {}

        attendance_id = (
            request.form.get('attendance_id')
            or request.form.get('record_id')
            or (payload or {}).get('attendance_id')
            or (payload or {}).get('record_id')
        )
        status = request.form.get('status') or (payload or {}).get('status')
        remarks = request.form.get('remarks')
        if remarks is None:
            remarks = (payload or {}).get('remarks', '')

        if not attendance_id:
            return jsonify({'success': False, 'message': 'attendance_id is required'}), 400

        try:
            attendance_id = int(attendance_id)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'attendance_id must be a valid integer'}), 400

        allowed_statuses = {'Present', 'Absent', 'Late'}
        normalized_status = str(status or '').strip().title()
        if normalized_status not in allowed_statuses:
            return jsonify({'success': False, 'message': 'status must be Present, Absent, or Late'}), 400

        cursor.execute("SELECT id FROM attendance WHERE id = %s", [attendance_id])
        existing_record = cursor.fetchone()
        if not existing_record:
            return jsonify({'success': False, 'message': 'Attendance record not found'}), 404

        cursor.execute(
            """
            UPDATE attendance
            SET status = %s, remarks = %s
            WHERE id = %s
            """,
            [normalized_status, str(remarks or '').strip(), attendance_id],
        )

        connection.commit()

        return jsonify({'success': True, 'message': 'Attendance updated successfully'})
    
    except Exception as e:
        connection.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    
    finally:
        cursor.close()
        connection.close()


@attendance_admin_bp.route('/export/overview')
@has_permission('attendance_view')
def export_overview():
    """
    Export overview statistics to CSV.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get class-wise attendance for today
        cursor.execute("""
            SELECT 
                c.name as course_name,
                cl.name as class_name,
                d.name as division_name,
                COUNT(DISTINCT a.student_id) as total_students,
                SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present,
                SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent,
                SUM(CASE WHEN a.status = 'Late' THEN 1 ELSE 0 END) as late,
                ROUND(
                    (SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) / COUNT(*)) * 100, 
                    2
                ) as percentage
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            JOIN courses c ON s.course_id = c.id
            JOIN classes cl ON s.class_id = cl.id
            JOIN divisions d ON s.division_id = d.id
            WHERE DATE(a.attendance_date) = CURDATE()
            GROUP BY c.name, cl.name, d.name
            ORDER BY c.name, cl.name, d.name
        """)
        data = cursor.fetchall()
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers
        writer.writerow(['Course', 'Class', 'Division', 'Total Students', 'Present', 'Absent', 'Late', 'Percentage'])
        
        # Write data
        for row in data:
            writer.writerow([
                row['course_name'],
                row['class_name'],
                row['division_name'],
                row['total_students'],
                row['present'],
                row['absent'],
                row['late'],
                f"{float(row['percentage'] or 0):.2f}%"
            ])
        
        # Create response
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=attendance_overview_{datetime.now().strftime("%Y%m%d")}.csv'
        
        return response
    
    finally:
        cursor.close()
        connection.close()


@attendance_admin_bp.route('/export/defaulters')
@has_permission('attendance_view_defaulters')
def export_defaulters():
    """
    Export defaulters list to CSV.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        threshold = request.args.get('threshold', 75, type=float)
        
        cursor.execute("""
            SELECT 
                st.id as student_id,
                st.roll_number,
                st.full_name,
                st.email,
                st.phone,
                c.name as course_name,
                cl.name as class_name,
                d.name as division_name,
                soa.total_classes,
                soa.present_count,
                soa.absent_count,
                soa.late_count,
                ROUND(soa.attendance_percentage, 2) as attendance_percentage
            FROM student_overall_attendance soa
            JOIN students st ON soa.student_id = st.id
            JOIN courses c ON st.course_id = c.id
            JOIN classes cl ON st.class_id = cl.id
            JOIN divisions d ON st.division_id = d.id
            WHERE soa.attendance_percentage < %s
            ORDER BY soa.attendance_percentage ASC, st.roll_number
        """, [threshold])
        data = cursor.fetchall()
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers
        writer.writerow(['Roll Number', 'Name', 'Course', 'Class', 'Division', 
                        'Total Classes', 'Present', 'Absent', 'Late', 'Percentage', 
                        'Email', 'Phone'])
        
        # Write data
        for row in data:
            writer.writerow([
                row['roll_number'],
                row['full_name'],
                row['course_name'],
                row['class_name'],
                row['division_name'],
                int(row['total_classes'] or 0),
                int(row['present_count'] or 0),
                int(row['absent_count'] or 0),
                int(row['late_count'] or 0),
                f"{float(row['attendance_percentage'] or 0):.2f}%",
                row['email'],
                row['phone']
            ])
        
        # Create response
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=attendance_defaulters_{datetime.now().strftime("%Y%m%d")}.csv'
        
        return response
    
    finally:
        cursor.close()
        connection.close()


@attendance_admin_bp.route('/charts/data')
@has_permission('attendance_view')
def charts_data():
    """
    Provide JSON data for chart visualizations.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        chart_type = request.args.get('type', 'trend')
        
        if chart_type == 'trend':
            # Last 30 days attendance trend
            cursor.execute("""
                SELECT 
                    DATE_FORMAT(attendance_date, '%Y-%m-%d') as date,
                    SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) as present,
                    SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) as absent,
                    SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END) as late
                FROM attendance
                WHERE attendance_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                GROUP BY DATE_FORMAT(attendance_date, '%Y-%m-%d')
                ORDER BY DATE_FORMAT(attendance_date, '%Y-%m-%d')
            """)
            data = cursor.fetchall()
            
            # Convert to chart format
            labels = [row['date'] for row in data]
            present = [int(row['present']) for row in data]
            absent = [int(row['absent']) for row in data]
            late = [int(row['late']) for row in data]
            
            return jsonify({
                'labels': labels,
                'datasets': [
                    {'label': 'Present', 'data': present, 'color': '#10b981'},
                    {'label': 'Absent', 'data': absent, 'color': '#ef4444'},
                    {'label': 'Late', 'data': late, 'color': '#f59e0b'}
                ]
            })
        
        elif chart_type == 'distribution':
            # Class-wise attendance distribution
            cursor.execute("""
                SELECT 
                    CONCAT(c.name, ' ', cl.name) as class_name,
                    ROUND(AVG(
                        CASE WHEN a.status IN ('Present', 'Late') THEN 100 ELSE 0 END
                    ), 2) as attendance_percentage
                FROM attendance a
                JOIN students s ON a.student_id = s.id
                JOIN courses c ON s.course_id = c.id
                JOIN classes cl ON s.class_id = cl.id
                WHERE a.attendance_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                GROUP BY c.id, cl.id, c.name, cl.name
                ORDER BY attendance_percentage DESC
                LIMIT 10
            """)
            data = cursor.fetchall()
            
            labels = [row['class_name'] for row in data]
            values = [float(row['attendance_percentage']) for row in data]
            
            return jsonify({
                'labels': labels,
                'data': values
            })
        
        return jsonify({'error': 'Invalid chart type'}), 400
    
    finally:
        cursor.close()
        connection.close()


@attendance_admin_bp.route('/mobile-logs')
@has_permission('attendance_view')
def mobile_sync_logs():
    """Show mobile synced attendance events from attendance_logs."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        if not _table_exists(cursor, 'attendance_logs'):
            flash("attendance_logs table not found. Run mobile attendance migration first.", "warning")
            return render_template(
                'admin/attendance/mobile_logs.html',
                logs=[],
                stats={'total': 0, 'processed': 0, 'pending': 0, 'failed': 0},
                filters={'date': '', 'processing_status': '', 'device_id': '', 'student_query': '', 'limit': 100},
            )

        filter_date = (request.args.get('date') or '').strip()
        processing_status = (request.args.get('processing_status') or '').strip().lower()
        device_id = (request.args.get('device_id') or '').strip()
        student_query = (request.args.get('student_query') or '').strip()
        limit = request.args.get('limit', 100, type=int) or 100
        limit = max(1, min(limit, 500))

        where_clauses = ['1=1']
        params = []

        if filter_date:
            where_clauses.append('al.attendance_date = %s')
            params.append(filter_date)

        if processing_status in ('processed', 'pending', 'failed'):
            where_clauses.append('al.processing_status = %s')
            params.append(processing_status)

        if device_id:
            where_clauses.append('al.device_id LIKE %s')
            params.append(f'%{device_id}%')

        if student_query:
            where_clauses.append(
                '(st.name LIKE %s OR st.roll_number LIKE %s OR CAST(al.student_id AS CHAR) LIKE %s)'
            )
            like_student = f'%{student_query}%'
            params.extend([like_student, like_student, like_student])

        where_sql = ' AND '.join(where_clauses)

        cursor.execute(
            f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN al.processing_status = 'processed' THEN 1 ELSE 0 END) AS processed,
                SUM(CASE WHEN al.processing_status = 'pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN al.processing_status = 'failed' THEN 1 ELSE 0 END) AS failed
            FROM attendance_logs al
            LEFT JOIN students st ON st.id = al.student_id
            WHERE {where_sql}
            """,
            tuple(params),
        )
        stats = cursor.fetchone() or {}
        stats = {
            'total': int(stats.get('total') or 0),
            'processed': int(stats.get('processed') or 0),
            'pending': int(stats.get('pending') or 0),
            'failed': int(stats.get('failed') or 0),
        }

        cursor.execute(
            f"""
            SELECT
                al.id,
                al.event_uuid,
                al.device_id,
                al.student_id,
                al.timetable_id,
                al.attendance_date,
                al.status,
                al.processing_status,
                al.confidence,
                al.face_model,
                al.detector_model,
                al.remarks,
                al.error_message,
                al.created_at,
                al.captured_at,
                al.processed_at,
                st.name AS student_name,
                st.roll_number,
                u.username AS marked_by_username,
                f.name AS marked_by_faculty,
                sub.name AS subject_name,
                c.name AS course_name,
                cl.name AS class_name,
                d.name AS division_name
            FROM attendance_logs al
            LEFT JOIN students st ON st.id = al.student_id
            LEFT JOIN users u ON u.id = al.marked_by_user_id
            LEFT JOIN faculty f ON f.id = al.marked_by_faculty_id
            LEFT JOIN timetable t ON t.id = al.timetable_id
            LEFT JOIN subjects sub ON sub.id = t.subject_id
            LEFT JOIN courses c ON c.id = t.course_id
            LEFT JOIN classes cl ON cl.id = t.class_id
            LEFT JOIN divisions d ON d.id = t.division_id
            WHERE {where_sql}
            ORDER BY al.created_at DESC
            LIMIT %s
            """,
            tuple(params + [limit]),
        )
        logs = cursor.fetchall() or []

        for row in logs:
            row['confidence'] = _decimal_to_number(row.get('confidence'))
            for key in ('attendance_date', 'created_at', 'captured_at', 'processed_at'):
                value = row.get(key)
                if isinstance(value, datetime):
                    if key == 'attendance_date':
                        row[key] = value.strftime('%Y-%m-%d')
                    else:
                        row[key] = value.strftime('%Y-%m-%d %H:%M:%S')

        return render_template(
            'admin/attendance/mobile_logs.html',
            logs=logs,
            stats=stats,
            filters={
                'date': filter_date,
                'processing_status': processing_status,
                'device_id': device_id,
                'student_query': student_query,
                'limit': limit,
            },
        )
    except Exception as e:
        print(f"Error fetching mobile sync logs: {e}")
        import traceback
        traceback.print_exc()
        flash("Unable to load mobile sync attendance logs.", "danger")
        return render_template(
            'admin/attendance/mobile_logs.html',
            logs=[],
            stats={'total': 0, 'processed': 0, 'pending': 0, 'failed': 0},
            filters={'date': '', 'processing_status': '', 'device_id': '', 'student_query': '', 'limit': 100},
        )
    finally:
        cursor.close()
        connection.close()


@attendance_admin_bp.route('/faculty-mobile-logs')
@has_permission('attendance_view_faculty')
def faculty_mobile_sync_logs():
    """Show mobile synced faculty attendance events from faculty_attendance_logs."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        if not _table_exists(cursor, 'faculty_attendance_logs'):
            flash(
                "faculty_attendance_logs table not found. Run add_mobile_faculty_attendance_sync.sql migration first.",
                "warning",
            )
            return render_template(
                'admin/attendance/faculty_mobile_logs.html',
                logs=[],
                stats={'total': 0, 'processed': 0, 'pending': 0, 'failed': 0},
                filters={
                    'date': '',
                    'processing_status': '',
                    'device_id': '',
                    'faculty_query': '',
                    'shift_query': '',
                    'per_page': 100,
                },
                pagination={
                    'page': 1,
                    'per_page': 100,
                    'total_count': 0,
                    'total_pages': 1,
                    'has_prev': False,
                    'has_next': False,
                    'start_index': 0,
                    'end_index': 0,
                },
            )

        filter_date = (request.args.get('date') or '').strip()
        processing_status = (request.args.get('processing_status') or '').strip().lower()
        device_id = (request.args.get('device_id') or '').strip()
        faculty_query = (request.args.get('faculty_query') or '').strip()
        shift_query = (request.args.get('shift_query') or '').strip()
        page = request.args.get('page', 1, type=int) or 1
        page = max(page, 1)

        per_page = request.args.get('per_page', type=int)
        if per_page is None:
            per_page = request.args.get('limit', 100, type=int)
        per_page = per_page or 100
        if per_page not in (20, 50, 100):
            per_page = 100

        where_clauses = ['1=1']
        params = []

        if filter_date:
            where_clauses.append('fal.attendance_date = %s')
            params.append(filter_date)

        if processing_status in ('processed', 'pending', 'failed'):
            where_clauses.append('fal.processing_status = %s')
            params.append(processing_status)

        if device_id:
            where_clauses.append('fal.device_id LIKE %s')
            params.append(f'%{device_id}%')

        if faculty_query:
            where_clauses.append(
                '('
                'f.name LIKE %s '
                'OR f.employee_id LIKE %s '
                'OR CAST(fal.faculty_id AS CHAR) LIKE %s '
                'OR CAST(fal.faculty_user_id AS CHAR) LIKE %s'
                ')'
            )
            like_faculty = f'%{faculty_query}%'
            params.extend([like_faculty, like_faculty, like_faculty, like_faculty])

        if shift_query:
            where_clauses.append('(fal.shift_name LIKE %s OR fal.shift_code LIKE %s)')
            like_shift = f'%{shift_query}%'
            params.extend([like_shift, like_shift])

        where_sql = ' AND '.join(where_clauses)

        cursor.execute(
            f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN fal.processing_status = 'processed' THEN 1 ELSE 0 END) AS processed,
                SUM(CASE WHEN fal.processing_status = 'pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN fal.processing_status = 'failed' THEN 1 ELSE 0 END) AS failed
            FROM faculty_attendance_logs fal
            LEFT JOIN faculty f ON f.id = fal.faculty_id
            WHERE {where_sql}
            """,
            tuple(params),
        )
        stats = cursor.fetchone() or {}
        stats = {
            'total': int(stats.get('total') or 0),
            'processed': int(stats.get('processed') or 0),
            'pending': int(stats.get('pending') or 0),
            'failed': int(stats.get('failed') or 0),
        }

        cursor.execute(
            f"""
            SELECT COUNT(*) AS total_count
            FROM faculty_attendance_logs fal
            LEFT JOIN faculty f ON f.id = fal.faculty_id
            WHERE {where_sql}
            """,
            tuple(params),
        )
        total_count_row = cursor.fetchone() or {}
        total_count = int(total_count_row.get('total_count') or 0)
        total_pages = max((total_count + per_page - 1) // per_page, 1)
        if page > total_pages:
            page = total_pages
        offset = (page - 1) * per_page

        cursor.execute(
            f"""
            SELECT
                fal.id,
                fal.event_uuid,
                fal.device_id,
                fal.faculty_id,
                fal.faculty_user_id,
                fal.attendance_date,
                fal.day_of_week,
                fal.shift_key,
                fal.shift_pattern_id,
                fal.shift_name,
                fal.shift_code,
                fal.shift_start_time,
                fal.shift_end_time,
                fal.status,
                fal.processing_status,
                fal.confidence,
                fal.face_model,
                fal.detector_model,
                fal.remarks,
                fal.error_message,
                fal.created_at,
                fal.captured_at,
                fal.processed_at,
                f.name AS faculty_name,
                f.employee_id,
                d.name AS department_name,
                fu.username AS faculty_username,
                mu.username AS marked_by_username,
                sp.shift_name AS shift_pattern_name,
                sp.shift_code AS shift_pattern_code
            FROM faculty_attendance_logs fal
            LEFT JOIN faculty f ON f.id = fal.faculty_id
            LEFT JOIN departments d ON d.id = f.department_id
            LEFT JOIN users fu ON fu.id = fal.faculty_user_id
            LEFT JOIN users mu ON mu.id = fal.marked_by_user_id
            LEFT JOIN shift_patterns sp ON sp.id = fal.shift_pattern_id
            WHERE {where_sql}
            ORDER BY fal.created_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple([*params, per_page, offset]),
        )
        logs = cursor.fetchall() or []

        for row in logs:
            row['confidence'] = _decimal_to_number(row.get('confidence'))
            for key in ('attendance_date', 'created_at', 'captured_at', 'processed_at'):
                value = row.get(key)
                if isinstance(value, datetime):
                    if key == 'attendance_date':
                        row[key] = value.strftime('%Y-%m-%d')
                    else:
                        row[key] = value.strftime('%Y-%m-%d %H:%M:%S')

        pagination = {
            'page': page,
            'per_page': per_page,
            'total_count': total_count,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'start_index': (offset + 1) if total_count > 0 else 0,
            'end_index': min(offset + len(logs), total_count),
        }

        return render_template(
            'admin/attendance/faculty_mobile_logs.html',
            logs=logs,
            stats=stats,
            filters={
                'date': filter_date,
                'processing_status': processing_status,
                'device_id': device_id,
                'faculty_query': faculty_query,
                'shift_query': shift_query,
                'per_page': per_page,
            },
            pagination=pagination,
        )
    except Exception as e:
        print(f"Error fetching faculty mobile sync logs: {e}")
        import traceback
        traceback.print_exc()
        flash("Unable to load faculty mobile sync logs.", "danger")
        return render_template(
            'admin/attendance/faculty_mobile_logs.html',
            logs=[],
            stats={'total': 0, 'processed': 0, 'pending': 0, 'failed': 0},
            filters={
                'date': '',
                'processing_status': '',
                'device_id': '',
                'faculty_query': '',
                'shift_query': '',
                'per_page': 100,
            },
            pagination={
                'page': 1,
                'per_page': 100,
                'total_count': 0,
                'total_pages': 1,
                'has_prev': False,
                'has_next': False,
                'start_index': 0,
                'end_index': 0,
            },
        )
    finally:
        cursor.close()
        connection.close()


@attendance_admin_bp.route('/faculty-mobile-logs/reprocess', methods=['POST'])
@has_permission('attendance_manage_faculty')
def reprocess_faculty_mobile_sync_logs():
    """Reprocess pending/failed faculty mobile logs into faculty_attendance table."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        if not _table_exists(cursor, 'faculty_attendance_logs') or not _table_exists(cursor, 'faculty_attendance'):
            flash(
                'faculty_attendance_logs/faculty_attendance tables not found. Run migration first.',
                'warning',
            )
            return redirect(url_for('attendance_admin.faculty_mobile_sync_logs'))

        limit = request.form.get('limit', 100, type=int) or 100
        limit = max(1, min(limit, 500))

        cursor.execute(
            """
            SELECT *
            FROM faculty_attendance_logs
            WHERE processing_status IN ('pending', 'failed')
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (limit,),
        )
        log_rows = cursor.fetchall() or []

        retried = 0
        processed = 0
        failed = 0

        for log_row in log_rows:
            retried += 1
            try:
                _promote_log_to_faculty_attendance(cursor, log_row)
                cursor.execute(
                    """
                    UPDATE faculty_attendance_logs
                    SET processing_status = 'processed',
                        processed_at = NOW(),
                        error_message = NULL
                    WHERE id = %s
                    """,
                    (log_row['id'],),
                )
                processed += 1
            except Exception as process_error:
                failed += 1
                cursor.execute(
                    """
                    UPDATE faculty_attendance_logs
                    SET processing_status = 'failed',
                        error_message = %s
                    WHERE id = %s
                    """,
                    (str(process_error)[:500], log_row['id']),
                )

        connection.commit()
        flash(
            f"Faculty reprocess complete: retried={retried}, processed={processed}, failed={failed}",
            'success' if failed == 0 else 'warning',
        )
        return redirect(url_for('attendance_admin.faculty_mobile_sync_logs'))
    except Exception as e:
        connection.rollback()
        flash(f'Failed to reprocess faculty mobile sync logs: {str(e)}', 'danger')
        return redirect(url_for('attendance_admin.faculty_mobile_sync_logs'))
    finally:
        cursor.close()
        connection.close()


@attendance_admin_bp.route('/mobile-logs/reprocess', methods=['POST'])
@has_permission('attendance_manage')
def reprocess_mobile_sync_logs():
    """Reprocess pending/failed mobile logs into attendance table."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        if not _table_exists(cursor, 'attendance_logs'):
            flash('attendance_logs table not found. Run migration first.', 'warning')
            return redirect(url_for('attendance_admin.mobile_sync_logs'))

        limit = request.form.get('limit', 100, type=int) or 100
        limit = max(1, min(limit, 500))

        cursor.execute(
            """
            SELECT *
            FROM attendance_logs
            WHERE processing_status IN ('pending', 'failed')
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (limit,),
        )
        log_rows = cursor.fetchall() or []

        retried = 0
        processed = 0
        failed = 0

        for log_row in log_rows:
            retried += 1
            try:
                _promote_log_to_attendance(cursor, log_row)
                cursor.execute(
                    """
                    UPDATE attendance_logs
                    SET processing_status = 'processed',
                        processed_at = NOW(),
                        error_message = NULL
                    WHERE id = %s
                    """,
                    (log_row['id'],),
                )
                processed += 1
            except Exception as process_error:
                failed += 1
                cursor.execute(
                    """
                    UPDATE attendance_logs
                    SET processing_status = 'failed',
                        error_message = %s
                    WHERE id = %s
                    """,
                    (str(process_error)[:500], log_row['id']),
                )

        connection.commit()
        flash(
            f"Reprocess complete: retried={retried}, processed={processed}, failed={failed}",
            'success' if failed == 0 else 'warning',
        )
        return redirect(url_for('attendance_admin.mobile_sync_logs'))
    except Exception as e:
        connection.rollback()
        flash(f'Failed to reprocess mobile sync logs: {str(e)}', 'danger')
        return redirect(url_for('attendance_admin.mobile_sync_logs'))
    finally:
        cursor.close()
        connection.close()
