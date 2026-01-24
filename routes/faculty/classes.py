from flask import session, redirect, url_for, flash, render_template
from database import get_db_connection
from .teacher import teacher_bp, teacher_required

@teacher_bp.route('/my-classes')
@teacher_required
def my_classes():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    faculty_id = session.get('faculty_id')
    if not faculty_id:
        flash("Faculty profile not found. Please contact administrator.", "danger")
        return redirect(url_for('auth.logout'))
    
    # Get user_id for this faculty (timetable uses user_id as faculty_id)
    cursor.execute("SELECT user_id FROM faculty WHERE id = %s", (faculty_id,))
    faculty_record = cursor.fetchone()
    if not faculty_record:
        flash("Faculty profile not found. Please contact administrator.", "danger")
        return redirect(url_for('auth.logout'))
    
    faculty_user_id = faculty_record['user_id']
    
    # Fetch all classes where teacher teaches with students (timetable uses user_id)
    cursor.execute(
        """
        SELECT DISTINCT 
            cl.id as class_id,
            cl.name as class_name, 
            d.id as division_id,
            d.name as division_name, 
            co.id as course_id,
            co.name as course_name,
            s.id as subject_id,
            s.name as subject_name
        FROM timetable t
        JOIN classes cl ON t.class_id = cl.id
        JOIN divisions d ON t.division_id = d.id
        JOIN courses co ON t.course_id = co.id
        JOIN subjects s ON t.subject_id = s.id
        WHERE t.faculty_id = %s
        ORDER BY cl.name, d.name, co.name, s.name
        """,
        [faculty_user_id],
    )
    teaching_assignments = cursor.fetchall()
    
    # Fetch students for each class
    classes_with_students = []
    for assignment in teaching_assignments:
        class_id = assignment['class_id']
        class_name = assignment['class_name']
        division_id = assignment['division_id']
        division_name = assignment['division_name']
        course_id = assignment['course_id']
        course_name = assignment['course_name']
        subject_id = assignment['subject_id']
        subject_name = assignment['subject_name']
        
        cursor.execute(
            """
            SELECT st.id, st.name, st.email, u.username
            FROM students st
            JOIN users u ON st.user_id = u.id
            WHERE st.class_id = %s 
                AND st.division_id = %s 
                AND st.course_id = %s
            ORDER BY st.name
            """,
            [class_id, division_id, course_id],
        )
        students = cursor.fetchall()
        
        classes_with_students.append({
            'class_name': class_name,
            'division_name': division_name,
            'course_name': course_name,
            'subject_name': subject_name,
            'student_count': len(students),
            'students': students
        })
    
    cursor.close()
    return render_template('teacher/my_classes.html', classes=classes_with_students)
