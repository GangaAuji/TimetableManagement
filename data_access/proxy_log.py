"""Proxy log SQL. The list query is extended by the caller before it is run."""

PROXY_LOG_QUERY = """
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


def fetch_proxy_request(cursor, proxy_id):
    """Return one substitution request with the class it covers."""
    cursor.execute(
        """
        SELECT pl.id, pl.original_faculty_id, pl.proxy_faculty_id, pl.absence_date,
               pl.status, pl.approval_status,
               t.day_of_week, t.start_time, t.end_time, t.subject_id
        FROM proxy_log pl
        JOIN timetable t ON t.id = pl.timetable_id
        WHERE pl.id = %s
        """,
        (proxy_id,),
    )
    return cursor.fetchone()


def fetch_cover_faculty(cursor, subject_id, original_user_id):
    """Return active faculty who teach this subject, other than the person who asked."""
    cursor.execute(
        """
        SELECT DISTINCT f.user_id, f.name, f.employee_id
        FROM faculty f
        WHERE f.is_active = 1
          AND f.user_id <> %s
          AND (
            EXISTS (
                SELECT 1 FROM faculty_allocations fa
                WHERE fa.subject_id = %s AND (fa.faculty_id = f.user_id OR fa.faculty_id = f.id)
            )
            OR EXISTS (
                SELECT 1 FROM timetable t
                WHERE t.subject_id = %s AND t.faculty_id = f.user_id
            )
          )
        ORDER BY f.name
        LIMIT 40
        """,
        (original_user_id, subject_id, subject_id),
    )
    return cursor.fetchall()


def fetch_named_faculty(cursor, user_id):
    """Return one active faculty member by the user id stored on a proxy row."""
    cursor.execute(
        "SELECT user_id, name, employee_id FROM faculty WHERE user_id = %s AND is_active = 1",
        (user_id,),
    )
    return cursor.fetchone()


def fetch_proxy_clash(cursor, proxy_user_id, absence_date, start_time, end_time, proxy_id):
    """Return a row when this faculty is already the approved substitute for an overlapping class."""
    cursor.execute(
        """
        SELECT 1 AS clash
        FROM proxy_log pl
        JOIN timetable t ON t.id = pl.timetable_id
        WHERE pl.proxy_faculty_id = %s
          AND pl.absence_date = %s
          AND pl.id <> %s
          AND pl.status = 'ASSIGNED'
          AND pl.approval_status = 'APPROVED'
          AND NOT (t.end_time <= %s OR t.start_time >= %s)
        LIMIT 1
        """,
        (proxy_user_id, absence_date, proxy_id, start_time, end_time),
    )
    return cursor.fetchone()


def approve_mapped_proxy(cursor, proxy_user_id, note, approved_by, proxy_id):
    """Approve a pending request and store the substitute."""
    cursor.execute(
        """
        UPDATE proxy_log
        SET approval_status = 'APPROVED',
            status = 'ASSIGNED',
            proxy_faculty_id = %s,
            approval_date = NOW(),
            approved_by = %s,
            approval_notes = %s
        WHERE id = %s AND approval_status = 'PENDING'
        """,
        (proxy_user_id, approved_by, note, proxy_id),
    )
    return cursor.rowcount


def reject_pending_proxy(cursor, note, approved_by, proxy_id):
    """Reject a pending request without changing who was named."""
    cursor.execute(
        """
        UPDATE proxy_log
        SET approval_status = 'REJECTED',
            approval_date = NOW(),
            approved_by = %s,
            approval_notes = %s
        WHERE id = %s AND approval_status = 'PENDING'
        """,
        (approved_by, note, proxy_id),
    )
    return cursor.rowcount


def fetch_proxy_summary(cursor):
    """Return unfiltered proxy log counts."""
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
    return cursor.fetchone()
