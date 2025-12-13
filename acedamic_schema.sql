-- ============================================================================
-- COMPLETE ACADEMIC MANAGEMENT DATABASE SCHEMA
-- College Timetable Management System
-- Supports UG (3 years) and PG (2 years) programs
-- Version: 2.0
-- ============================================================================

-- Drop existing tables in correct order (child tables first)
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS student_subject_selections;
DROP TABLE IF EXISTS faculty_allocations;
DROP TABLE IF EXISTS elective_group_subjects;
DROP TABLE IF EXISTS elective_groups;
DROP TABLE IF EXISTS timetable;
DROP TABLE IF EXISTS subjects;
DROP TABLE IF EXISTS course_batches;
DROP TABLE IF EXISTS semesters;
DROP TABLE IF EXISTS classes;
DROP TABLE IF EXISTS students;
DROP TABLE IF EXISTS faculty_workload;
DROP TABLE IF EXISTS faculty_availability;
DROP TABLE IF EXISTS faculty_absences;
DROP TABLE IF EXISTS faculty;
DROP TABLE IF EXISTS courses;
DROP TABLE IF EXISTS academic_years;
DROP TABLE IF EXISTS academic_terms;
DROP TABLE IF EXISTS departments;
DROP TABLE IF EXISTS divisions;
DROP TABLE IF EXISTS rooms;
DROP TABLE IF EXISTS room_availability;

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================================
-- 1. DEPARTMENTS
-- ============================================================================
CREATE TABLE departments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    code VARCHAR(20) UNIQUE,
    description TEXT,
    head_of_department VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_dept_active (is_active),
    INDEX idx_dept_code (code)
) ENGINE=InnoDB COMMENT='Academic departments';

-- ============================================================================
-- 2. ACADEMIC YEARS
-- ============================================================================
CREATE TABLE academic_years (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(20) NOT NULL UNIQUE COMMENT 'e.g., 2024-25',
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_current BOOLEAN DEFAULT FALSE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_academic_year_current (is_current),
    INDEX idx_academic_year_dates (start_date, end_date),
    CONSTRAINT chk_year_dates CHECK (end_date > start_date)
) ENGINE=InnoDB COMMENT='Academic years management';

-- ============================================================================
-- 3. SEMESTERS
-- ============================================================================
CREATE TABLE semesters (
    id INT AUTO_INCREMENT PRIMARY KEY,
    academic_year_id INT NOT NULL,
    semester_number TINYINT NOT NULL COMMENT 'Semester number (1-8)',
    semester_name VARCHAR(50) NOT NULL COMMENT 'e.g., Semester I, Semester II',
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_current BOOLEAN DEFAULT FALSE,
    min_credits DECIMAL(4,1) DEFAULT 18.0,
    max_credits DECIMAL(4,1) DEFAULT 30.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (academic_year_id) REFERENCES academic_years(id) ON DELETE CASCADE,
    UNIQUE KEY unique_semester_per_year (academic_year_id, semester_number),
    INDEX idx_semester_current (is_current),
    INDEX idx_semester_dates (start_date, end_date),
    CONSTRAINT chk_semester_dates CHECK (end_date > start_date),
    CONSTRAINT chk_credits CHECK (max_credits >= min_credits)
) ENGINE=InnoDB COMMENT='Semester management with credit requirements';

-- ============================================================================
-- 4. COURSES (Programs)
-- ============================================================================
CREATE TABLE courses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(20) UNIQUE,
    program ENUM('UG', 'PG') NOT NULL,
    department_id INT NOT NULL,
    duration_years INT DEFAULT 3,
    total_semesters INT DEFAULT 6,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE RESTRICT,
    INDEX idx_course_program (program),
    INDEX idx_course_active (is_active),
    INDEX idx_course_dept (department_id)
) ENGINE=InnoDB COMMENT='Academic courses/programs';

-- ============================================================================
-- 5. CLASSES (Year levels: FY, SY, TY)
-- ============================================================================
CREATE TABLE classes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE COMMENT 'FY, SY, TY, etc',
    display_order INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_class_order (display_order)
) ENGINE=InnoDB COMMENT='Class/Year levels';

-- ============================================================================
-- 6. DIVISIONS
-- ============================================================================
CREATE TABLE divisions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(10) NOT NULL UNIQUE COMMENT 'A, B, C, etc',
    capacity INT DEFAULT 60,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_capacity CHECK (capacity > 0)
) ENGINE=InnoDB COMMENT='Class divisions/sections';

