#!/usr/bin/env python3
"""
Create sample proxy log data for testing
"""

import mysql.connector
import sys
import os
from datetime import datetime, date, timedelta

# Add the parent directory to Python path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config

def get_db_connection():
    """Get database connection using app config"""
    try:
        connection = mysql.connector.connect(
            host=Config.MYSQL_HOST,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            database=Config.MYSQL_DB,
            autocommit=False
        )
        return connection
    except mysql.connector.Error as e:
        print(f"❌ Database connection failed: {e}")
        sys.exit(1)

def create_sample_data():
    """Create sample proxy log data"""
    print("🚀 Creating Sample Proxy Log Data")
    print("=" * 40)
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # First, let's check what faculty and timetable data we have
        cursor.execute("SELECT user_id, name FROM faculty")
        faculty_data = cursor.fetchall()
        
        cursor.execute("SELECT id, faculty_id, subject_id, day_of_week, start_time, end_time FROM timetable LIMIT 5")
        timetable_data = cursor.fetchall()
        
        print(f"📊 Available Faculty: {len(faculty_data)}")
        for user_id, name in faculty_data:
            print(f"   • {name} (user_id: {user_id})")
        
        print(f"📊 Available Timetable Entries: {len(timetable_data)}")
        for tt_id, faculty_id, subject_id, day, start_time, end_time in timetable_data:
            print(f"   • Timetable ID: {tt_id}, Faculty: {faculty_id}, Subject: {subject_id}, {day} {start_time}-{end_time}")
        
        if not faculty_data or not timetable_data:
            print("⚠️ Not enough data to create proxy log entries. Need faculty and timetable records.")
            return
        
        # Create some sample proxy log entries
        print("\n📝 Creating sample proxy log entries...")
        
        # Sample data for proxy logs
        sample_data = [
            {
                'original_faculty_id': faculty_data[0][0],  # First faculty user_id
                'proxy_faculty_id': faculty_data[1][0] if len(faculty_data) > 1 else None,  # Second faculty user_id
                'timetable_id': timetable_data[0][0],  # First timetable entry
                'absence_date': date.today() - timedelta(days=5),
                'status': 'ASSIGNED',
                'approval_status': 'APPROVED',
                'approved_by': 1,  # Assuming admin user with ID 1
                'approval_date': datetime.now() - timedelta(days=4),
                'approval_notes': 'Approved by admin - proxy available'
            },
            {
                'original_faculty_id': faculty_data[0][0],  # First faculty user_id
                'proxy_faculty_id': None,  # No proxy assigned
                'timetable_id': timetable_data[1][0] if len(timetable_data) > 1 else timetable_data[0][0],
                'absence_date': date.today() - timedelta(days=3),
                'status': 'UNASSIGNED',
                'approval_status': 'PENDING',
                'approved_by': None,
                'approval_date': None,
                'approval_notes': None
            },
            {
                'original_faculty_id': faculty_data[1][0] if len(faculty_data) > 1 else faculty_data[0][0],
                'proxy_faculty_id': faculty_data[0][0],  # First faculty as proxy
                'timetable_id': timetable_data[2][0] if len(timetable_data) > 2 else timetable_data[0][0],
                'absence_date': date.today() - timedelta(days=1),
                'status': 'ASSIGNED',
                'approval_status': 'REJECTED',
                'approved_by': 1,
                'approval_date': datetime.now() - timedelta(hours=12),
                'approval_notes': 'Rejected - proxy not available during this time'
            }
        ]
        
        for i, data in enumerate(sample_data, 1):
            try:
                cursor.execute("""
                    INSERT INTO proxy_log (
                        original_faculty_id, proxy_faculty_id, timetable_id, absence_date,
                        status, approval_status, approved_by, approval_date, approval_notes
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    data['original_faculty_id'],
                    data['proxy_faculty_id'],
                    data['timetable_id'],
                    data['absence_date'],
                    data['status'],
                    data['approval_status'],
                    data['approved_by'],
                    data['approval_date'],
                    data['approval_notes']
                ))
                print(f"   ✅ Created sample proxy log entry {i}")
            except mysql.connector.Error as e:
                print(f"   ❌ Failed to create entry {i}: {e}")
        
        # Commit the changes
        connection.commit()
        print("\n✅ Sample data creation completed!")
        
        # Verify the data was created
        cursor.execute("SELECT COUNT(*) FROM proxy_log")
        count = cursor.fetchone()[0]
        print(f"📊 Total proxy log entries: {count}")
        
    except mysql.connector.Error as e:
        connection.rollback()
        print(f"❌ Sample data creation failed: {e}")
    
    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    print("Sample Proxy Log Data Creator")
    print("This will create sample proxy log entries for testing")
    
    response = input("\nDo you want to proceed? (y/N): ").strip().lower()
    if response in ['y', 'yes']:
        create_sample_data()
    else:
        print("Sample data creation cancelled.")