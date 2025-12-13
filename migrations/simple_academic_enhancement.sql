-- Simple Academic Management Enhancement for MySQL
-- File: migrations/simple_academic_enhancement.sql

-- ========================================
-- 1. ADD MISSING COLUMNS TO COURSES TABLE
-- ========================================
ALTER TABLE courses 
ADD COLUMN duration_years INT DEFAULT 3 COMMENT 'Duration in years (3 for UG, 2 for PG)';

ALTER TABLE courses 
ADD COLUMN total_semesters INT DEFAULT 6 COMMENT 'Total semesters in the course';

ALTER TABLE courses 
ADD COLUMN description TEXT COMMENT 'Course description';

ALTER TABLE courses 
ADD COLUMN is_active BOOLEAN DEFAULT TRUE COMMENT 'Course active status';

-- ========================================
-- 2. ACADEMIC YEARS TABLE
-- ========================================
CREATE TABLE IF NOT EXISTS academic_years (
    id INT AUTO_INCREMENT PRIMARY KEY,
    year_name VARCHAR(20) NOT NULL UNIQUE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_current BOOLEAN DEFAULT FALSE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- ========================================
-- 3. SEMESTERS TABLE
-- ========================================
CREATE TABLE IF NOT EXISTS semesters (
    id INT AUTO_INCREMENT PRIMARY KEY,
    academic_year_id INT NOT NULL,
    semester_number TINYINT NOT NULL,
    semester_name VARCHAR(50) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_current BOOLEAN DEFAULT FALSE,
    min_credits DECIMAL(4,1) DEFAULT 18.0,
    max_credits DECIMAL(4,1) DEFAULT 30.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (academic_year_id) REFERENCES academic_years(id) ON DELETE CASCADE,
    UNIQUE KEY unique_semester_per_year (academic_year_id, semester_number)
);

-- ========================================
-- 4. COURSE BATCHES TABLE
-- ========================================
CREATE TABLE IF NOT EXISTS course_batches (
    id INT AUTO_INCREMENT PRIMARY KEY,
    course_id INT NOT NULL,
    batch_name VARCHAR(50) NOT NULL,
    academic_year_id INT NULL,
    start_year YEAR NOT NULL,
    end_year YEAR NOT NULL,
    total_students INT DEFAULT 0,
    current_semester TINYINT DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (academic_year_id) REFERENCES academic_years(id) ON DELETE SET NULL,
    UNIQUE KEY unique_batch_per_course (course_id, batch_name)
);

-- ========================================
-- 5. BACKUP AND RECREATE SUBJECTS TABLE
-- ========================================
-- Rename existing subjects table to backup
RENAME TABLE subjects TO subjects_backup;

-- Create new enhanced subjects table
CREATE TABLE subjects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    course_code VARCHAR(20) NOT NULL,
    course_id INT NOT NULL,
    class_id INT NULL,
    semester_id INT NULL,
    course_type ENUM('Core', 'Elective', 'Core Practical', 'Elective Practical', 'Project', 'Internship', 'Dissertation') DEFAULT 'Core',
    theory_practical ENUM('Theory', 'Practical', 'Both') DEFAULT 'Theory',
    credits DECIMAL(3,1) NOT NULL DEFAULT 0,
    theory_credits DECIMAL(3,1) DEFAULT 0,
    practical_credits DECIMAL(3,1) DEFAULT 0,
    marks INT DEFAULT 100,
    theory_marks INT DEFAULT 0,
    practical_marks INT DEFAULT 0,
    lectures_per_week TINYINT DEFAULT 0,
    practical_hours_per_week TINYINT DEFAULT 0,
    is_elective BOOLEAN DEFAULT FALSE,
    is_mandatory BOOLEAN DEFAULT TRUE,
    prerequisite_subject_id INT NULL,
    description TEXT,
    syllabus_url VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL,
    FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE SET NULL,
    FOREIGN KEY (prerequisite_subject_id) REFERENCES subjects(id) ON DELETE SET NULL,
    UNIQUE KEY unique_course_code_per_course (course_id, course_code)
);

-- ========================================
-- 6. MIGRATE DATA FROM BACKUP
-- ========================================
INSERT INTO subjects (name, course_id, class_id, course_code, course_type, credits, marks, description)
SELECT 
    name,
    course_id,
    class_id,
    CONCAT('SUBJ-', LPAD(id, 3, '0')) as course_code,
    'Core' as course_type,
    3.0 as credits,
    COALESCE(marks, 100) as marks,
    name as description
FROM subjects_backup;

-- ========================================
-- 7. ELECTIVE GROUPS TABLE
-- ========================================
CREATE TABLE IF NOT EXISTS elective_groups (
    id INT AUTO_INCREMENT PRIMARY KEY,
    group_name VARCHAR(100) NOT NULL,
    course_id INT NOT NULL,
    semester_id INT NOT NULL,
    min_subjects_to_choose TINYINT DEFAULT 1,
    max_subjects_to_choose TINYINT DEFAULT 1,
    total_credits DECIMAL(4,1) DEFAULT 0,
    description TEXT,
    is_mandatory BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE CASCADE,
    UNIQUE KEY unique_group_per_semester (course_id, semester_id, group_name)
);

