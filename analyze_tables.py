import mysql.connector
from config import Config

try:
    conn = mysql.connector.connect(
        host=Config.MYSQL_HOST or 'localhost',
        user=Config.MYSQL_USER or 'root',
        password=Config.MYSQL_PASSWORD or '',
        database=Config.MYSQL_DB or 'college_timetable'
    )
    cursor = conn.cursor()
    
    print('=== EXISTING ACADEMIC TABLES ANALYSIS ===')
    
    # Check academic_years table
    try:
        cursor.execute('DESCRIBE academic_years')
        columns = cursor.fetchall()
        print('\nACUDEMIC_YEARS table structure:')
        for col in columns:
            print(f'  {col[0]} - {col[1]}')
    except:
        print('\nACUDEMIC_YEARS table does not exist')
    
    # Check academic_terms table
    try:
        cursor.execute('DESCRIBE academic_terms')
        columns = cursor.fetchall()
        print('\nACUDEMIC_TERMS table structure:')
        for col in columns:
            print(f'  {col[0]} - {col[1]}')
    except:
        print('\nACUDEMIC_TERMS table does not exist')
    
    # Check faculty_allocations table
    try:
        cursor.execute('DESCRIBE faculty_allocations')
        columns = cursor.fetchall()
        print('\nFACULTY_ALLOCATIONS table structure:')
        for col in columns:
            print(f'  {col[0]} - {col[1]}')
    except:
        print('\nFACULTY_ALLOCATIONS table does not exist')
    
    # Check classes table
    try:
        cursor.execute('DESCRIBE classes')
        columns = cursor.fetchall()
        print('\nCLASSES table structure:')
        for col in columns:
            print(f'  {col[0]} - {col[1]}')
    except:
        print('\nCLASSES table does not exist')
    
    # Check timetable table
    try:
        cursor.execute('DESCRIBE timetable')
        columns = cursor.fetchall()
        print('\nTIMETABLE table structure:')
        for col in columns:
            print(f'  {col[0]} - {col[1]}')
    except:
        print('\nTIMETABLE table does not exist')
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f'Database error: {str(e)}')