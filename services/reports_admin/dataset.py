"""Admin report screens. dataset."""

def _build_report_export_dataset(cursor, report_type, payload):
    """Build export dataset and ordered CSV fields for a report type."""
    rows = []
    fieldnames = []

    if report_type == 'attendance':
        start_date = payload.get('start_date')
        end_date = payload.get('end_date')
        course_id = payload.get('course_id')
        class_id = payload.get('class_id')
        division_id = payload.get('division_id')

        query = """
            SELECT
                s.id as student_id,
                s.id as roll_number,
                s.name as full_name,
                c.name as course_name,
                cl.name as class_name,
                d.name as division_name,
                COUNT(a.id) as total_classes,
                SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present,
                SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent,
                SUM(CASE WHEN a.status = 'Late' THEN 1 ELSE 0 END) as late,
                ROUND(
                    (SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) / NULLIF(COUNT(a.id), 0)) * 100,
                    2
                ) as attendance_percentage
            FROM students s
            JOIN courses c ON s.course_id = c.id
            JOIN classes cl ON s.class_id = cl.id
            JOIN divisions d ON s.division_id = d.id
            LEFT JOIN attendance a ON s.id = a.student_id
        """

        conditions = []
        params = []
        if start_date:
            conditions.append("a.attendance_date >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("a.attendance_date <= %s")
            params.append(end_date)
        if course_id:
            conditions.append("s.course_id = %s")
            params.append(course_id)
        if class_id:
            conditions.append("s.class_id = %s")
            params.append(class_id)
        if division_id:
            conditions.append("s.division_id = %s")
            params.append(division_id)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " GROUP BY s.id, s.name, c.name, cl.name, d.name ORDER BY s.id"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        for row in rows:
            row['attendance_percentage'] = float(row.get('attendance_percentage') or 0)

        fieldnames = [
            'student_id', 'roll_number', 'full_name', 'course_name', 'class_name',
            'division_name', 'total_classes', 'present', 'absent', 'late', 'attendance_percentage'
        ]

    elif report_type == 'timetable':
        report_view = payload.get('report_type', 'class')
        entity_id = payload.get('entity_id')

        if report_view not in {'class', 'faculty', 'room'} or not entity_id:
            raise ValueError('Timetable export requires a report type and entity.')

        if report_view == 'class':
            query = """
                SELECT
                    t.day_of_week,
                    DATE_FORMAT(t.start_time, '%H:%i') as start_time,
                    DATE_FORMAT(t.end_time, '%H:%i') as end_time,
                    sub.name as subject_name,
                    sub.course_code as subject_code,
                    f.name as faculty_name,
                    r.room_number,
                    r.room_type as room_name,
                    d.name as division_name
                FROM timetable t
                JOIN subjects sub ON t.subject_id = sub.id
                JOIN faculty f ON t.faculty_id = f.user_id
                JOIN rooms r ON t.room_id = r.id
                JOIN divisions d ON t.division_id = d.id
                WHERE t.class_id = %s AND t.is_active = 1
                ORDER BY FIELD(t.day_of_week, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'), t.start_time
            """
            cursor.execute(query, [entity_id])
            rows = cursor.fetchall()
            fieldnames = [
                'day_of_week', 'start_time', 'end_time', 'subject_name', 'subject_code',
                'faculty_name', 'room_number', 'room_name', 'division_name'
            ]
        elif report_view == 'faculty':
            query = """
                SELECT
                    t.day_of_week,
                    DATE_FORMAT(t.start_time, '%H:%i') as start_time,
                    DATE_FORMAT(t.end_time, '%H:%i') as end_time,
                    sub.name as subject_name,
                    sub.course_code as subject_code,
                    c.name as course_name,
                    cl.name as class_name,
                    d.name as division_name,
                    r.room_number,
                    r.room_type as room_name
                FROM timetable t
                JOIN subjects sub ON t.subject_id = sub.id
                JOIN courses c ON t.course_id = c.id
                JOIN classes cl ON t.class_id = cl.id
                JOIN divisions d ON t.division_id = d.id
                JOIN rooms r ON t.room_id = r.id
                WHERE t.faculty_id = %s AND t.is_active = 1
                ORDER BY FIELD(t.day_of_week, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'), t.start_time
            """
            cursor.execute(query, [entity_id])
            rows = cursor.fetchall()
            fieldnames = [
                'day_of_week', 'start_time', 'end_time', 'subject_name', 'subject_code',
                'course_name', 'class_name', 'division_name', 'room_number', 'room_name'
            ]
        else:
            query = """
                SELECT
                    t.day_of_week,
                    DATE_FORMAT(t.start_time, '%H:%i') as start_time,
                    DATE_FORMAT(t.end_time, '%H:%i') as end_time,
                    sub.name as subject_name,
                    sub.course_code as subject_code,
                    f.name as faculty_name,
                    c.name as course_name,
                    cl.name as class_name,
                    d.name as division_name
                FROM timetable t
                JOIN subjects sub ON t.subject_id = sub.id
                JOIN faculty f ON t.faculty_id = f.user_id
                JOIN courses c ON t.course_id = c.id
                JOIN classes cl ON t.class_id = cl.id
                JOIN divisions d ON t.division_id = d.id
                WHERE t.room_id = %s AND t.is_active = 1
                ORDER BY FIELD(t.day_of_week, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'), t.start_time
            """
            cursor.execute(query, [entity_id])
            rows = cursor.fetchall()
            fieldnames = [
                'day_of_week', 'start_time', 'end_time', 'subject_name', 'subject_code',
                'faculty_name', 'course_name', 'class_name', 'division_name'
            ]

    elif report_type == 'audit-logs':
        start_date = payload.get('start_date')
        end_date = payload.get('end_date')
        user_id = payload.get('user_id')
        action = payload.get('action')

        query = """
            SELECT
                al.id,
                u.username,
                al.activity_type as action,
                al.description,
                al.ip_address,
                al.user_agent,
                DATE_FORMAT(al.created_at, '%Y-%m-%d %H:%i:%s') as timestamp
            FROM user_activity_log al
            JOIN users u ON al.user_id = u.id
        """

        conditions = []
        params = []
        if start_date:
            conditions.append("DATE(al.created_at) >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("DATE(al.created_at) <= %s")
            params.append(end_date)
        if user_id:
            conditions.append("al.user_id = %s")
            params.append(user_id)
        if action:
            conditions.append("al.activity_type = %s")
            params.append(action)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY al.created_at DESC LIMIT 500"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        fieldnames = ['id', 'timestamp', 'username', 'action', 'description', 'ip_address', 'user_agent']

    elif report_type == 'shifts':
        status = payload.get('status')
        faculty_id = payload.get('faculty_id')
        start_date = payload.get('start_date')
        end_date = payload.get('end_date')

        query = """
            SELECT
                scr.id,
                f.name as full_name,
                scr.current_shift_name as current_shift,
                scr.requested_shift_name as requested_shift,
                scr.reason,
                scr.status,
                DATE_FORMAT(scr.created_at, '%Y-%m-%d') as effective_date,
                DATE_FORMAT(scr.created_at, '%Y-%m-%d %H:%i') as created_at,
                COALESCE(scr.admin_response, '') as admin_remarks
            FROM shift_change_requests scr
            LEFT JOIN faculty f ON scr.faculty_id = f.id OR scr.faculty_id = f.user_id
        """

        conditions = []
        params = []
        if status:
            conditions.append("scr.status = %s")
            params.append(status)
        if faculty_id:
            conditions.append("(scr.faculty_id = %s OR f.id = %s OR f.user_id = %s)")
            params.extend([faculty_id, faculty_id, faculty_id])
        if start_date:
            conditions.append("DATE(scr.created_at) >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("DATE(scr.created_at) <= %s")
            params.append(end_date)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY scr.created_at DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        fieldnames = [
            'id', 'full_name', 'current_shift', 'requested_shift', 'status',
            'effective_date', 'created_at', 'reason', 'admin_remarks'
        ]

    elif report_type == 'proxy-log':
        start_date = payload.get('start_date')
        end_date = payload.get('end_date')

        query = """
            SELECT
                pl.id,
                f1.name as original_faculty,
                f2.name as proxy_faculty,
                sub.name as subject_name,
                course.name as course_name,
                c.name as class_name,
                d.name as division_name,
                DATE_FORMAT(pl.absence_date, '%Y-%m-%d') as proxy_date,
                DATE_FORMAT(t.start_time, '%H:%i') as start_time,
                DATE_FORMAT(t.end_time, '%H:%i') as end_time,
                COALESCE(pl.approval_notes, '') as reason,
                DATE_FORMAT(COALESCE(pl.approval_date, pl.absence_date), '%Y-%m-%d %H:%i') as created_at
            FROM proxy_log pl
            JOIN faculty f1 ON pl.original_faculty_id = f1.user_id
            LEFT JOIN faculty f2 ON pl.proxy_faculty_id = f2.user_id
            JOIN timetable t ON pl.timetable_id = t.id
            JOIN subjects sub ON t.subject_id = sub.id
            JOIN courses course ON t.course_id = course.id
            JOIN classes c ON t.class_id = c.id
            LEFT JOIN divisions d ON t.division_id = d.id
        """

        conditions = []
        params = []
        if start_date:
            conditions.append("pl.absence_date >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("pl.absence_date <= %s")
            params.append(end_date)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY pl.absence_date DESC, t.start_time DESC LIMIT 500"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        fieldnames = [
            'id', 'proxy_date', 'start_time', 'end_time', 'original_faculty',
            'proxy_faculty', 'subject_name', 'course_name', 'class_name',
            'division_name', 'reason', 'created_at'
        ]

    elif report_type == 'invitations':
        role = payload.get('role')
        status = payload.get('status')
        start_date = payload.get('start_date')
        end_date = payload.get('end_date')
        course_id = payload.get('course_id')
        class_id = payload.get('class_id')
        division_id = payload.get('division_id')

        query = """
            SELECT
                ri.id,
                ri.email,
                ri.role,
                ri.status,
                c.name as course_name,
                cl.name as class_name,
                d.name as division_name,
                DATE_FORMAT(ri.created_at, '%Y-%m-%d %H:%i') as created_at,
                DATE_FORMAT(ri.expires_at, '%Y-%m-%d') as expires_at,
                CASE
                    WHEN ri.status = 'used' THEN 'Registered'
                    WHEN ri.expires_at < NOW() THEN 'Expired'
                    ELSE 'Active'
                END as display_status
            FROM registration_invitations ri
            LEFT JOIN courses c ON ri.course_id = c.id
            LEFT JOIN classes cl ON ri.class_id = cl.id
            LEFT JOIN divisions d ON ri.division_id = d.id
        """

        conditions = []
        params = []
        if role:
            conditions.append("ri.role = %s")
            params.append(role)
        if status:
            conditions.append("ri.status = %s")
            params.append(status)
        if start_date:
            conditions.append("DATE(ri.created_at) >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("DATE(ri.created_at) <= %s")
            params.append(end_date)
        if course_id:
            conditions.append("ri.course_id = %s")
            params.append(course_id)
        if class_id:
            conditions.append("ri.class_id = %s")
            params.append(class_id)
        if division_id:
            conditions.append("ri.division_id = %s")
            params.append(division_id)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY ri.created_at DESC LIMIT 500"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        fieldnames = [
            'id', 'email', 'role', 'status', 'display_status',
            'course_name', 'class_name', 'division_name', 'created_at', 'expires_at'
        ]

    return rows, fieldnames
