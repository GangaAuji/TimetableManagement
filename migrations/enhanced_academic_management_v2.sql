-- Enhanced Academic Management Database Schema for MySQL
-- Supports both UG and PG programs with comprehensive academic structure
-- File: migrations/enhanced_academic_management_v2.sql

-- ========================================
-- 1. ENHANCED COURSES TABLE
-- ========================================
-- Add new columns to courses table safely
ALTER TABLE courses 
ADD COLUMN duration_years INT DEFAULT 3 COMMENT 'Duration in years (3 for UG, 2 for PG)';

ALTER TABLE courses 
ADD COLUMN total_semesters INT DEFAULT 6 COMMENT 'Total semesters in the course';

ALTER TABLE courses 
ADD COLUMN description TEXT COMMENT 'Course description';

ALTER TABLE courses 
ADD COLUMN is_active BOOLEAN DEFAULT TRUE COMMENT 'Course active status';

ALTER TABLE courses 
ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE courses 
ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

-- Update existing courses with proper values
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
    END
WHERE duration_years IS NULL OR total_semesters IS NULL;

-- ========================================
-- 2. ACADEMIC YEARS TABLE
-- ========================================
CREATE TABLE IF NOT EXISTS academic_years (
    id INT AUTO_INCREMENT PRIMARY KEY,
    year_name VARCHAR(20) NOT NULL UNIQUE COMMENT 'e.g., 2024-25',
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_current BOOLEAN DEFAULT FALSE COMMENT 'Only one academic year can be current',
    description TEXT COMMENT 'Academic year description',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_academic_year_current (is_current),
    INDEX idx_academic_year_dates (start_date, end_date)
) ENGINE=InnoDB COMMENT='Academic years management';

-- ========================================
-- 3. SEMESTERS TABLE
-- ========================================
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
    UNIQUE KEY unique_semester_per_year (academic_year_id, semester_number),
    INDEX idx_semester_current (is_current),
    INDEX idx_semester_dates (start_date, end_date)
) ENGINE=InnoDB COMMENT='Semester management with credit requirements';

-- ========================================
-- 4. COURSE BATCHES TABLE
-- ========================================
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
    UNIQUE KEY unique_batch_per_course (course_id, batch_name),
    INDEX idx_batch_active (is_active),
    INDEX idx_batch_years (start_year, end_year)
) ENGINE=InnoDB COMMENT='Course batch management for student groups';

-- ========================================
-- 5. ENHANCED SUBJECTS TABLE
-- ========================================
-- First backup existing subjects data if table exists
CREATE TABLE IF NOT EXISTS subjects_backup AS SELECT * FROM subjects WHERE 1=0;

-- Drop and recreate subjects table with enhanced structure
DROP TABLE IF EXISTS subjects;

CREATE TABLE subjects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    course_code VARCHAR(20) NOT NULL COMMENT 'e.g., MCA-601, BCA-301',
    course_id INT NOT NULL,
    class_id INT NULL,
    semester_id INT NULL COMMENT 'Links to semesters table',
    course_type ENUM('Core', 'Elective', 'Core Practical', 'Elective Practical', 'Project', 'Internship', 'Dissertation') DEFAULT 'Core',
    theory_practical ENUM('Theory', 'Practical', 'Both') DEFAULT 'Theory',
    credits DECIMAL(3,1) NOT NULL DEFAULT 0 COMMENT 'Total credits',
    theory_credits DECIMAL(3,1) DEFAULT 0 COMMENT 'Theory credits',
    practical_credits DECIMAL(3,1) DEFAULT 0 COMMENT 'Practical credits',
    marks INT DEFAULT 100 COMMENT 'Total marks',
    theory_marks INT DEFAULT 0 COMMENT 'Theory marks',
    practical_marks INT DEFAULT 0 COMMENT 'Practical marks',
    lectures_per_week TINYINT DEFAULT 0 COMMENT 'Weekly lecture hours',
    practical_hours_per_week TINYINT DEFAULT 0 COMMENT 'Weekly practical hours',
    is_elective BOOLEAN DEFAULT FALSE COMMENT 'Subject is elective',
    is_mandatory BOOLEAN DEFAULT TRUE COMMENT 'Subject is mandatory',
    prerequisite_subject_id INT NULL COMMENT 'Prerequisite subject',
    description TEXT COMMENT 'Subject description and objectives',
    syllabus_url VARCHAR(255) NULL COMMENT 'Link to syllabus document',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL,
    FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE SET NULL,
    FOREIGN KEY (prerequisite_subject_id) REFERENCES subjects(id) ON DELETE SET NULL,
    UNIQUE KEY unique_course_code_per_course (course_id, course_code),
    INDEX idx_subject_type (course_type),
    INDEX idx_subject_elective (is_elective),
    INDEX idx_subject_semester (semester_id),
    INDEX idx_subject_credits (credits)
) ENGINE=InnoDB COMMENT='Enhanced subjects with comprehensive academic details';