-- ========================================
-- 8. ELECTIVE GROUP SUBJECTS TABLE
-- ========================================
CREATE TABLE IF NOT EXISTS elective_group_subjects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    elective_group_id INT NOT NULL,
    subject_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (elective_group_id) REFERENCES elective_groups(id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
    UNIQUE KEY unique_subject_per_group (elective_group_id, subject_id)
);

-- ========================================
-- 9. ENHANCED FACULTY ALLOCATIONS
-- ========================================
-- Rename existing table to backup
RENAME TABLE faculty_allocations TO faculty_allocations_backup;

-- Create new enhanced faculty allocations table
CREATE TABLE faculty_allocations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    faculty_id INT NOT NULL,
    subject_id INT NOT NULL,
    class_id INT NULL,
    division_id INT NULL,
    semester_id INT NULL,
    course_batch_id INT NULL,
    allocated_hours DECIMAL(4,1) DEFAULT 0,
    workload_percentage DECIMAL(5,2) DEFAULT 100.0,
    is_primary BOOLEAN DEFAULT TRUE,
    allocation_type ENUM('Regular', 'Guest', 'Visiting', 'Part-time') DEFAULT 'Regular',
    start_date DATE NULL,
    end_date DATE NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (faculty_id) REFERENCES faculty(id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL,
    FOREIGN KEY (division_id) REFERENCES divisions(id) ON DELETE SET NULL,
    FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE SET NULL,
    FOREIGN KEY (course_batch_id) REFERENCES course_batches(id) ON DELETE SET NULL,
    UNIQUE KEY unique_faculty_subject_class (faculty_id, subject_id, class_id, division_id)
);

-- Migrate existing faculty allocations
INSERT INTO faculty_allocations (faculty_id, subject_id, class_id, division_id, allocated_hours, is_primary)
SELECT 
    faculty_id,
    subject_id,
    class_id,
    division_id,
    COALESCE(allocated_hours, 3.0) as allocated_hours,
    TRUE as is_primary
FROM faculty_allocations_backup;

-- ========================================
-- 10. SAMPLE DATA INSERTION
-- ========================================

-- Insert default academic year
INSERT IGNORE INTO academic_years (year_name, start_date, end_date, is_current, description) 
VALUES ('2024-25', '2024-07-01', '2025-06-30', TRUE, 'Academic Year 2024-25');

-- Get the academic year ID
SET @academic_year_id = (SELECT id FROM academic_years WHERE year_name = '2024-25');

-- Insert semesters for the academic year
INSERT IGNORE INTO semesters (academic_year_id, semester_number, semester_name, start_date, end_date, is_current, min_credits, max_credits) VALUES
(@academic_year_id, 1, 'Semester I', '2024-07-01', '2024-11-30', TRUE, 18.0, 26.0),
(@academic_year_id, 2, 'Semester II', '2024-12-01', '2025-04-30', FALSE, 18.0, 26.0),
(@academic_year_id, 3, 'Semester III', '2024-07-01', '2024-11-30', FALSE, 20.0, 28.0),
(@academic_year_id, 4, 'Semester IV', '2024-12-01', '2025-04-30', FALSE, 20.0, 28.0);

-- Update existing courses with enhanced details
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
    description = CASE 
        WHEN name LIKE '%Computer%' THEN 'Computer Science and applications program'
        WHEN name LIKE '%Data%' THEN 'Data Analytics and Management program'
        WHEN name LIKE '%Management%' THEN 'Management and Business Administration program'
        ELSE 'Academic program'
    END,
    is_active = TRUE
WHERE duration_years IS NULL;

-- Sample course batches for existing courses
INSERT IGNORE INTO course_batches (course_id, batch_name, academic_year_id, start_year, end_year, total_students, current_semester) 
SELECT 
    c.id, 
    CONCAT(c.name, ' 2024-', CASE WHEN c.program = 'UG' THEN '27' ELSE '26' END),
    @academic_year_id,
    2024,
    CASE WHEN c.program = 'UG' THEN 2027 ELSE 2026 END,
    FLOOR(RAND() * 50) + 30,
    1
FROM courses c 
WHERE c.is_active = TRUE;

-- Update subjects with semester associations
UPDATE subjects s
JOIN courses c ON s.course_id = c.id
JOIN semesters sem ON sem.academic_year_id = @academic_year_id
SET s.semester_id = sem.id
WHERE s.semester_id IS NULL 
AND sem.semester_number = 1;  -- Assign all subjects to first semester initially

-- ========================================
-- 11. CREATE USEFUL VIEWS
-- ========================================

-- View for comprehensive subject information
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
    prereq.name as prerequisite_name,
    s.description
FROM subjects s
LEFT JOIN courses c ON s.course_id = c.id
LEFT JOIN departments d ON c.department_id = d.id
LEFT JOIN semesters sem ON s.semester_id = sem.id
LEFT JOIN subjects prereq ON s.prerequisite_subject_id = prereq.id;

-- View for faculty workload analysis
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
GROUP BY f.id, f.name, f.email, d.name;

-- ========================================
-- 12. COMPLETION MESSAGE
-- ========================================

SELECT 'Simple Academic Management Database Enhancement Completed!' as message,
       'Created: Academic Years, Semesters, Course Batches, Enhanced Subjects, Elective Groups, Faculty Allocations' as features,
       'Data migrated from existing tables and sample data inserted' as migration_status,
       'Ready for Academic Management Interface Testing' as next_step;