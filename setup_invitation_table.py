"""
Quick script to add the missing registration_invitations table
Run this script if you can't access MySQL directly
"""

import mysql.connector
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def add_registration_table():
    try:
        # Connect to database
        connection = mysql.connector.connect(
            host=os.getenv('MYSQL_HOST', 'localhost'),
            user=os.getenv('MYSQL_USER', 'root'),
            password=os.getenv('MYSQL_PASSWORD', ''),
            database=os.getenv('MYSQL_DB', 'college_timetable_db')
        )
        
        cursor = connection.cursor()
        
        # Check if table already exists
        cursor.execute("SHOW TABLES LIKE 'registration_invitations'")
        if cursor.fetchone():
            print("✅ Table 'registration_invitations' already exists!")
            return
        
        # Create the table
        create_table_sql = """
        CREATE TABLE `registration_invitations` (
          `id` INT AUTO_INCREMENT PRIMARY KEY,
          `token` VARCHAR(64) NOT NULL UNIQUE,
          `email` VARCHAR(100) NOT NULL,
          `role` ENUM('Teacher', 'Student') NOT NULL,
          `name` VARCHAR(100),
          `course_id` INT DEFAULT NULL,
          `class_id` INT DEFAULT NULL,
          `division_id` INT DEFAULT NULL,
          `department_id` INT DEFAULT NULL,
          `created_by` INT NOT NULL,
          `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          `expires_at` TIMESTAMP NOT NULL,
          `used_at` TIMESTAMP NULL DEFAULT NULL,
          `status` ENUM('pending', 'used', 'expired') DEFAULT 'pending',
          FOREIGN KEY (`created_by`) REFERENCES `users`(`id`) ON DELETE CASCADE,
          FOREIGN KEY (`course_id`) REFERENCES `courses`(`id`) ON DELETE SET NULL,
          FOREIGN KEY (`class_id`) REFERENCES `classes`(`id`) ON DELETE SET NULL,
          FOREIGN KEY (`division_id`) REFERENCES `divisions`(`id`) ON DELETE SET NULL,
          FOREIGN KEY (`department_id`) REFERENCES `departments`(`id`) ON DELETE SET NULL,
          INDEX idx_token (`token`),
          INDEX idx_email (`email`),
          INDEX idx_status (`status`),
          INDEX idx_expires (`expires_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        
        cursor.execute(create_table_sql)
        
        # Update users table to include Super Admin role
        try:
            cursor.execute("ALTER TABLE `users` MODIFY COLUMN `role` ENUM('Admin', 'Super Admin', 'Teacher', 'Student') NOT NULL")
            print("✅ Updated users table to include 'Super Admin' role")
        except mysql.connector.Error as e:
            if "Duplicate" in str(e):
                print("✅ Users table already has 'Super Admin' role")
            else:
                print(f"⚠️  Warning updating users table: {e}")
        
        connection.commit()
        print("✅ Successfully created 'registration_invitations' table!")
        
        # Verify table creation
        cursor.execute("DESCRIBE registration_invitations")
        columns = cursor.fetchall()
        print(f"✅ Table created with {len(columns)} columns")
        
    except mysql.connector.Error as error:
        print(f"❌ Error: {error}")
        
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()
            print("🔌 Database connection closed")

if __name__ == "__main__":
    print("🔄 Adding registration_invitations table...")
    add_registration_table()
    print("✨ Done! You can now use the invitation system.")