-- ============================================================================
-- 7. COURSE BATCHES
-- ============================================================================
CREATE TABLE course_batches (
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
    UNIQUE KEY unique_batch_per_course (course_id, batch_name),
    INDEX idx_batch_active (is_active),
    INDEX idx_batch_years (start_year, end_year),
    CONSTRAINT chk_batch_years CHECK (end_year >= start_year)
) ENGINE=InnoDB COMMENT='Course batch management for student groups';

-- ============================================================================
-- 8. SUBJECTS
-- ============================================================================
CREATE TABLE subjects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    course_code VARCHAR(20) NOT NULL,
    course_id INT NOT NULL,
    class_id INT NULL,
    semester_id INT NULL,
    course_type ENUM('Core', 'Elective', 'Core Practical', 'Elective Practical', 'Project', 'Internship', 'Dissertation') DEFAULT 'Core',
    theory_practical ENUM('Theory', 'Practical', 'Both') DEFAULT 'Theory',
    credits DECIMAL(3,1) NOT NULL DEFAULT 3.0,
    theory_credits DECIMAL(3,1) DEFAULT 0,
    practical_credits DECIMAL(3,1) DEFAULT 0,
    marks INT DEFAULT 100,
    theory_marks INT DEFAULT 0,
    practical_marks INT DEFAULT 0,
    lectures_per_week TINYINT DEFAULT 3,
    practical_hours_per_week TINYINT DEFAULT 0,
    is_elective BOOLEAN DEFAULT FALSE,
    description TEXT,
    syllabus_url VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL,
    FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE SET NULL,
    UNIQUE KEY unique_course_code_per_course (course_id, course_code),
    INDEX idx_subject_type (course_type),
    INDEX idx_subject_elective (is_elective),
    INDEX idx_subject_semester (semester_id),
    INDEX idx_subject_credits (credits),
    CONSTRAINT chk_total_credits CHECK (ABS(credits - (theory_credits + practical_credits)) < 0.1),
    CONSTRAINT chk_total_marks CHECK (marks = theory_marks + practical_marks)
) ENGINE=InnoDB COMMENT='Enhanced subjects with comprehensive academic details';

-- ============================================================================
-- 9. ELECTIVE GROUPS
-- ============================================================================
CREATE TABLE elective_groups (
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
    UNIQUE KEY unique_group_per_semester (course_id, semester_id, group_name),
    INDEX idx_elective_group_semester (semester_id),
    INDEX idx_elective_group_mandatory (is_mandatory)
) ENGINE=InnoDB COMMENT='Elective subject groups for student selection';

-- ============================================================================
-- 10. ELECTIVE GROUP SUBJECTS
-- ============================================================================
CREATE TABLE elective_group_subjects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    elective_group_id INT NOT NULL,
    subject_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (elective_group_id) REFERENCES elective_groups(id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
    UNIQUE KEY unique_subject_per_group (elective_group_id, subject_id),
    INDEX idx_group_subjects (elective_group_id)
) ENGINE=InnoDB COMMENT='Subjects belonging to elective groups';

-- ============================================================================
-- 11. FACULTY
-- ============================================================================
CREATE TABLE faculty (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    phone VARCHAR(20),
    department_id INT NOT NULL,
    designation VARCHAR(50),
    qualification VARCHAR(100),
    specialization VARCHAR(200),
    max_hours_per_week INT DEFAULT 24,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE RESTRICT,
    INDEX idx_faculty_dept (department_id),
    INDEX idx_faculty_active (is_active),
    INDEX idx_faculty_email (email)
) ENGINE=InnoDB COMMENT='Faculty members';

-- ============================================================================
-- 12. FACULTY ALLOCATIONS
-- ============================================================================
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
    INDEX idx_allocation_faculty (faculty_id),
    INDEX idx_allocation_subject (subject_id),
    INDEX idx_allocation_semester (semester_id),
    INDEX idx_allocation_primary (is_primary)
) ENGINE=InnoDB COMMENT='Faculty subject allocations with workload tracking';

-- ============================================================================
-- 13. STUDENTS
-- ============================================================================
CREATE TABLE students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    phone VARCHAR(20),
    roll_number VARCHAR(50) UNIQUE,
    course_id INT NOT NULL,
    class_id INT NULL,
    division_id INT NULL,
    course_batch_id INT NULL,
    admission_year YEAR,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE RESTRICT,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL,
    FOREIGN KEY (division_id) REFERENCES divisions(id) ON DELETE SET NULL,
    FOREIGN KEY (course_batch_id) REFERENCES course_batches(id) ON DELETE SET NULL,
    INDEX idx_student_course (course_id),
    INDEX idx_student_class (class_id),
    INDEX idx_student_batch (course_batch_id),
    INDEX idx_student_active (is_active)
) ENGINE=InnoDB COMMENT='Student information';

