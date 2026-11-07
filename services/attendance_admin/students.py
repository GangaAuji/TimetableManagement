"""Admin attendance screens. students."""

from flask import Blueprint, request, jsonify, session, flash, redirect, url_for, make_response
from ui.pages import render_template
from core.pagination import page_bounds
from extensions import get_db_connection
from datetime import datetime, timedelta

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

        total_pages = page_bounds(page, per_page, total_count, minimum_pages=1)[1]
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
