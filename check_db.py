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
    
    print('Database connection successful!')
    print('Connected to database:', Config.MYSQL_DB or 'college_timetable')
    
    # Check if courses table exists and show its structure
    cursor.execute('DESCRIBE courses')
    courses_columns = cursor.fetchall()
    print('\nCurrent courses table structure:')
    for col in courses_columns:
        print(f'  {col[0]} - {col[1]}')
    
    # Check if subjects table exists and show its structure  
    cursor.execute('DESCRIBE subjects')
    subjects_columns = cursor.fetchall()
    print('\nCurrent subjects table structure:')
    for col in subjects_columns:
        print(f'  {col[0]} - {col[1]}')
    
    # Check what tables exist
    cursor.execute('SHOW TABLES')
    tables = cursor.fetchall()
    print('\nExisting tables:')
    for table in tables:
        print(f'  {table[0]}')
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f'Database error: {str(e)}')