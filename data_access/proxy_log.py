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