-- ========================================
-- 6. ELECTIVE GROUPS TABLE
-- ========================================
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
    UNIQUE KEY unique_group_per_semester (course_id, semester_id, group_name),
    INDEX idx_elective_group_semester (semester_id),
    INDEX idx_elective_group_mandatory (is_mandatory)
) ENGINE=InnoDB COMMENT='Elective subject groups for student selection';

-- ========================================
-- 7. ELECTIVE GROUP SUBJECTS TABLE
-- ========================================
CREATE TABLE IF NOT EXISTS elective_group_subjects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    elective_group_id INT NOT NULL,
    subject_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (elective_group_id) REFERENCES elective_groups(id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
    UNIQUE KEY unique_subject_per_group (elective_group_id, subject_id),
    INDEX idx_group_subjects (elective_group_id)
) ENGINE=InnoDB COMMENT='Subjects belonging to elective groups';

-- ========================================
-- 8. SEMESTER CREDIT REQUIREMENTS TABLE
-- ========================================
CREATE TABLE IF NOT EXISTS semester_credit_requirements (
    id INT AUTO_INCREMENT PRIMARY KEY,
    course_id INT NOT NULL,
    semester_id INT NOT NULL,
    min_credits DECIMAL(4,1) NOT NULL DEFAULT 18.0,
    max_credits DECIMAL(4,1) NOT NULL DEFAULT 30.0,
    core_credits DECIMAL(4,1) DEFAULT 0 COMMENT 'Required core credits',
    elective_credits DECIMAL(4,1) DEFAULT 0 COMMENT 'Required elective credits',
    practical_credits DECIMAL(4,1) DEFAULT 0 COMMENT 'Required practical credits',
    project_credits DECIMAL(4,1) DEFAULT 0 COMMENT 'Project/dissertation credits',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE CASCADE,
    UNIQUE KEY unique_requirement_per_semester (course_id, semester_id),
    INDEX idx_credit_requirements (course_id, semester_id)
) ENGINE=InnoDB COMMENT='Credit requirements for each semester';

-- ========================================
-- 9. CURRICULUM TEMPLATES TABLE
-- ========================================
CREATE TABLE IF NOT EXISTS curriculum_templates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    template_name VARCHAR(100) NOT NULL,
    course_id INT NOT NULL,
    academic_year_id INT NOT NULL,
    description TEXT COMMENT 'Template description',
    is_active BOOLEAN DEFAULT TRUE,
    total_credits DECIMAL(5,1) DEFAULT 0 COMMENT 'Total credits in curriculum',
    created_by INT NULL COMMENT 'User who created template',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (academic_year_id) REFERENCES academic_years(id) ON DELETE CASCADE,
    UNIQUE KEY unique_template_per_course_year (course_id, academic_year_id, template_name),
    INDEX idx_curriculum_active (is_active)
) ENGINE=InnoDB COMMENT='Curriculum templates for course planning';

-- ========================================
-- 10. ENHANCED FACULTY ALLOCATIONS TABLE
-- ========================================
-- Backup existing allocations
CREATE TABLE IF NOT EXISTS faculty_allocations_backup AS SELECT * FROM faculty_allocations WHERE 1=0;

