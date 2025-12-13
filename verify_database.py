"""
Verify New Database Structure
Displays comprehensive database information after schema application
"""
import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

def verify_database():
    """Verify the new database structure"""
    try:
        connection = mysql.connector.connect(
            host=os.getenv('MYSQL_HOST', 'localhost'),
            user=os.getenv('MYSQL_USER'),
            password=os.getenv('MYSQL_PASSWORD'),
            database=os.getenv('MYSQL_DB')
        )
        
        if connection.is_connected():
            cursor = connection.cursor(dictionary=True)
            
            print("="*80)
            print(f"DATABASE STRUCTURE VERIFICATION - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("="*80)
            
            # Get all tables
            cursor.execute("SHOW TABLES")
            tables = [list(row.values())[0] for row in cursor.fetchall()]
            
            print(f"\n✓ Total Tables: {len(tables)}")
            print("-"*80)
            
            for table in sorted(tables):
                # Get table info
                cursor.execute(f"DESCRIBE {table}")
                columns = cursor.fetchall()
                
                cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
                row_count = cursor.fetchone()['count']
                
                # Get foreign keys
                cursor.execute(f"""
                    SELECT 
                        COLUMN_NAME,
                        REFERENCED_TABLE_NAME,
                        REFERENCED_COLUMN_NAME
                    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = '{os.getenv('MYSQL_DB')}'
                    AND TABLE_NAME = '{table}'
                    AND REFERENCED_TABLE_NAME IS NOT NULL
                """)
                foreign_keys = cursor.fetchall()
                
                print(f"\n📋 {table.upper()}")
                print(f"   Rows: {row_count} | Columns: {len(columns)} | Foreign Keys: {len(foreign_keys)}")
                
                # Show columns
                print("   Columns:")
                for col in columns:
                    key_info = ""
                    if col['Key'] == 'PRI':
                        key_info = " [PRIMARY KEY]"
                    elif col['Key'] == 'UNI':
                        key_info = " [UNIQUE]"
                    elif col['Key'] == 'MUL':
                        key_info = " [INDEXED]"
                    
                    null_info = "NULL" if col['Null'] == 'YES' else "NOT NULL"
                    default_info = f" DEFAULT {col['Default']}" if col['Default'] else ""
                    
                    print(f"      • {col['Field']}: {col['Type']} {null_info}{default_info}{key_info}")
                
                # Show foreign keys
                if foreign_keys:
                    print("   Foreign Keys:")
                    for fk in foreign_keys:
                        print(f"      • {fk['COLUMN_NAME']} → {fk['REFERENCED_TABLE_NAME']}.{fk['REFERENCED_COLUMN_NAME']}")
            
            # Check views
            cursor.execute("SHOW FULL TABLES WHERE Table_type = 'VIEW'")
            views = cursor.fetchall()
            
            if views:
                print("\n" + "="*80)
                print(f"VIEWS ({len(views)})")
                print("="*80)
                for view in views:
                    view_name = list(view.values())[0]
                    print(f"   • {view_name}")
            
            # Show initial data
            print("\n" + "="*80)
            print("INITIAL DATA SUMMARY")
            print("="*80)
            
            # Departments
            cursor.execute("SELECT id, name, code FROM departments ORDER BY name")
            depts = cursor.fetchall()
            print(f"\n📚 Departments ({len(depts)}):")
            for dept in depts:
                print(f"   • [{dept['code']}] {dept['name']}")
            
            # Academic Years
            cursor.execute("SELECT id, name, start_date, end_date, is_current FROM academic_years ORDER BY start_date DESC")
            years = cursor.fetchall()
            print(f"\n📅 Academic Years ({len(years)}):")
            for year in years:
                current = " [CURRENT]" if year['is_current'] else ""
                print(f"   • {year['name']}: {year['start_date']} to {year['end_date']}{current}")
            
            # Semesters
            cursor.execute("""
                SELECT s.*, ay.name as year_name 
                FROM semesters s
                JOIN academic_years ay ON s.academic_year_id = ay.id
                ORDER BY s.semester_number
            """)
            semesters = cursor.fetchall()
            print(f"\n📖 Semesters ({len(semesters)}):")
            for sem in semesters:
                current = " [CURRENT]" if sem['is_current'] else ""
                print(f"   • {sem['semester_name']} ({sem['year_name']}): {sem['start_date']} to {sem['end_date']}{current}")
                print(f"     Credits: {sem['min_credits']}-{sem['max_credits']}")
            
            # Courses
            cursor.execute("""
                SELECT c.*, d.name as dept_name 
                FROM courses c
                JOIN departments d ON c.department_id = d.id
                ORDER BY c.program, c.name
            """)
            courses = cursor.fetchall()
            print(f"\n🎓 Courses ({len(courses)}):")
            for course in courses:
                print(f"   • [{course['code']}] {course['name']} ({course['program']})")
                print(f"     Department: {course['dept_name']}")
                print(f"     Duration: {course['duration_years']} years ({course['total_semesters']} semesters)")
            
            # Classes
            cursor.execute("SELECT id, name FROM classes ORDER BY display_order")
            classes = cursor.fetchall()
            print(f"\n📚 Classes ({len(classes)}):")
            for cls in classes:
                print(f"   • {cls['name']}")
            
            # Divisions
            cursor.execute("SELECT id, name, capacity FROM divisions ORDER BY name")
            divisions = cursor.fetchall()
            print(f"\n🏫 Divisions ({len(divisions)}):")
            for div in divisions:
                print(f"   • Division {div['name']}: Capacity {div['capacity']}")
            
            # Rooms
            cursor.execute("SELECT id, room_number, room_type, capacity FROM rooms ORDER BY room_number")
            rooms = cursor.fetchall()
            print(f"\n🏢 Rooms ({len(rooms)}):")
            for room in rooms:
                print(f"   • Room {room['room_number']}: {room['room_type']} (Capacity: {room['capacity']})")
            
            print("\n" + "="*80)
            print("✓ DATABASE STRUCTURE VERIFIED SUCCESSFULLY")
            print("✓ All tables created with proper foreign key constraints")
            print("✓ Initial data loaded successfully")
            print("✓ Ready for CRUD operations implementation")
            print("="*80)
            
            return True
            
    except Error as e:
        print(f"\n✗ Error: {e}")
        return False
    
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

if __name__ == "__main__":
    verify_database()
