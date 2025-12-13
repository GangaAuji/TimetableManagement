"""Create test data to verify approval buttons"""
import mysql.connector
from config import Config
from datetime import datetime, timedelta

conn = mysql.connector.connect(
    host=Config.MYSQL_HOST,
    user=Config.MYSQL_USER,
    password=Config.MYSQL_PASSWORD,
    database=Config.MYSQL_DB
)
cursor = conn.cursor()

# Create PENDING proxy request
cursor.execute('SELECT id FROM timetable WHERE faculty_id=2 LIMIT 1')
tt_row = cursor.fetchone()

if tt_row:
    test_date = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')
    cursor.execute(
        'INSERT INTO proxy_log (original_faculty_id, timetable_id, absence_date, status, approval_status) VALUES (2, %s, %s, %s, %s)',
        (tt_row[0], test_date, 'PENDING', 'PENDING')
    )
    conn.commit()
    print(f'✅ Created PENDING proxy request for faculty_id=2 on {test_date}')
else:
    print('❌ No timetable found for faculty_id=2')

cursor.close()
conn.close()

print('\n' + '='*60)
print('NOW REFRESH THE ADMIN FACULTY DETAILS PAGE')
print('='*60)
print('You should see:')
print('1. Absences tab: UNPROCESSED absence with Approve/Reject/Delete buttons')
print('2. Proxy Log tab: PENDING request with Approve/Reject buttons')
print('='*60)