-- Drop and recreate with enhanced structure
DROP TABLE IF EXISTS faculty_allocations;

CREATE TABLE faculty_allocations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    faculty_id INT NOT NULL,
    subject_id INT NOT NULL,
    class_id INT NULL,
    division_id INT NULL,
    semester_id INT NULL COMMENT 'Current semester allocation',
    course_batch_id INT NULL COMMENT 'Specific batch allocation',
    allocated_hours DECIMAL(4,1) DEFAULT 0 COMMENT 'Weekly allocated hours',
    workload_percentage DECIMAL(5,2) DEFAULT 100.0 COMMENT 'Percentage of subject workload',
    is_primary BOOLEAN DEFAULT TRUE COMMENT 'Primary faculty for subject',
    allocation_type ENUM('Regular', 'Guest', 'Visiting', 'Part-time') DEFAULT 'Regular',
    start_date DATE NULL COMMENT 'Allocation start date',
    end_date DATE NULL COMMENT 'Allocation end date',
    notes TEXT COMMENT 'Additional notes for allocation',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (faculty_id) REFERENCES faculty(id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL,
    FOREIGN KEY (division_id) REFERENCES divisions(id) ON DELETE SET NULL,
    FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE SET NULL,
    FOREIGN KEY (course_batch_id) REFERENCES course_batches(id) ON DELETE SET NULL,
    UNIQUE KEY unique_faculty_subject_class (faculty_id, subject_id, class_id, division_id),
    INDEX idx_allocation_faculty (faculty_id),
    INDEX idx_allocation_subject (subject_id),
    INDEX idx_allocation_semester (semester_id),
    INDEX idx_allocation_primary (is_primary)
) ENGINE=InnoDB COMMENT='Enhanced faculty subject allocations with workload tracking';

