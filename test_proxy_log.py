#!/usr/bin/env python3
"""
Test script to verify proxy log backend functionality
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

def test_proxy_log_query():
    """Test the proxy log query used in the backend"""
    print("🧪 Testing Proxy Log Query")
    print("=" * 40)
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Test the main query from the backend
        query = """
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
            ORDER BY pl.absence_date DESC, t.start_time ASC
            LIMIT 5
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        print(f"✅ Query executed successfully")
        print(f"📊 Found {len(results)} proxy log records")
        
        if results:
            print("\n📋 Sample Records:")
            for i, row in enumerate(results, 1):
                print(f"\n   Record {i}:")
                print(f"   • Date: {row[1]}")
                print(f"   • Original Faculty: {row[6]} ({row[7]})")
                print(f"   • Proxy Faculty: {row[8] or 'None'} ({row[9] or 'N/A'})")
                print(f"   • Subject: {row[13]}")
                print(f"   • Class: {row[14]} ({row[15]})")
                print(f"   • Time: {row[11]} - {row[12]}")
                print(f"   • Status: {row[2]}")
                print(f"   • Approval: {row[3]}")
        else:
            print("   ⚠️ No proxy log records found in database")
        
        # Test summary statistics query
        print("\n📈 Testing Summary Statistics...")
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
        
        stats = cursor.fetchone()
        print(f"   • Total Records: {stats[0]}")
        print(f"   • Assigned: {stats[1]}")
        print(f"   • Unassigned: {stats[2]}")
        print(f"   • Pending Approval: {stats[3]}")
        print(f"   • Approved: {stats[4]}")
        print(f"   • Rejected: {stats[5]}")
        
        # Check if proxy_log table has the required columns
        print("\n🔍 Checking proxy_log table structure...")
        cursor.execute("DESCRIBE proxy_log")
        columns = [row[0] for row in cursor.fetchall()]
        
        required_columns = ['id', 'original_faculty_id', 'proxy_faculty_id', 'timetable_id', 
                          'absence_date', 'status', 'approval_status', 'approval_date', 
                          'approved_by', 'approval_notes']
        
        missing_columns = [col for col in required_columns if col not in columns]
        
        if missing_columns:
            print(f"   ❌ Missing columns in proxy_log: {missing_columns}")
            print("   💡 You may need to run the proxy log schema migration")
        else:
            print("   ✅ All required columns present in proxy_log table")
        
    except mysql.connector.Error as e:
        print(f"❌ Query test failed: {e}")
    
    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    test_proxy_log_query()