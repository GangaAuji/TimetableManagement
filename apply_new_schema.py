"""
Apply Complete Database Schema
Creates new comprehensive database structure with proper foreign key constraints
"""
import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def apply_schema():
    """Apply the complete database schema"""
    try:
        # Database connection
        connection = mysql.connector.connect(
            host=os.getenv('MYSQL_HOST', 'localhost'),
            user=os.getenv('MYSQL_USER'),
            password=os.getenv('MYSQL_PASSWORD'),
            database=os.getenv('MYSQL_DB')
        )
        
        if connection.is_connected():
            print("✓ Connected to MySQL database")
            cursor = connection.cursor()
            
            # Read SQL file
            sql_file = 'complete_database_schema.sql'
            print(f"\n✓ Reading SQL file: {sql_file}")
            
            with open(sql_file, 'r', encoding='utf-8') as file:
                sql_script = file.read()
            
            # Split into individual statements
            statements = []
            current_statement = []
            
            for line in sql_script.split('\n'):
                # Skip empty lines and comments
                line = line.strip()
                if not line or line.startswith('--'):
                    continue
                
                current_statement.append(line)
                
                # Execute when we hit a semicolon
                if line.endswith(';'):
                    statement = ' '.join(current_statement)
                    statements.append(statement)
                    current_statement = []
            
            print(f"\n✓ Found {len(statements)} SQL statements")
            print("\n" + "="*70)
            print("APPLYING DATABASE SCHEMA")
            print("="*70)
            
            success_count = 0
            error_count = 0
            
            # Execute each statement
            for i, statement in enumerate(statements, 1):
                try:
                    # Get statement type for logging
                    stmt_type = statement.split()[0].upper()
                    
                    if stmt_type == 'DROP':
                        table_name = statement.split('TABLE')[1].split('IF')[1].split('EXISTS')[1].split()[0] if 'IF EXISTS' in statement else statement.split('TABLE')[1].split()[0]
                        print(f"\n[{i}/{len(statements)}] Dropping table: {table_name}")
                    elif stmt_type == 'CREATE':
                        if 'TABLE' in statement:
                            table_name = statement.split('TABLE')[1].split('(')[0].strip()
                            print(f"\n[{i}/{len(statements)}] Creating table: {table_name}")
                        elif 'VIEW' in statement or 'OR REPLACE VIEW' in statement:
                            view_name = statement.split('VIEW')[1].split('AS')[0].strip()
                            print(f"\n[{i}/{len(statements)}] Creating view: {view_name}")
                    elif stmt_type == 'INSERT':
                        table_name = statement.split('INTO')[1].split('(')[0].strip()
                        print(f"\n[{i}/{len(statements)}] Inserting data into: {table_name}")
                    elif stmt_type == 'SET':
                        print(f"\n[{i}/{len(statements)}] Setting variable")
                    elif stmt_type == 'SELECT':
                        print(f"\n[{i}/{len(statements)}] Executing SELECT statement")
                    
                    # Execute statement
                    cursor.execute(statement)
                    success_count += 1
                    print(f"  ✓ Success")
                    
                except Error as e:
                    error_count += 1
                    print(f"  ✗ Error: {e}")
                    if "already exists" not in str(e).lower() and "doesn't exist" not in str(e).lower():
                        print(f"  Statement: {statement[:100]}...")
            
            # Commit changes
            connection.commit()
            
            print("\n" + "="*70)
            print("SCHEMA APPLICATION COMPLETE")
            print("="*70)
            print(f"\n✓ Successful statements: {success_count}")
            print(f"✗ Failed statements: {error_count}")
            
            # Get table counts
            print("\n" + "="*70)
            print("DATABASE SUMMARY")
            print("="*70)
            
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            print(f"\n✓ Total tables: {len(tables)}")
            
            # Show row counts for main tables
            print("\nRow counts:")
            for (table_name,) in sorted(tables):
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    count = cursor.fetchone()[0]
                    print(f"  • {table_name}: {count} rows")
                except:
                    pass
            
            print("\n✓ Database schema applied successfully!")
            print("✓ Ready for academic management operations")
            
    except Error as e:
        print(f"\n✗ Database Error: {e}")
        return False
    
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()
            print("\n✓ Database connection closed")
    
    return True

if __name__ == "__main__":
    print("="*70)
    print("COLLEGE TIMETABLE MANAGEMENT SYSTEM")
    print("Complete Database Schema Application")
    print("="*70)
    print("\nThis will:")
    print("  1. Drop all existing tables (if they exist)")
    print("  2. Create new comprehensive database schema")
    print("  3. Add proper foreign key constraints")
    print("  4. Insert initial/sample data")
    print("  5. Create useful views for reporting")
    print("\n⚠ WARNING: This will DELETE all existing data!")
    
    response = input("\nDo you want to proceed? (yes/no): ").strip().lower()
    
    if response == 'yes':
        print("\nProceeding with schema application...\n")
        apply_schema()
    else:
        print("\n✗ Operation cancelled by user")
