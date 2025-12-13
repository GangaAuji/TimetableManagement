#!/usr/bin/env python3
"""
Test script to verify the migration worked correctly
"""

import mysql.connector
import sys
import os

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

def test_migration():
    """Test the migration results"""
    print("🧪 Testing Migration Results")
    print("=" * 40)
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Test 1: Check faculty structure
        print("1️⃣ Testing faculty table structure...")
        cursor.execute("DESCRIBE faculty")
        faculty_columns = [row['Field'] for row in cursor.fetchall()]
        
        required_columns = ['user_id', 'employee_id', 'name', 'email']
        missing_columns = [col for col in required_columns if col not in faculty_columns]
        
        if missing_columns:
            print(f"   ❌ Missing columns: {missing_columns}")
        else:
            print("   ✅ All required columns present")
        
        # Test 2: Check students structure
        print("2️⃣ Testing students table structure...")
        cursor.execute("DESCRIBE students")
        student_columns = [row['Field'] for row in cursor.fetchall()]
        
        required_columns = ['user_id', 'admission_id', 'name', 'email']
        missing_columns = [col for col in required_columns if col not in student_columns]
        
        if missing_columns:
            print(f"   ❌ Missing columns: {missing_columns}")
        else:
            print("   ✅ All required columns present")
        
        # Test 3: Check unique constraints
        print("3️⃣ Testing unique constraints...")
        
        # Check for duplicate employee_ids
        cursor.execute("SELECT employee_id, COUNT(*) FROM faculty GROUP BY employee_id HAVING COUNT(*) > 1")
        dup_emp = cursor.fetchall()
        if dup_emp:
            print(f"   ❌ Duplicate employee_ids found: {dup_emp}")
        else:
            print("   ✅ No duplicate employee_ids")
        
        # Check for duplicate admission_ids
        cursor.execute("SELECT admission_id, COUNT(*) FROM students GROUP BY admission_id HAVING COUNT(*) > 1")
        dup_adm = cursor.fetchall()
        if dup_adm:
            print(f"   ❌ Duplicate admission_ids found: {dup_adm}")
        else:
            print("   ✅ No duplicate admission_ids")
        
        # Test 4: Check user mapping
        print("4️⃣ Testing user-to-faculty/student mapping...")
        
        # Test faculty mapping
        cursor.execute("""
            SELECT f.name, f.employee_id, u.username, u.role 
            FROM faculty f 
            JOIN users u ON f.user_id = u.id 
            WHERE u.role = 'Teacher'
        """)
        faculty_mappings = cursor.fetchall()
        
        print("   👨‍🏫 Faculty mappings:")
        for mapping in faculty_mappings:
            print(f"     • {mapping['name']} ({mapping['employee_id']}) ↔ {mapping['username']} ({mapping['role']})")
        
        # Test student mapping
        cursor.execute("""
            SELECT s.name, s.admission_id, u.username, u.role 
            FROM students s 
            JOIN users u ON s.user_id = u.id 
            WHERE u.role = 'Student'
        """)
        student_mappings = cursor.fetchall()
        
        print("   🎓 Student mappings:")
        for mapping in student_mappings:
            print(f"     • {mapping['name']} ({mapping['admission_id']}) ↔ {mapping['username']} ({mapping['role']})")
        
        # Test 5: Test login simulation
        print("5️⃣ Simulating teacher login...")
        
        # Simulate login for a teacher
        cursor.execute("SELECT id, username, role FROM users WHERE role = 'Teacher' LIMIT 1")
        teacher_user = cursor.fetchone()
        
        if teacher_user:
            user_id = teacher_user['id']
            username = teacher_user['username']
            
            # Try to get faculty profile
            cursor.execute("SELECT id, name, email, department_id FROM faculty WHERE user_id = %s", (user_id,))
            faculty_profile = cursor.fetchone()
            
            if faculty_profile:
                print(f"   ✅ Login simulation successful for {username}")
                print(f"      Faculty ID: {faculty_profile['id']}")
                print(f"      Faculty Name: {faculty_profile['name']}")
                print(f"      User ID: {user_id}")
            else:
                print(f"   ❌ No faculty profile found for user {username} (ID: {user_id})")
        else:
            print("   ⚠️ No teacher users found")
        
        print("\n🎉 Migration test completed!")
        
    except mysql.connector.Error as e:
        print(f"❌ Test failed: {e}")
    
    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    test_migration()