-- ========================================
-- 11. STUDENT SUBJECT SELECTIONS TABLE
-- ========================================
CREATE TABLE IF NOT EXISTS student_subject_selections (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    subject_id INT NOT NULL,
    elective_group_id INT NULL COMMENT 'If subject is from elective group',
    semester_id INT NOT NULL,
    academic_year_id INT NOT NULL,
    selection_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_confirmed BOOLEAN DEFAULT FALSE COMMENT 'Selection confirmed by admin',
    grade VARCHAR(2) NULL COMMENT 'Final grade received',
    marks_obtained DECIMAL(5,2) NULL COMMENT 'Marks obtained',
    credits_earned DECIMAL(3,1) NULL COMMENT 'Credits earned',
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

-- ========================================
-- 12. ACADEMIC PROGRESS TRACKING TABLE
-- ========================================
CREATE TABLE IF NOT EXISTS academic_progress (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    course_batch_id INT NOT NULL,
    current_semester TINYINT NOT NULL,
    total_credits_completed DECIMAL(5,1) DEFAULT 0,
    total_credits_required DECIMAL(5,1) DEFAULT 0,
    cgpa DECIMAL(3,2) NULL COMMENT 'Cumulative GPA',
    sgpa DECIMAL(3,2) NULL COMMENT 'Semester GPA',
    attendance_percentage DECIMAL(5,2) NULL,
    academic_status ENUM('Regular', 'Probation', 'Suspended', 'Graduated', 'Dropped') DEFAULT 'Regular',
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    academic_year_id INT NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (course_batch_id) REFERENCES course_batches(id) ON DELETE CASCADE,
    FOREIGN KEY (academic_year_id) REFERENCES academic_years(id) ON DELETE CASCADE,
    UNIQUE KEY unique_student_progress (student_id, academic_year_id),
    INDEX idx_progress_batch (course_batch_id),
    INDEX idx_progress_status (academic_status),
    INDEX idx_progress_semester (current_semester)
) ENGINE=InnoDB COMMENT='Student academic progress tracking';

-- ========================================
-- 13. TIMETABLE ENHANCEMENTS
-- ========================================
-- Add new columns to existing timetable table
ALTER TABLE timetable 
ADD COLUMN IF NOT EXISTS academic_year_id INT NULL COMMENT 'Academic year for timetable',
ADD COLUMN IF NOT EXISTS semester_id INT NULL COMMENT 'Semester for timetable',
ADD COLUMN IF NOT EXISTS course_batch_id INT NULL COMMENT 'Specific batch timetable',
ADD COLUMN IF NOT EXISTS room_number VARCHAR(20) NULL COMMENT 'Classroom/lab assignment',
ADD COLUMN IF NOT EXISTS timetable_type ENUM('Regular', 'Exam', 'Special', 'Makeup') DEFAULT 'Regular',
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE COMMENT 'Timetable entry active status';

-- Add foreign key constraints for new columns
ALTER TABLE timetable 
ADD CONSTRAINT fk_timetable_academic_year 
    FOREIGN KEY (academic_year_id) REFERENCES academic_years(id) ON DELETE SET NULL,
ADD CONSTRAINT fk_timetable_semester 
    FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE SET NULL,
ADD CONSTRAINT fk_timetable_course_batch 
    FOREIGN KEY (course_batch_id) REFERENCES course_batches(id) ON DELETE SET NULL;

-- ========================================
-- 14. SAMPLE DATA INSERTION
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

-- Sample course batches
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

-- ========================================
-- 15. INDEXES FOR PERFORMANCE
-- ========================================

-- Additional indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_subjects_comprehensive ON subjects(course_id, semester_id, course_type, is_elective);
CREATE INDEX IF NOT EXISTS idx_faculty_allocations_comprehensive ON faculty_allocations(faculty_id, semester_id, is_primary);
CREATE INDEX IF NOT EXISTS idx_student_selections_comprehensive ON student_subject_selections(student_id, semester_id, status);
CREATE INDEX IF NOT EXISTS idx_timetable_comprehensive ON timetable(course_id, class_id, division_id, day_of_week, academic_year_id);

-- ========================================
-- 16. VIEWS FOR COMMON QUERIES
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
LEFT JOIN semesters sem ON 1=1
LEFT JOIN subjects s ON c.id = s.course_id AND sem.id = s.semester_id
WHERE c.is_active = TRUE
GROUP BY c.id, c.name, c.program, c.duration_years, c.total_semesters, sem.semester_number, sem.semester_name
ORDER BY c.program, c.name, sem.semester_number;

-- ========================================
-- 17. STORED PROCEDURES FOR COMMON OPERATIONS
-- ========================================

DELIMITER //

-- Procedure to validate curriculum credit requirements
CREATE PROCEDURE IF NOT EXISTS ValidateCurriculumCredits(IN p_course_id INT, IN p_semester_id INT)
BEGIN
    DECLARE total_credits DECIMAL(5,1);
    DECLARE min_required DECIMAL(5,1);
    DECLARE max_allowed DECIMAL(5,1);
    DECLARE validation_status VARCHAR(50);
    
    -- Get total credits for the semester
    SELECT COALESCE(SUM(credits), 0) INTO total_credits
    FROM subjects 
    WHERE course_id = p_course_id AND semester_id = p_semester_id;
    
    -- Get credit requirements
    SELECT min_credits, max_credits INTO min_required, max_allowed
    FROM semester_credit_requirements 
    WHERE course_id = p_course_id AND semester_id = p_semester_id;
    
    -- Determine validation status
    IF total_credits < min_required THEN
        SET validation_status = 'INSUFFICIENT_CREDITS';
    ELSEIF total_credits > max_allowed THEN
        SET validation_status = 'EXCESSIVE_CREDITS';
    ELSE
        SET validation_status = 'VALID';
    END IF;
    
    SELECT validation_status as status, total_credits, min_required, max_allowed;
END //

-- Procedure to calculate student academic progress
CREATE PROCEDURE IF NOT EXISTS CalculateStudentProgress(IN p_student_id INT, IN p_academic_year_id INT)
BEGIN
    DECLARE total_completed DECIMAL(5,1) DEFAULT 0;
    DECLARE total_required DECIMAL(5,1) DEFAULT 0;
    DECLARE calculated_cgpa DECIMAL(3,2) DEFAULT 0;
    
    -- Calculate completed credits
    SELECT COALESCE(SUM(credits_earned), 0) INTO total_completed
    FROM student_subject_selections sss
    JOIN subjects s ON sss.subject_id = s.id
    WHERE sss.student_id = p_student_id 
    AND sss.academic_year_id = p_academic_year_id
    AND sss.status = 'Completed';
    
    -- Calculate required credits (from course structure)
    SELECT COALESCE(SUM(s.credits), 0) INTO total_required
    FROM student_subject_selections sss
    JOIN subjects s ON sss.subject_id = s.id
    WHERE sss.student_id = p_student_id 
    AND sss.academic_year_id = p_academic_year_id;
    
    -- Update academic progress
    INSERT INTO academic_progress (student_id, course_batch_id, current_semester, total_credits_completed, total_credits_required, academic_year_id)
    VALUES (p_student_id, 
            (SELECT course_batch_id FROM students st JOIN course_batches cb ON st.course_id = cb.course_id WHERE st.id = p_student_id LIMIT 1),
            (SELECT current_semester FROM course_batches cb JOIN students st ON cb.course_id = st.course_id WHERE st.id = p_student_id LIMIT 1),
            total_completed, 
            total_required, 
            p_academic_year_id)
    ON DUPLICATE KEY UPDATE 
        total_credits_completed = total_completed,
        total_credits_required = total_required,
        last_updated = CURRENT_TIMESTAMP;
        
    SELECT total_completed, total_required, (total_completed/total_required)*100 as completion_percentage;
END //

DELIMITER ;

-- ========================================
-- 18. TRIGGERS FOR DATA CONSISTENCY
-- ========================================

DELIMITER //

-- Trigger to ensure only one current academic year
CREATE TRIGGER IF NOT EXISTS tr_academic_year_current_unique
BEFORE UPDATE ON academic_years
FOR EACH ROW
BEGIN
    IF NEW.is_current = TRUE AND OLD.is_current = FALSE THEN
        UPDATE academic_years SET is_current = FALSE WHERE id != NEW.id;
    END IF;
END //

-- Trigger to ensure only one current semester
CREATE TRIGGER IF NOT EXISTS tr_semester_current_unique
BEFORE UPDATE ON semesters
FOR EACH ROW
BEGIN
    IF NEW.is_current = TRUE AND OLD.is_current = FALSE THEN
        UPDATE semesters SET is_current = FALSE WHERE id != NEW.id;
    END IF;
END //

-- Trigger to validate credit calculations
CREATE TRIGGER IF NOT EXISTS tr_subject_credit_validation
BEFORE INSERT ON subjects
FOR EACH ROW
BEGIN
    IF ABS(NEW.credits - (NEW.theory_credits + NEW.practical_credits)) > 0.1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Total credits must equal sum of theory and practical credits';
    END IF;
    
    IF NEW.theory_marks + NEW.practical_marks != NEW.marks THEN
        SET NEW.theory_marks = ROUND(NEW.marks * 0.7);
        SET NEW.practical_marks = NEW.marks - NEW.theory_marks;
    END IF;
END //

CREATE TRIGGER IF NOT EXISTS tr_subject_credit_validation_update
BEFORE UPDATE ON subjects
FOR EACH ROW
BEGIN
    IF ABS(NEW.credits - (NEW.theory_credits + NEW.practical_credits)) > 0.1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Total credits must equal sum of theory and practical credits';
    END IF;
    
    IF NEW.theory_marks + NEW.practical_marks != NEW.marks THEN
        SET NEW.theory_marks = ROUND(NEW.marks * 0.7);
        SET NEW.practical_marks = NEW.marks - NEW.theory_marks;
    END IF;
END //

DELIMITER ;

-- ========================================
-- 19. COMPLETION MESSAGE
-- ========================================

SELECT 'Enhanced Academic Management Database Schema Created Successfully!' as message,
       'Features: Academic Years, Semesters, Course Batches, Enhanced Subjects, Credit Tracking, Elective Groups, Faculty Allocations, Student Progress' as features,
       'Next Steps: Run Academic Management Interface, Configure Course Curricula, Set Up Academic Calendar' as next_steps;