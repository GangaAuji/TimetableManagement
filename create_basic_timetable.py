#!/usr/bin/env python3
"""
Create basic timetable entries for testing proxy log functionality
"""

import mysql.connector
import sys
import os
from datetime import time

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

def create_basic_timetable():
    """Create basic timetable entries"""
    print("🚀 Creating Basic Timetable Data")
    print("=" * 40)
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Check available data
        cursor.execute("SELECT id, name FROM courses LIMIT 3")
        courses = cursor.fetchall()
        
        cursor.execute("SELECT id, name FROM classes LIMIT 3")
        classes = cursor.fetchall()
        
        cursor.execute("SELECT id, name FROM divisions LIMIT 3")
        divisions = cursor.fetchall()
        
        cursor.execute("SELECT id, name FROM subjects LIMIT 3")
        subjects = cursor.fetchall()
        
        cursor.execute("SELECT user_id, name FROM faculty")
        faculty = cursor.fetchall()
        
        print(f"📊 Available Data:")
        print(f"   • Courses: {len(courses)}")
        print(f"   • Classes: {len(classes)}")
        print(f"   • Divisions: {len(divisions)}")
        print(f"   • Subjects: {len(subjects)}")
        print(f"   • Faculty: {len(faculty)}")
        
        if not all([courses, classes, divisions, subjects, faculty]):
            print("❌ Missing required data. Need courses, classes, divisions, subjects, and faculty.")
            return
        
        # Create sample timetable entries
        timetable_entries = [
            {
                'course_id': courses[0][0],
                'class_id': classes[0][0],
                'division_id': divisions[0][0],
                'day_of_week': 'Monday',
                'start_time': time(9, 0),
                'end_time': time(10, 0),
                'subject_id': subjects[0][0],
                'faculty_id': faculty[0][0]
            },
            {
                'course_id': courses[0][0],
                'class_id': classes[0][0],
                'division_id': divisions[0][0],
                'day_of_week': 'Tuesday',
                'start_time': time(10, 0),
                'end_time': time(11, 0),
                'subject_id': subjects[1][0] if len(subjects) > 1 else subjects[0][0],
                'faculty_id': faculty[0][0]
            },
            {
                'course_id': courses[0][0],
                'class_id': classes[0][0],
                'division_id': divisions[0][0],
                'day_of_week': 'Wednesday',
                'start_time': time(11, 0),
                'end_time': time(12, 0),
                'subject_id': subjects[2][0] if len(subjects) > 2 else subjects[0][0],
                'faculty_id': faculty[1][0] if len(faculty) > 1 else faculty[0][0]
            }
        ]
        
        print("\n📝 Creating timetable entries...")
        for i, entry in enumerate(timetable_entries, 1):
            try:
                cursor.execute("""
                    INSERT INTO timetable (
                        course_id, class_id, division_id, day_of_week,
                        start_time, end_time, subject_id, faculty_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    entry['course_id'],
                    entry['class_id'],
                    entry['division_id'],
                    entry['day_of_week'],
                    entry['start_time'],
                    entry['end_time'],
                    entry['subject_id'],
                    entry['faculty_id']
                ))
                print(f"   ✅ Created timetable entry {i}: {entry['day_of_week']} {entry['start_time']}-{entry['end_time']}")
            except mysql.connector.Error as e:
                print(f"   ❌ Failed to create entry {i}: {e}")
        
        connection.commit()
        
        # Verify creation
        cursor.execute("SELECT COUNT(*) FROM timetable")
        count = cursor.fetchone()[0]
        print(f"\n✅ Timetable creation completed!")
        print(f"📊 Total timetable entries: {count}")
        
    except mysql.connector.Error as e:
        connection.rollback()
        print(f"❌ Timetable creation failed: {e}")
    
    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    create_basic_timetable()