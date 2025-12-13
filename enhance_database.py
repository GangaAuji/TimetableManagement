import mysql.connector
from config import Config

# Enhanced Academic Management Database Upgrade
# This script enhances existing tables to support comprehensive academic management

def execute_sql_safely(cursor, sql, description):
    """Execute SQL with error handling"""
    try:
        cursor.execute(sql)
        print(f"✓ {description}")
        return True
    except mysql.connector.Error as e:
        if "Duplicate column name" in str(e) or "already exists" in str(e):
            print(f"- {description} (already exists)")
            return True
        else:
            print(f"✗ {description} - Error: {str(e)}")
            return False

try:
    conn = mysql.connector.connect(
        host=Config.MYSQL_HOST or 'localhost',
        user=Config.MYSQL_USER or 'root',
        password=Config.MYSQL_PASSWORD or '',
        database=Config.MYSQL_DB or 'college_timetable'
    )
    cursor = conn.cursor()
    
    print('=== ENHANCING ACADEMIC MANAGEMENT DATABASE ===\n')
    
    # 1. ENHANCE COURSES TABLE
    print('1. ENHANCING COURSES TABLE:')
    execute_sql_safely(cursor, 
        "ALTER TABLE courses ADD COLUMN duration_years INT DEFAULT 3 COMMENT 'Duration in years (3 for UG, 2 for PG)'",
        "Added duration_years column to courses")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE courses ADD COLUMN total_semesters INT DEFAULT 6 COMMENT 'Total semesters in the course'",
        "Added total_semesters column to courses")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE courses ADD COLUMN description TEXT COMMENT 'Course description'",
        "Added description column to courses")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE courses ADD COLUMN is_active BOOLEAN DEFAULT TRUE COMMENT 'Course active status'",
        "Added is_active column to courses")
    
    # Update existing courses with default values
    execute_sql_safely(cursor, """
        UPDATE courses SET 
            duration_years = CASE 
                WHEN program = 'UG' THEN 3 
                WHEN program = 'PG' THEN 2 
                ELSE 3 
            END,
            total_semesters = CASE 
                WHEN program = 'UG' THEN 6 
                WHEN program = 'PG' THEN 4 
                ELSE 6 
            END,
            is_active = TRUE
        WHERE duration_years IS NULL OR total_semesters IS NULL
    """, "Updated existing courses with enhanced data")
    
    # 2. CREATE SEMESTERS TABLE (enhanced version of academic_terms)
    print('\n2. CREATING SEMESTERS TABLE:')
    execute_sql_safely(cursor, """
        CREATE TABLE IF NOT EXISTS semesters (
            id INT AUTO_INCREMENT PRIMARY KEY,
            academic_year_id INT NOT NULL,
            semester_number TINYINT NOT NULL COMMENT 'Semester number (1-8)',
            semester_name VARCHAR(50) NOT NULL COMMENT 'e.g., Semester I, Semester II',
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            is_current BOOLEAN DEFAULT FALSE COMMENT 'Current active semester',
            min_credits DECIMAL(4,1) DEFAULT 18.0 COMMENT 'Minimum credits required',
            max_credits DECIMAL(4,1) DEFAULT 30.0 COMMENT 'Maximum credits allowed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (academic_year_id) REFERENCES academic_years(id) ON DELETE CASCADE,
            UNIQUE KEY unique_semester_per_year (academic_year_id, semester_number)
        )
    """, "Created semesters table")
    
    # 3. CREATE COURSE BATCHES TABLE
    print('\n3. CREATING COURSE BATCHES TABLE:')
    execute_sql_safely(cursor, """
        CREATE TABLE IF NOT EXISTS course_batches (
            id INT AUTO_INCREMENT PRIMARY KEY,
            course_id INT NOT NULL,
            batch_name VARCHAR(50) NOT NULL COMMENT 'e.g., MSC DA 2024-26, BCA 2023-26',
            academic_year_id INT NULL COMMENT 'Academic year when batch started',
            start_year YEAR NOT NULL COMMENT 'Batch start year',
            end_year YEAR NOT NULL COMMENT 'Expected completion year',
            total_students INT DEFAULT 0 COMMENT 'Total enrolled students',
            current_semester TINYINT DEFAULT 1 COMMENT 'Current semester of the batch',
            is_active BOOLEAN DEFAULT TRUE COMMENT 'Active batch status',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            FOREIGN KEY (academic_year_id) REFERENCES academic_years(id) ON DELETE SET NULL,
            UNIQUE KEY unique_batch_per_course (course_id, batch_name)
        )
    """, "Created course_batches table")
    
    # 4. ENHANCE SUBJECTS TABLE
    print('\n4. ENHANCING SUBJECTS TABLE:')
    execute_sql_safely(cursor, 
        "ALTER TABLE subjects ADD COLUMN course_code VARCHAR(20) COMMENT 'e.g., MCA-601, BCA-301'",
        "Added course_code column to subjects")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE subjects ADD COLUMN semester_id INT COMMENT 'Links to semesters table'",
        "Added semester_id column to subjects")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE subjects ADD COLUMN course_type ENUM('Core', 'Elective', 'Core Practical', 'Elective Practical', 'Project', 'Internship', 'Dissertation') DEFAULT 'Core'",
        "Added course_type column to subjects")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE subjects ADD COLUMN theory_practical ENUM('Theory', 'Practical', 'Both') DEFAULT 'Theory'",
        "Added theory_practical column to subjects")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE subjects ADD COLUMN credits DECIMAL(3,1) NOT NULL DEFAULT 3.0 COMMENT 'Total credits'",
        "Added credits column to subjects")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE subjects ADD COLUMN theory_credits DECIMAL(3,1) DEFAULT 0 COMMENT 'Theory credits'",
        "Added theory_credits column to subjects")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE subjects ADD COLUMN practical_credits DECIMAL(3,1) DEFAULT 0 COMMENT 'Practical credits'",
        "Added practical_credits column to subjects")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE subjects ADD COLUMN marks INT DEFAULT 100 COMMENT 'Total marks'",
        "Added marks column to subjects")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE subjects ADD COLUMN lectures_per_week TINYINT DEFAULT 3 COMMENT 'Weekly lecture hours'",
        "Added lectures_per_week column to subjects")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE subjects ADD COLUMN is_elective BOOLEAN DEFAULT FALSE COMMENT 'Subject is elective'",
        "Added is_elective column to subjects")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE subjects ADD COLUMN description TEXT COMMENT 'Subject description'",
        "Added description column to subjects")
    
    # Update existing subjects with default values
    execute_sql_safely(cursor, """
        UPDATE subjects 
        SET course_code = CONCAT('SUBJ-', LPAD(id, 3, '0')),
            credits = 3.0,
            theory_credits = 3.0,
            marks = 100,
            lectures_per_week = 3,
            description = name
        WHERE course_code IS NULL
    """, "Updated existing subjects with enhanced data")
    
    # 5. ENHANCE FACULTY ALLOCATIONS TABLE
    print('\n5. ENHANCING FACULTY ALLOCATIONS TABLE:')
    execute_sql_safely(cursor, 
        "ALTER TABLE faculty_allocations ADD COLUMN semester_id INT COMMENT 'Current semester allocation'",
        "Added semester_id to faculty_allocations")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE faculty_allocations ADD COLUMN course_batch_id INT COMMENT 'Specific batch allocation'",
        "Added course_batch_id to faculty_allocations")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE faculty_allocations ADD COLUMN allocated_hours DECIMAL(4,1) DEFAULT 3.0 COMMENT 'Weekly allocated hours'",
        "Added allocated_hours to faculty_allocations")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE faculty_allocations ADD COLUMN workload_percentage DECIMAL(5,2) DEFAULT 100.0 COMMENT 'Percentage of subject workload'",
        "Added workload_percentage to faculty_allocations")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE faculty_allocations ADD COLUMN is_primary BOOLEAN DEFAULT TRUE COMMENT 'Primary faculty for subject'",
        "Added is_primary to faculty_allocations")
    
    # 6. ENHANCE TIMETABLE TABLE
    print('\n6. ENHANCING TIMETABLE TABLE:')
    execute_sql_safely(cursor, 
        "ALTER TABLE timetable ADD COLUMN academic_year_id INT COMMENT 'Academic year for timetable'",
        "Added academic_year_id to timetable")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE timetable ADD COLUMN semester_id INT COMMENT 'Semester for timetable'",
        "Added semester_id to timetable")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE timetable ADD COLUMN course_batch_id INT COMMENT 'Specific batch timetable'",
        "Added course_batch_id to timetable")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE timetable ADD COLUMN room_number VARCHAR(20) COMMENT 'Classroom/lab assignment'",
        "Added room_number to timetable")
    
    execute_sql_safely(cursor, 
        "ALTER TABLE timetable ADD COLUMN is_active BOOLEAN DEFAULT TRUE COMMENT 'Timetable entry active status'",
        "Added is_active to timetable")
    
    # 7. CREATE ELECTIVE GROUPS TABLE
    print('\n7. CREATING ELECTIVE GROUPS TABLE:')
    execute_sql_safely(cursor, """
        CREATE TABLE IF NOT EXISTS elective_groups (
            id INT AUTO_INCREMENT PRIMARY KEY,
            group_name VARCHAR(100) NOT NULL,
            course_id INT NOT NULL,
            semester_id INT NOT NULL,
            min_subjects_to_choose TINYINT DEFAULT 1 COMMENT 'Minimum subjects student must choose',
            max_subjects_to_choose TINYINT DEFAULT 1 COMMENT 'Maximum subjects student can choose',
            total_credits DECIMAL(4,1) DEFAULT 0 COMMENT 'Total credits for this group',
            description TEXT COMMENT 'Group description and selection criteria',
            is_mandatory BOOLEAN DEFAULT TRUE COMMENT 'Students must select from this group',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE CASCADE,
            UNIQUE KEY unique_group_per_semester (course_id, semester_id, group_name)
        )
    """, "Created elective_groups table")
    
    # 8. INSERT SAMPLE DATA
    print('\n8. INSERTING SAMPLE DATA:')
    
    # Get current academic year
    cursor.execute("SELECT id FROM academic_years WHERE is_current = 1 LIMIT 1")
    result = cursor.fetchone()
    if result:
        academic_year_id = result[0]
        print(f"Found current academic year ID: {academic_year_id}")
    else:
        # Create a current academic year if none exists
        execute_sql_safely(cursor, """
            INSERT INTO academic_years (name, start_date, end_date, is_current) 
            VALUES ('2024-25', '2024-07-01', '2025-06-30', TRUE)
        """, "Created default academic year 2024-25")
        
        cursor.execute("SELECT LAST_INSERT_ID()")
        academic_year_id = cursor.fetchone()[0]
    
    # Insert sample semesters
    execute_sql_safely(cursor, f"""
        INSERT IGNORE INTO semesters (academic_year_id, semester_number, semester_name, start_date, end_date, is_current, min_credits, max_credits) VALUES
        ({academic_year_id}, 1, 'Semester I', '2024-07-01', '2024-11-30', TRUE, 18.0, 26.0),
        ({academic_year_id}, 2, 'Semester II', '2024-12-01', '2025-04-30', FALSE, 18.0, 26.0),
        ({academic_year_id}, 3, 'Semester III', '2024-07-01', '2024-11-30', FALSE, 20.0, 28.0),
        ({academic_year_id}, 4, 'Semester IV', '2024-12-01', '2025-04-30', FALSE, 20.0, 28.0)
    """, "Inserted sample semesters")
    
    # Create sample course batches for existing courses
    execute_sql_safely(cursor, f"""
        INSERT IGNORE INTO course_batches (course_id, batch_name, academic_year_id, start_year, end_year, total_students, current_semester) 
        SELECT 
            c.id, 
            CONCAT(c.name, ' 2024-', CASE WHEN c.program = 'UG' THEN '27' ELSE '26' END),
            {academic_year_id},
            2024,
            CASE WHEN c.program = 'UG' THEN 2027 ELSE 2026 END,
            FLOOR(RAND() * 50) + 30,
            1
        FROM courses c 
        WHERE c.is_active = TRUE
    """, "Created sample course batches")
    
    # Link subjects to first semester initially
    cursor.execute("SELECT id FROM semesters WHERE semester_number = 1 AND academic_year_id = %s LIMIT 1", (academic_year_id,))
    result = cursor.fetchone()
    if result:
        semester_id = result[0]
        execute_sql_safely(cursor, f"""
            UPDATE subjects 
            SET semester_id = {semester_id}
            WHERE semester_id IS NULL
        """, "Linked subjects to first semester")
    
    # 9. CREATE USEFUL VIEWS
    print('\n9. CREATING USEFUL VIEWS:')
    execute_sql_safely(cursor, """
        CREATE OR REPLACE VIEW v_subjects_detailed AS
        SELECT 
            s.id,
            s.name,
            s.course_code,
            s.course_type,
            s.theory_practical,
            s.credits,
            s.theory_credits,
            s.practical_credits,
            s.lectures_per_week,
            s.is_elective,
            c.name as course_name,
            c.program,
            d.name as department_name,
            sem.semester_name,
            sem.semester_number,
            s.description
        FROM subjects s
        LEFT JOIN courses c ON s.course_id = c.id
        LEFT JOIN departments d ON c.department_id = d.id
        LEFT JOIN semesters sem ON s.semester_id = sem.id
    """, "Created v_subjects_detailed view")
    
    execute_sql_safely(cursor, """
        CREATE OR REPLACE VIEW v_faculty_workload AS
        SELECT 
            f.id as faculty_id,
            f.name as faculty_name,
            f.email,
            d.name as department_name,
            COUNT(fa.id) as total_subjects,
            SUM(s.credits) as total_credits,
            SUM(fa.allocated_hours) as total_hours,
            AVG(fa.workload_percentage) as avg_workload_percentage
        FROM faculty f
        LEFT JOIN departments d ON f.department_id = d.id
        LEFT JOIN faculty_allocations fa ON f.id = fa.faculty_id
        LEFT JOIN subjects s ON fa.subject_id = s.id
        GROUP BY f.id, f.name, f.email, d.name
    """, "Created v_faculty_workload view")
    
    # Commit all changes
    conn.commit()
    
    print('\n' + '='*60)
    print('✓ ACADEMIC MANAGEMENT DATABASE ENHANCEMENT COMPLETED!')
    print('✓ Enhanced courses table with duration and program details')
    print('✓ Created semesters table with credit requirements')
    print('✓ Created course batches for student group management')
    print('✓ Enhanced subjects with credits, course codes, and types')
    print('✓ Enhanced faculty allocations with workload tracking')
    print('✓ Enhanced timetable with academic year/semester links')
    print('✓ Created elective groups for student choice management')
    print('✓ Inserted sample data for testing')
    print('✓ Created useful views for reporting')
    print('\n✓ READY FOR ACADEMIC MANAGEMENT INTERFACE TESTING!')
    print('='*60)
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f'Database error: {str(e)}')
    if 'conn' in locals():
        conn.rollback()
        conn.close()