-- ============================================================================
-- 14. STUDENT SUBJECT SELECTIONS
-- ============================================================================
CREATE TABLE student_subject_selections (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    subject_id INT NOT NULL,
    elective_group_id INT NULL,
    semester_id INT NOT NULL,
    academic_year_id INT NOT NULL,
    selection_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_confirmed BOOLEAN DEFAULT FALSE,
    grade VARCHAR(2) NULL,
    marks_obtained DECIMAL(5,2) NULL,
    credits_earned DECIMAL(3,1) NULL,
    status ENUM('Enrolled', 'Completed', 'Failed', 'Withdrawn') DEFAULT 'Enrolled',
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
    FOREIGN KEY (elective_group_id) REFERENCES elective_groups(id) ON DELETE SET NULL,
    FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE CASCADE,
    FOREIGN KEY (academic_year_id) REFERENCES academic_years(id) ON DELETE CASCADE,
    UNIQUE KEY unique_student_subject_semester (student_id, subject_id, semester_id),
    INDEX idx_student_selections (student_id, semester_id),
    INDEX idx_subject_enrollments (subject_id),
    INDEX idx_selection_status (status)
) ENGINE=InnoDB COMMENT='Student subject selections and academic progress';

-- ============================================================================
-- 15. ROOMS
-- ============================================================================
CREATE TABLE rooms (
    id INT AUTO_INCREMENT PRIMARY KEY,
    room_number VARCHAR(20) NOT NULL UNIQUE,
    room_type ENUM('Classroom', 'Laboratory', 'Auditorium', 'Seminar Hall') DEFAULT 'Classroom',
    capacity INT DEFAULT 60,
    floor INT,
    building VARCHAR(50),
    has_projector BOOLEAN DEFAULT FALSE,
    has_ac BOOLEAN DEFAULT FALSE,
    is_available BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_room_type (room_type),
    INDEX idx_room_available (is_available),
    CONSTRAINT chk_room_capacity CHECK (capacity > 0)
) ENGINE=InnoDB COMMENT='Classroom and lab information';

-- ============================================================================
-- 16. TIMETABLE
-- ============================================================================
CREATE TABLE timetable (
    id INT AUTO_INCREMENT PRIMARY KEY,
    course_id INT NOT NULL,
    class_id INT NOT NULL,
    division_id INT NULL,
    day_of_week ENUM('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday') NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    subject_id INT NOT NULL,
    faculty_id INT NOT NULL,
    room_id INT NULL,
    academic_year_id INT NULL,
    semester_id INT NULL,
    course_batch_id INT NULL,
    room_number VARCHAR(20),
    timetable_type ENUM('Regular', 'Exam', 'Special', 'Makeup') DEFAULT 'Regular',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    FOREIGN KEY (division_id) REFERENCES divisions(id) ON DELETE SET NULL,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
    FOREIGN KEY (faculty_id) REFERENCES faculty(id) ON DELETE CASCADE,
    FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE SET NULL,
    FOREIGN KEY (academic_year_id) REFERENCES academic_years(id) ON DELETE SET NULL,
    FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE SET NULL,
    FOREIGN KEY (course_batch_id) REFERENCES course_batches(id) ON DELETE SET NULL,
    INDEX idx_timetable_course_class (course_id, class_id),
    INDEX idx_timetable_day (day_of_week),
    INDEX idx_timetable_time (start_time, end_time),
    INDEX idx_timetable_faculty (faculty_id),
    INDEX idx_timetable_room (room_id),
    INDEX idx_timetable_semester (semester_id),
    CONSTRAINT chk_time_slot CHECK (end_time > start_time)
) ENGINE=InnoDB COMMENT='Timetable schedule';

-- ============================================================================
-- INITIAL DATA INSERTION
-- ============================================================================

-- Insert default classes
INSERT INTO classes (name, display_order) VALUES
('FY', 1), ('SY', 2), ('TY', 3), ('Final Year', 4);

-- Insert default divisions
INSERT INTO divisions (name, capacity) VALUES
('A', 60), ('B', 60), ('C', 60), ('D', 60);

