-- Enhanced Academic Management Database Schema
-- Run this script to add comprehensive academic management features

-- Academic Years/Terms Management
CREATE TABLE IF NOT EXISTS academic_years (
    id INT AUTO_INCREMENT PRIMARY KEY,
    year_name VARCHAR(20) NOT NULL UNIQUE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_current BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_current (is_current),
    INDEX idx_dates (start_date, end_date)
);

-- Semesters within Academic Years
CREATE TABLE IF NOT EXISTS semesters (
    id INT AUTO_INCREMENT PRIMARY KEY,
    academic_year_id INT NOT NULL,
    semester_number INT NOT NULL,
    semester_name VARCHAR(50) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_current BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (academic_year_id) REFERENCES academic_years(id) ON DELETE CASCADE,
    UNIQUE KEY unique_semester (academic_year_id, semester_number),
    INDEX idx_current_semester (is_current)
);

-- Course Batches for batch-wise management
CREATE TABLE IF NOT EXISTS course_batches (
    id INT AUTO_INCREMENT PRIMARY KEY,
    course_id INT NOT NULL,
    batch_year INT NOT NULL,
    batch_name VARCHAR(100) NOT NULL,
    admission_year INT NOT NULL,
    total_students INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    UNIQUE KEY unique_batch (course_id, batch_year),
    INDEX idx_active (is_active),
    INDEX idx_admission (admission_year)
);

-- Enhanced Subjects with Credit Management
ALTER TABLE subjects 
ADD COLUMN IF NOT EXISTS course_code VARCHAR(20),
ADD COLUMN IF NOT EXISTS course_type ENUM('Core', 'Core Practical', 'Elective', 'Project', 'Seminar', 'Industrial Training') DEFAULT 'Core',
ADD COLUMN IF NOT EXISTS theory_practical ENUM('Theory', 'Practical', 'Both') DEFAULT 'Theory',
ADD COLUMN IF NOT EXISTS credits INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS theory_credits INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS practical_credits INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS marks INT DEFAULT 100,
ADD COLUMN IF NOT EXISTS lectures_per_week INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS semester_id INT,
ADD COLUMN IF NOT EXISTS is_elective BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS prerequisite_subject_id INT,
ADD COLUMN IF NOT EXISTS description TEXT,
ADD COLUMN IF NOT EXISTS syllabus_file VARCHAR(255),
ADD INDEX idx_course_type (course_type),
ADD INDEX idx_semester (semester_id),
ADD INDEX idx_elective (is_elective),
ADD FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE SET NULL,
ADD FOREIGN KEY (prerequisite_subject_id) REFERENCES subjects(id) ON DELETE SET NULL;

-- Curriculum Templates for different course structures
CREATE TABLE IF NOT EXISTS curriculum_templates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    course_id INT NOT NULL,
    template_name VARCHAR(100) NOT NULL,
    academic_year_id INT NOT NULL,
    total_semesters INT NOT NULL,
    total_credits INT NOT NULL,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INT,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (academic_year_id) REFERENCES academic_years(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_default (is_default)
);

