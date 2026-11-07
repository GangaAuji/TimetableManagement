"""Registration invitation SQL. Callers pass a cursor."""


def count_invitations(cursor, query_base, where_clause, params):
    """Return the invitation count."""
    cursor.execute(
        f"SELECT COUNT(ri.id) AS total {query_base}{where_clause}",
        tuple(params),
    )
    return cursor.fetchone()['total']


def fetch_invitations(cursor, query_base, where_clause, params, per_page, offset):
    """Return one page of invitations."""
    cursor.execute(
        f"""
        SELECT ri.id, ri.token, ri.email, ri.name, ri.role, ri.status,
               ri.created_at, ri.expires_at, ri.used_at,
               c.name as course_name, d.name as dept_name, u.username as created_by_username
        {query_base}{where_clause}
        ORDER BY ri.created_at DESC
        LIMIT %s OFFSET %s
    """,
        tuple(params) + (per_page, offset),
    )
    return cursor.fetchall()


def fetch_named_rows(cursor, table):
    """Return id and name rows from a fixed catalog table."""
    cursor.execute(f"SELECT id, name FROM {table} ORDER BY name")
    return cursor.fetchall()


def fetch_invitation_stats(cursor):
    """Return invitation status counts."""
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN status = 'pending' AND expires_at > NOW() THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN status = 'used' THEN 1 ELSE 0 END) as used,
            SUM(CASE WHEN status = 'expired' OR (status = 'pending' AND expires_at <= NOW()) THEN 1 ELSE 0 END) as expired,
            COUNT(*) as total
        FROM registration_invitations
    """)
    return cursor.fetchone()


def fetch_pending_invitation(cursor, email):
    """Return a live pending invitation for an email."""
    cursor.execute("""
        SELECT id FROM registration_invitations 
        WHERE email = %s AND status = 'pending' AND expires_at > NOW()
    """, (email,))
    return cursor.fetchone()


def fetch_registered_email(cursor, role, email):
    """Return a student or faculty row that already uses this email."""
    if role == 'Student':
        cursor.execute("SELECT id FROM students WHERE email = %s", (email,))
    else:
        cursor.execute("SELECT id FROM faculty WHERE email = %s", (email,))
    return cursor.fetchone()


def insert_invitation(cursor, values):
    """Insert one pending invitation."""
    cursor.execute("""
            INSERT INTO registration_invitations 
            (token, email, name, role, course_id, class_id, division_id, department_id, created_by, expires_at, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
        """, values)


def expire_invitation(cursor, invitation_id):
    """Expire a pending invitation."""
    cursor.execute("""
        UPDATE registration_invitations 
        SET status = 'expired' 
        WHERE id = %s AND status = 'pending'
    """, (invitation_id,))


def fetch_invitation_status(cursor, invitation_id):
    """Return the email and status of one invitation."""
    cursor.execute("SELECT email, status FROM registration_invitations WHERE id = %s", (invitation_id,))
    return cursor.fetchone()


def refresh_invitation(cursor, token, expires_at, invitation_id):
    """Store a new token and mark the invitation pending."""
    cursor.execute("""
        UPDATE registration_invitations 
        SET token = %s, expires_at = %s, status = 'pending' 
        WHERE id = %s
    """, (token, expires_at, invitation_id))


def fetch_invitation_token(cursor, invitation_id):
    """Return the token row for one invitation."""
    cursor.execute("SELECT token FROM registration_invitations WHERE id = %s", (invitation_id,))
    return cursor.fetchone()