-- Insert sample departments
INSERT INTO departments (name, code, description, is_active) VALUES
('Computer Science', 'CS', 'Computer Science and IT Department', TRUE),
('Data Science', 'DS', 'Data Science and Analytics Department', TRUE),
('Management', 'MGT', 'Management Studies Department', TRUE),
('Commerce', 'COM', 'Commerce Department', TRUE);

-- Insert current academic year
INSERT INTO academic_years (name, start_date, end_date, is_current, description) VALUES
('2024-25', '2024-07-01', '2025-06-30', TRUE, 'Academic Year 2024-2025');

-- Get academic year ID
SET @academic_year_id = LAST_INSERT_ID();

-- Insert semesters for current year
INSERT INTO semesters (academic_year_id, semester_number, semester_name, start_date, end_date, is_current, min_credits, max_credits) VALUES
(@academic_year_id, 1, 'Semester I', '2024-07-01', '2024-11-30', TRUE, 18.0, 26.0),
(@academic_year_id, 2, 'Semester II', '2024-12-01', '2025-04-30', FALSE, 18.0, 26.0),
(@academic_year_id, 3, 'Semester III', '2024-07-01', '2024-11-30', FALSE, 20.0, 28.0),
(@academic_year_id, 4, 'Semester IV', '2024-12-01', '2025-04-30', FALSE, 20.0, 28.0);

-- Insert sample courses
INSERT INTO courses (name, code, program, department_id, duration_years, total_semesters, description, is_active) VALUES
('Bachelor of Computer Applications', 'BCA', 'UG', 1, 3, 6, 'UG program in Computer Applications', TRUE),
('Master of Computer Applications', 'MCA', 'PG', 1, 2, 4, 'PG program in Computer Applications', TRUE),
('MSc in Data Analytics', 'MSC-DA', 'PG', 2, 2, 4, 'PG program in Data Analytics', TRUE),
('BBA', 'BBA', 'UG', 3, 3, 6, 'Bachelor of Business Administration', TRUE);

-- Insert sample rooms
INSERT INTO rooms (room_number, room_type, capacity, floor, building, has_projector, has_ac, is_available) VALUES
('101', 'Classroom', 60, 1, 'Main Building', TRUE, TRUE, TRUE),
('102', 'Classroom', 60, 1, 'Main Building', TRUE, TRUE, TRUE),
('103', 'Laboratory', 40, 1, 'Main Building', TRUE, TRUE, TRUE),
('201', 'Classroom', 60, 2, 'Main Building', TRUE, FALSE, TRUE),
('202', 'Laboratory', 40, 2, 'Main Building', TRUE, TRUE, TRUE);

-- ============================================================================
-- USEFUL VIEWS
-- ============================================================================

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
    s.description
FROM subjects s
LEFT JOIN courses c ON s.course_id = c.id
LEFT JOIN departments d ON c.department_id = d.id
LEFT JOIN semesters sem ON s.semester_id = sem.id;

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
    AVG(fa.workload_percentage) as avg_workload_percentage,
    f.max_hours_per_week
FROM faculty f
LEFT JOIN departments d ON f.department_id = d.id
LEFT JOIN faculty_allocations fa ON f.id = fa.faculty_id
LEFT JOIN subjects s ON fa.subject_id = s.id
GROUP BY f.id, f.name, f.email, d.name, f.max_hours_per_week;

-- View for course curriculum overview
CREATE OR REPLACE VIEW v_curriculum_overview AS
SELECT 
    c.id as course_id,
    c.name as course_name,
    c.program,
    c.duration_years,
    c.total_semesters,
    sem.semester_number,
    sem.semester_name,
    COUNT(s.id) as total_subjects,
    SUM(s.credits) as total_credits,
    SUM(CASE WHEN s.course_type = 'Core' THEN s.credits ELSE 0 END) as core_credits,
    SUM(CASE WHEN s.course_type LIKE '%Elective%' THEN s.credits ELSE 0 END) as elective_credits,
    SUM(CASE WHEN s.theory_practical = 'Practical' THEN s.credits ELSE 0 END) as practical_credits
FROM courses c
CROSS JOIN semesters sem
LEFT JOIN subjects s ON c.id = s.course_id AND sem.id = s.semester_id
WHERE c.is_active = TRUE
GROUP BY c.id, c.name, c.program, c.duration_years, c.total_semesters, sem.semester_number, sem.semester_name
ORDER BY c.program, c.name, sem.semester_number;

-- ============================================================================
-- COMPLETION MESSAGE
-- ============================================================================
SELECT 'Academic Management Database Schema v2.0 created successfully!' AS message;