-- Subject Prerequisites (many-to-many relationship)
CREATE TABLE IF NOT EXISTS subject_prerequisites (
    id INT AUTO_INCREMENT PRIMARY KEY,
    subject_id INT NOT NULL,
    prerequisite_subject_id INT NOT NULL,
    is_mandatory BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
    FOREIGN KEY (prerequisite_subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
    UNIQUE KEY unique_prerequisite (subject_id, prerequisite_subject_id)
);

-- Elective Groups for managing elective choices
CREATE TABLE IF NOT EXISTS elective_groups (
    id INT AUTO_INCREMENT PRIMARY KEY,
    group_name VARCHAR(100) NOT NULL,
    course_id INT NOT NULL,
    semester_id INT NOT NULL,
    min_subjects_to_choose INT DEFAULT 1,
    max_subjects_to_choose INT DEFAULT 1,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE CASCADE
);

-- Subjects in Elective Groups
CREATE TABLE IF NOT EXISTS elective_group_subjects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    elective_group_id INT NOT NULL,
    subject_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (elective_group_id) REFERENCES elective_groups(id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
    UNIQUE KEY unique_group_subject (elective_group_id, subject_id)
);

-- Credit Requirements per semester
CREATE TABLE IF NOT EXISTS semester_credit_requirements (
    id INT AUTO_INCREMENT PRIMARY KEY,
    course_id INT NOT NULL,
    semester_id INT NOT NULL,
    min_credits INT NOT NULL,
    max_credits INT NOT NULL,
    core_credits INT DEFAULT 0,
    elective_credits INT DEFAULT 0,
    practical_credits INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE CASCADE,
    UNIQUE KEY unique_course_semester (course_id, semester_id)
);

-- Enhanced Faculty Allocations with more details
ALTER TABLE faculty_allocations 
ADD COLUMN IF NOT EXISTS academic_year_id INT,
ADD COLUMN IF NOT EXISTS semester_id INT,
ADD COLUMN IF NOT EXISTS batch_id INT,
ADD COLUMN IF NOT EXISTS allocated_hours INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS is_primary BOOLEAN DEFAULT TRUE,
ADD COLUMN IF NOT EXISTS notes TEXT,
ADD INDEX idx_academic_year (academic_year_id),
ADD INDEX idx_semester_alloc (semester_id),
ADD INDEX idx_batch (batch_id),
ADD FOREIGN KEY (academic_year_id) REFERENCES academic_years(id) ON DELETE SET NULL,
ADD FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE SET NULL,
ADD FOREIGN KEY (batch_id) REFERENCES course_batches(id) ON DELETE SET NULL;

-- Student Elective Choices
CREATE TABLE IF NOT EXISTS student_elective_choices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    elective_group_id INT NOT NULL,
    subject_id INT NOT NULL,
    academic_year_id INT NOT NULL,
    semester_id INT NOT NULL,
    choice_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (elective_group_id) REFERENCES elective_groups(id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
    FOREIGN KEY (academic_year_id) REFERENCES academic_years(id) ON DELETE CASCADE,
    FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE CASCADE,
    UNIQUE KEY unique_student_group (student_id, elective_group_id, academic_year_id, semester_id)
);

-- Course Progression Rules
CREATE TABLE IF NOT EXISTS course_progression_rules (
    id INT AUTO_INCREMENT PRIMARY KEY,
    course_id INT NOT NULL,
    from_semester_id INT NOT NULL,
    to_semester_id INT NOT NULL,
    min_credits_required INT NOT NULL,
    min_gpa_required DECIMAL(3,2) DEFAULT 0.00,
    mandatory_subjects JSON, -- Array of subject IDs that must be passed
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (from_semester_id) REFERENCES semesters(id) ON DELETE CASCADE,
    FOREIGN KEY (to_semester_id) REFERENCES semesters(id) ON DELETE CASCADE
);

-- Time Slot Templates for different course types
CREATE TABLE IF NOT EXISTS time_slot_templates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    template_name VARCHAR(100) NOT NULL,
    course_type ENUM('UG', 'PG', 'PhD') NOT NULL,
    slot_duration_minutes INT NOT NULL,
    total_slots_per_day INT NOT NULL,
    break_after_slot INT,
    break_duration_minutes INT,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    days_per_week INT DEFAULT 6,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_course_type_template (course_type),
    INDEX idx_default_template (is_default)
);

-- Sample Data Insertion
INSERT IGNORE INTO academic_years (year_name, start_date, end_date, is_current) VALUES
('2024-25', '2024-07-01', '2025-06-30', TRUE),
('2025-26', '2025-07-01', '2026-06-30', FALSE);

INSERT IGNORE INTO semesters (academic_year_id, semester_number, semester_name, start_date, end_date, is_current) 
SELECT ay.id, 1, 'Semester I', '2024-07-01', '2024-12-31', FALSE FROM academic_years ay WHERE ay.year_name = '2024-25'
UNION ALL
SELECT ay.id, 2, 'Semester II', '2025-01-01', '2025-06-30', FALSE FROM academic_years ay WHERE ay.year_name = '2024-25'
UNION ALL
SELECT ay.id, 3, 'Semester III', '2024-07-01', '2024-12-31', FALSE FROM academic_years ay WHERE ay.year_name = '2024-25'
UNION ALL
SELECT ay.id, 4, 'Semester IV', '2025-01-01', '2025-06-30', TRUE FROM academic_years ay WHERE ay.year_name = '2024-25';

INSERT IGNORE INTO time_slot_templates (template_name, course_type, slot_duration_minutes, total_slots_per_day, break_after_slot, break_duration_minutes, start_time, end_time, is_default) VALUES
('Standard UG', 'UG', 45, 5, 3, 30, '07:45:00', '12:30:00', TRUE),
('Standard PG', 'PG', 60, 4, 2, 30, '13:00:00', '18:00:00', TRUE);

-- Add indexes for better performance
CREATE INDEX IF NOT EXISTS idx_subjects_course_semester ON subjects(course_id, semester_id);
CREATE INDEX IF NOT EXISTS idx_subjects_type ON subjects(course_type);
CREATE INDEX IF NOT EXISTS idx_faculty_allocations_composite ON faculty_allocations(academic_year_id, semester_id, course_id);

-- Update existing courses to have proper program types
UPDATE courses SET program = 'PG' WHERE program IS NULL OR program = '';