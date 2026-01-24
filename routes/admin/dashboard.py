"""
Admin Dashboard Routes
Displays statistics, charts, and quick access to core admin functions
"""

from flask import Blueprint, render_template, session
from datetime import datetime
from database import get_db_connection

# Import shared utilities
from routes.admin_utils import admin_required, format_time

dashboard_bp = Blueprint('admin', __name__, url_prefix='/admin')


@dashboard_bp.route('/dashboard')
@admin_required
def dashboard():
    """Main admin dashboard with statistics and overview"""
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Basic stats - using COUNT(*) with alias for DictCursor
        cursor.execute("SELECT COUNT(id) as count FROM students WHERE is_active = 1")
        total_students = int(cursor.fetchone()['count'])
        
        cursor.execute("SELECT COUNT(id) as count FROM faculty WHERE is_active = 1")
        total_faculty = int(cursor.fetchone()['count'])
        
        cursor.execute("SELECT COUNT(id) as count FROM courses WHERE is_active = 1")
        total_courses = int(cursor.fetchone()['count'])
        
        cursor.execute("SELECT COUNT(id) as count FROM departments WHERE is_active = 1")
        total_departments = int(cursor.fetchone()['count'])
        
        cursor.execute("SELECT COUNT(id) as count FROM rooms")
        total_rooms = int(cursor.fetchone()['count'])
        
        cursor.execute("SELECT COUNT(id) as count FROM course_batches WHERE is_active = 1")
        total_batches = int(cursor.fetchone()['count'])
        
        cursor.execute("SELECT COUNT(id) as count FROM subjects")
        total_subjects = int(cursor.fetchone()['count'])
        
        cursor.execute("SELECT COUNT(id) as count FROM faculty_allocations")
        total_allocations = int(cursor.fetchone()['count'])
        
        # Room breakdown
        cursor.execute("SELECT room_type, COUNT(*) as count FROM rooms GROUP BY room_type")
        room_breakdown = {row['room_type']: int(row['count']) for row in cursor.fetchall()}
        
        # Weekly schedule load (classes per day)
        cursor.execute("""
            SELECT day_of_week, COUNT(*) as class_count
            FROM timetable
            GROUP BY day_of_week
            ORDER BY FIELD(day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday')
        """)
        weekly_load = {row['day_of_week']: int(row['class_count']) for row in cursor.fetchall()}
        
        # Session type distribution
        cursor.execute("""
            SELECT s.theory_practical, COUNT(t.id) as count
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            GROUP BY s.theory_practical
        """)
        session_types = {row['theory_practical']: int(row['count']) for row in cursor.fetchall()}
        total_sessions = sum(session_types.values()) or 1
        session_percentages = {k: float(round((int(v)/total_sessions)*100, 1)) for k, v in session_types.items()}
        
        # Today's active classes
        today = datetime.now().strftime('%A')
        cursor.execute("""
            SELECT t.start_time, t.end_time, s.name as subject_name, 
                   f.name as faculty_name, r.room_number,
                   c.name as class_name, d.name as division_name,
                   s.theory_practical,
                   dept.name as department_name,
                   course.name as course_name
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN faculty f ON t.faculty_id = f.user_id
            LEFT JOIN rooms r ON t.room_id = r.id
            JOIN classes c ON t.class_id = c.id
            LEFT JOIN divisions d ON t.division_id = d.id
            LEFT JOIN courses course ON s.course_id = course.id
            LEFT JOIN departments dept ON course.department_id = dept.id
            WHERE t.day_of_week = %s
            ORDER BY t.start_time
            LIMIT 50
        """, (today,))
        todays_classes = cursor.fetchall()
    
        # Recent proxy requests (last 5)
        cursor.execute("""
            SELECT pl.id, pl.absence_date, 
                   f1.name as original_faculty, 
                   f2.name as proxy_faculty,
                   pl.status, pl.approval_status,
                   s.name as subject_name,
                   pl.approval_date
            FROM proxy_log pl
            JOIN faculty f1 ON pl.original_faculty_id = f1.user_id
            LEFT JOIN faculty f2 ON pl.proxy_faculty_id = f2.user_id
            JOIN timetable t ON pl.timetable_id = t.id
            JOIN subjects s ON t.subject_id = s.id
            ORDER BY pl.absence_date DESC, pl.id DESC
            LIMIT 5
        """)
        recent_proxies = cursor.fetchall()
        
        # Upcoming holidays
        cursor.execute("""
            SELECT name, holiday_date, applies_to_program
            FROM institution_holidays
            WHERE holiday_date >= CURDATE()
            ORDER BY holiday_date
            LIMIT 5
        """)
        upcoming_holidays = cursor.fetchall()
        
        # Faculty workload (top 5 busiest)
        cursor.execute("""
            SELECT f.name, 
                   COUNT(t.id) as class_count,
                   COALESCE(SUM(TIMESTAMPDIFF(MINUTE, t.start_time, t.end_time) / 60), 0) as hours
            FROM faculty f
            LEFT JOIN timetable t ON f.user_id = t.faculty_id
            WHERE f.is_active = 1
            GROUP BY f.user_id, f.name
            ORDER BY class_count DESC
            LIMIT 5
        """)
        faculty_workload = cursor.fetchall()
    
        cursor.close()
        
        # Prepare stats dictionary for template
        stats = {
            'today_day': datetime.now().strftime('%A, %B %d, %Y'),
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
            'today_classes': todays_classes,
            'recent_updates': [],  # Can be populated later if needed
            'top_faculty': faculty_workload
        }
        
        return render_template(
            'admin/dashboard.html',
            stats=stats,
            recent_proxies=recent_proxies,
            upcoming_holidays=upcoming_holidays,
            format_time=format_time
        )
        
    except Exception as e:
        # Log the error and return error page
        print(f"Dashboard Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Return minimal dashboard with error message
        return render_template(
            'admin/dashboard.html',
            stats={
                'today_day': datetime.now().strftime('%A, %B %d, %Y'),
                'total_students': 0,
                'total_faculty': 0,
                'total_courses': 0,
                'total_departments': 0,
                'total_rooms': 0,
                'total_batches': 0,
                'total_subjects': 0,
                'total_allocations': 0,
                'room_breakdown': {},
                'weekly_load': {},
                'session_types': {},
                'session_percentages': {},
                'today_classes': [],
                'recent_updates': [],
                'top_faculty': []
            },
            recent_proxies=[],
            upcoming_holidays=[],
            format_time=format_time,
            error_message=f"Error loading dashboard: {str(e)}"
        )
