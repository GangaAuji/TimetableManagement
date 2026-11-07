"""Academic year SQL. Callers pass a cursor; this module does not read the request."""


def fetch_academic_years(cursor):
    """Return academic years, newest start date first."""
    cursor.execute("""
            SELECT * FROM academic_years 
            ORDER BY start_date DESC
        """)
    return cursor.fetchall()


def clear_current_academic_years(cursor, except_id=None):
    """Unmark the current year, leaving one row marked when an id is given."""
    if except_id is None:
        cursor.execute("UPDATE academic_years SET is_current = 0")
        return
    cursor.execute("UPDATE academic_years SET is_current = 0 WHERE id != %s", (except_id,))


def insert_academic_year(cursor, name, start_date, end_date, is_current, description):
    """Insert one academic year."""
    cursor.execute("""
            INSERT INTO academic_years (name, start_date, end_date, is_current, description)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, start_date, end_date, is_current, description))


def update_academic_year(cursor, year_id, name, start_date, end_date, is_current, description):
    """Update one academic year."""
    cursor.execute("""
            UPDATE academic_years 
            SET name = %s, start_date = %s, end_date = %s, is_current = %s, description = %s
            WHERE id = %s
        """, (name, start_date, end_date, is_current, description, year_id))


def delete_academic_year(cursor, year_id):
    """Delete one academic year."""
    cursor.execute("DELETE FROM academic_years WHERE id = %s", (year_id,))
