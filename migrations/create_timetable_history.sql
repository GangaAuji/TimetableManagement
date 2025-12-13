-- Migration: Create timetable_history table
-- Purpose: Archive old timetable data before generating new timetables
-- Created: 2025-11-22
-- Updated: 2025-11-29 - Removed week_start_date to match timetable schema

-- Create timetable_history table to preserve old timetables
CREATE TABLE IF NOT EXISTS timetable_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    course_id INT NOT NULL,
    class_id INT,
    division_id INT,
    day_of_week VARCHAR(20),
    start_time TIME,
    end_time TIME,
    subject_id INT,
    faculty_id INT,
    room_id INT,
    archived_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_course_class_div (course_id, class_id, division_id),
    INDEX idx_archived_at (archived_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add foreign key constraints (optional, based on your schema)
-- ALTER TABLE timetable_history 
-- ADD CONSTRAINT fk_history_course FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
-- ADD CONSTRAINT fk_history_class FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL,
-- ADD CONSTRAINT fk_history_division FOREIGN KEY (division_id) REFERENCES divisions(id) ON DELETE SET NULL,
-- ADD CONSTRAINT fk_history_subject FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE SET NULL,
-- ADD CONSTRAINT fk_history_faculty FOREIGN KEY (faculty_id) REFERENCES faculty(user_id) ON DELETE SET NULL,
-- ADD CONSTRAINT fk_history_room FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE SET NULL;

-- Verify the table was created
SHOW TABLES LIKE 'timetable_history';
DESCRIBE timetable_history;
