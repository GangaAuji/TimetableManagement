"""Admin attendance screens. students.

These routes serve the React page. The figures on it come from
/api/attendance/overview (services.attendance_calc), so nothing is computed
here.
"""

from ui.pages import render_template


def attendance_overview():
    """Main attendance dashboard."""
    return render_template('admin/attendance/overview.html')


def attendance_defaulters():
    """Students below the attendance threshold."""
    return render_template('admin/attendance/defaulters.html')


def student_attendance_details(student_id):
    """Detailed attendance view for a specific student."""
    return render_template('admin/attendance/student_details.html', student_id=student_id)
