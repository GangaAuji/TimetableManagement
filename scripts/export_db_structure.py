import mysql.connector
from config import Config
import json
from datetime import datetime

try:
    conn = mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB,
        autocommit=False
    )
    cursor = conn.cursor()
    
    print("="*80)
    print("EXPORTING CURRENT DATABASE STRUCTURE")
    print("="*80)
    
    # Get all base tables and views with type metadata
    cursor.execute(
        """
        SELECT TABLE_NAME, TABLE_TYPE
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = %s
        ORDER BY TABLE_NAME
        """,
        (Config.MYSQL_DB,)
    )
    tables = cursor.fetchall()
    
    export_data = {
        'export_date': datetime.now().isoformat(),
        'database': Config.MYSQL_DB,
        'tables': {}
    }
    
    for table_name, table_type in tables:
        print(f"\n--- Table: {table_name} ---")
        print(f"Type: {table_type}")
        
        # Get table structure
        safe_table_name = table_name.replace('`', '``')
        cursor.execute(f"DESCRIBE `{safe_table_name}`")
        columns = cursor.fetchall()
        
        table_info = {
            'columns': [],
            'foreign_keys': [],
            'indexes': [],
            'sample_count': 0
        }
        
        print("Columns:")
        for col in columns:
            col_info = {
                'name': col[0],
                'type': col[1],
                'null': col[2],
                'key': col[3],
                'default': col[4],
                'extra': col[5]
            }
            table_info['columns'].append(col_info)
            print(f"  {col[0]}: {col[1]} {'NULL' if col[2] == 'YES' else 'NOT NULL'} {col[3]} {col[5]}")
        
        # Get foreign keys
        cursor.execute(f"""
            SELECT 
                CONSTRAINT_NAME,
                COLUMN_NAME,
                REFERENCED_TABLE_NAME,
                REFERENCED_COLUMN_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = %s
            AND TABLE_NAME = %s
            AND REFERENCED_TABLE_NAME IS NOT NULL
        """, (Config.MYSQL_DB, table_name))
        fks = cursor.fetchall()
        if fks:
            print("Foreign Keys:")
            for fk in fks:
                fk_info = {
                    'constraint': fk[0],
                    'column': fk[1],
                    'ref_table': fk[2],
                    'ref_column': fk[3]
                }
                table_info['foreign_keys'].append(fk_info)
                print(f"  {fk[1]} -> {fk[2]}.{fk[3]}")
        
        # Get row count
        try:
            if table_type.upper() == 'BASE TABLE':
                cursor.execute(f"SELECT COUNT(*) FROM `{safe_table_name}`")
                count = cursor.fetchone()[0]
            else:
                count = "N/A (view)"
                print("Row count skipped for view")
        except Exception as e:
            count = f"Error: {str(e)}"
            print(f"Warning: Could not get row count - {e}")
        table_info['sample_count'] = count
        print(f"Row count: {count}")
        
        export_data['tables'][table_name] = table_info
    
    # Save to JSON file
    with open('database_export.json', 'w') as f:
        json.dump(export_data, f, indent=2, default=str)
    
    print("\n" + "="*80)
    print("EXPORT COMPLETED!")
    print(f"Total Tables: {len(tables)}")
    print(f"Export saved to: database_export.json")
    print("="*80)
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"Error: {str(e)}")
    import traceback
    traceback.print_exc()