-- ============================================================================
-- ENTERPRISE TIMETABLE MANAGEMENT SYSTEM - DATABASE UPGRADE
-- ============================================================================
-- Purpose: Upgrade timetable system to support:
--   1. Cross-course faculty collision detection
--   2. Dynamic lecture durations (PG: 60min, UG: 45min)
--   3. Shift management and teaching hours tracking
--   4. Practical session continuous block scheduling
--   5. Proxy and absence handling with rescheduling
-- 
-- Created: 2025-11-29
-- Author: System Architect
-- ============================================================================

USE college_timetable_db;

-- ============================================================================
-- 1. CREATE TIMETABLE HISTORY TABLE
-- ============================================================================

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
    archived_reason VARCHAR(100) DEFAULT 'Regenerated',
    INDEX idx_course_class_div (course_id, class_id, division_id),
    INDEX idx_archived_at (archived_at),
    INDEX idx_faculty_date (faculty_id, archived_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 2. ADD LECTURE DURATION SUPPORT TO COURSES TABLE
-- ============================================================================

-- Check if lecture_duration_minutes column exists, if not add it
SET @dbname = DATABASE();
SET @tablename = 'courses';
SET @columnname = 'lecture_duration_minutes';
SET @preparedStatement = (SELECT IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
     WHERE (table_name = @tablename)
       AND (table_schema = @dbname)
       AND (column_name = @columnname)
    ) > 0,
    'SELECT 1',
    CONCAT('ALTER TABLE ', @tablename, ' ADD COLUMN ', @columnname, ' INT DEFAULT 60 COMMENT ''Default lecture duration for this course (PG: 60min, UG: 45min)''')
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Check if max_sessions_per_day column exists, if not add it
SET @columnname = 'max_sessions_per_day';
SET @preparedStatement = (SELECT IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
     WHERE (table_name = @tablename)
       AND (table_schema = @dbname)
       AND (column_name = @columnname)
    ) > 0,
    'SELECT 1',
    CONCAT('ALTER TABLE ', @tablename, ' ADD COLUMN ', @columnname, ' INT DEFAULT 4 COMMENT ''Maximum sessions per day for this course''')
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Check if course_level column exists, if not add it
SET @columnname = 'course_level';
SET @preparedStatement = (SELECT IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
     WHERE (table_name = @tablename)
       AND (table_schema = @dbname)
       AND (column_name = @columnname)
    ) > 0,
    'SELECT 1',
    CONCAT('ALTER TABLE ', @tablename, ' ADD COLUMN ', @columnname, ' ENUM(''UG'', ''PG'', ''Diploma'', ''Certificate'') DEFAULT ''PG'' COMMENT ''Course level determines lecture duration defaults''')
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- ============================================================================
-- 3. ENHANCE FACULTY AVAILABILITY WITH SHIFT MANAGEMENT
-- ============================================================================

-- Add teaching_hours_per_day column to faculty_availability
SET @tablename = 'faculty_availability';
SET @columnname = 'teaching_hours_per_day';
SET @preparedStatement = (SELECT IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
     WHERE (table_name = @tablename)
       AND (table_schema = @dbname)
       AND (column_name = @columnname)
    ) > 0,
    'SELECT 1',
    CONCAT('ALTER TABLE ', @tablename, ' ADD COLUMN ', @columnname, ' DECIMAL(4,2) DEFAULT 6.0 COMMENT ''Maximum teaching hours allowed per day''')
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Add shift_name column
SET @columnname = 'shift_name';
SET @preparedStatement = (SELECT IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
     WHERE (table_name = @tablename)
       AND (table_schema = @dbname)
       AND (column_name = @columnname)
    ) > 0,
    'SELECT 1',
    CONCAT('ALTER TABLE ', @tablename, ' ADD COLUMN ', @columnname, ' VARCHAR(50) DEFAULT ''General'' COMMENT ''Shift identifier (Morning, Evening, General)''')
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- ============================================================================
-- 4. CREATE TIMETABLE CONFLICTS LOG TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS timetable_conflicts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    generation_timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    course_id INT NOT NULL,
    class_id INT,
    division_id INT,
    conflict_type ENUM('faculty_collision', 'room_unavailable', 'faculty_unavailable', 'exceed_hours', 'no_slot') NOT NULL,
    faculty_id INT,
    subject_id INT,
    day_of_week VARCHAR(20),
    start_time TIME,
    end_time TIME,
    description TEXT,
    resolution_status ENUM('unresolved', 'resolved', 'ignored') DEFAULT 'unresolved',
    INDEX idx_generation (generation_timestamp),
    INDEX idx_conflict_type (conflict_type),
    INDEX idx_faculty (faculty_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 5. CREATE PROXY ASSIGNMENTS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS proxy_assignments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    original_faculty_id INT NOT NULL,
    proxy_faculty_id INT NOT NULL,
    subject_id INT NOT NULL,
    course_id INT NOT NULL,
    class_id INT,
    division_id INT,
    day_of_week VARCHAR(20),
    start_time TIME,
    end_time TIME,
    assignment_date DATE NOT NULL,
    reason ENUM('absence', 'workload', 'expertise', 'manual') DEFAULT 'absence',
    status ENUM('pending', 'confirmed', 'rejected', 'completed') DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by INT,
    INDEX idx_original_faculty (original_faculty_id),
    INDEX idx_proxy_faculty (proxy_faculty_id),
    INDEX idx_date (assignment_date),
    FOREIGN KEY (original_faculty_id) REFERENCES faculty(user_id),
    FOREIGN KEY (proxy_faculty_id) REFERENCES faculty(user_id),
    FOREIGN KEY (subject_id) REFERENCES subjects(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 6. CREATE FACULTY WORKLOAD TRACKING VIEW
-- ============================================================================

CREATE OR REPLACE VIEW v_faculty_daily_workload AS
SELECT 
    t.faculty_id,
    f.name AS faculty_name,
    t.day_of_week,
    COUNT(*) AS total_sessions,
    SUM(TIME_TO_SEC(TIMEDIFF(t.end_time, t.start_time)) / 3600) AS total_hours,
    GROUP_CONCAT(DISTINCT c.code ORDER BY c.code) AS courses_taught
FROM timetable t
JOIN faculty f ON f.user_id = t.faculty_id
JOIN courses c ON c.id = t.course_id
GROUP BY t.faculty_id, f.name, t.day_of_week;

-- ============================================================================
-- 7. CREATE CROSS-COURSE COLLISION DETECTION VIEW
-- ============================================================================

CREATE OR REPLACE VIEW v_faculty_schedule_conflicts AS
SELECT 
    t1.faculty_id,
    f.name AS faculty_name,
    t1.day_of_week,
    t1.start_time,
    t1.end_time,
    t1.course_id AS course1_id,
    c1.code AS course1_code,
    c1.name AS course1_name,
    t1.class_id AS class1_id,
    t2.course_id AS course2_id,
    c2.code AS course2_code,
    c2.name AS course2_name,
    t2.class_id AS class2_id,
    'Time Overlap' AS conflict_reason
FROM timetable t1
JOIN timetable t2 ON 
    t1.faculty_id = t2.faculty_id 
    AND t1.day_of_week = t2.day_of_week
    AND t1.id < t2.id
    AND (
        (t1.start_time < t2.end_time AND t1.end_time > t2.start_time)
    )
JOIN faculty f ON f.user_id = t1.faculty_id
JOIN courses c1 ON c1.id = t1.course_id
JOIN courses c2 ON c2.id = t2.course_id;

-- ============================================================================
-- 8. UPDATE EXISTING DATA WITH DEFAULTS
-- ============================================================================

-- Set default lecture durations based on course name patterns
UPDATE courses 
SET lecture_duration_minutes = 60,
    max_sessions_per_day = 4,
    course_level = 'PG'
WHERE (name LIKE '%MSc%' OR name LIKE '%M.Sc%' OR name LIKE '%Master%' OR name LIKE '%MCA%');

UPDATE courses 
SET lecture_duration_minutes = 45,
    max_sessions_per_day = 6,
    course_level = 'UG'
WHERE (name LIKE '%BSc%' OR name LIKE '%B.Sc%' OR name LIKE '%BCA%' OR name LIKE '%Bachelor%');

UPDATE courses 
SET lecture_duration_minutes = 45,
    max_sessions_per_day = 5,
    course_level = 'Diploma'
WHERE name LIKE '%Diploma%';

-- ============================================================================
-- 9. CREATE STORED PROCEDURE FOR FACULTY COLLISION CHECK
-- ============================================================================

DELIMITER $$

DROP PROCEDURE IF EXISTS sp_check_faculty_collision$$

CREATE PROCEDURE sp_check_faculty_collision(
    IN p_faculty_id INT,
    IN p_day VARCHAR(20),
    IN p_start_time TIME,
    IN p_end_time TIME,
    IN p_exclude_timetable_id INT
)
BEGIN
    -- Check if faculty has conflicting sessions
    SELECT 
        t.id,
        t.course_id,
        c.code AS course_code,
        c.name AS course_name,
        t.class_id,
        t.day_of_week,
        t.start_time,
        t.end_time,
        s.name AS subject_name
    FROM timetable t
    JOIN courses c ON c.id = t.course_id
    LEFT JOIN subjects s ON s.id = t.subject_id
    WHERE t.faculty_id = p_faculty_id
      AND t.day_of_week = p_day
      AND (t.id != p_exclude_timetable_id OR p_exclude_timetable_id IS NULL)
      AND (
          (p_start_time < t.end_time AND p_end_time > t.start_time)
      );
END$$

DELIMITER ;

-- ============================================================================
-- 10. CREATE DIAGNOSTIC QUERIES FOR TROUBLESHOOTING
-- ============================================================================

-- Check subject configuration
SELECT 
    'Subject Configuration Check' AS check_type,
    s.id,
    s.name,
    s.course_code AS subject_code,
    c.code AS course_code,
    c.name AS course_name,
    s.theory_practical,
    s.lectures_per_week,
    s.practical_hours_per_week,
    (s.lectures_per_week + CEIL(s.practical_hours_per_week / 2)) AS total_sessions_needed,
    COUNT(fa.id) AS faculty_count
FROM subjects s
JOIN courses c ON c.id = s.course_id
LEFT JOIN faculty_allocations fa ON fa.subject_id = s.id
WHERE c.id = 3  -- MSc Data Analytics
GROUP BY s.id, s.name, s.course_code, c.code, c.name,
         s.theory_practical, s.lectures_per_week, s.practical_hours_per_week;

-- Check faculty allocations
SELECT 
    'Faculty Allocation Check' AS check_type,
    s.name AS subject,
    f.name AS faculty,
    fa.is_primary,
    f.max_hours_per_week AS faculty_max_hours
FROM faculty_allocations fa
JOIN subjects s ON s.id = fa.subject_id
JOIN faculty f ON f.user_id = fa.faculty_id
WHERE s.course_id = 3
ORDER BY s.name, fa.is_primary DESC;

-- Check faculty availability
SELECT 
    'Faculty Availability Check' AS check_type,
    f.name AS faculty,
    fav.day_of_week,
    fav.start_time,
    fav.end_time,
    fav.is_available,
    COALESCE(fav.teaching_hours_per_day, 6.0) AS max_hours_per_day
FROM faculty f
LEFT JOIN faculty_availability fav ON fav.faculty_id = f.user_id
WHERE f.user_id IN (
    SELECT DISTINCT fa.faculty_id 
    FROM faculty_allocations fa 
    JOIN subjects s ON s.id = fa.subject_id 
    WHERE s.course_id = 3
)
ORDER BY f.name, fav.day_of_week;

-- ============================================================================
-- VERIFICATION & SUMMARY
-- ============================================================================

SELECT '=== MIGRATION SUMMARY ===' AS summary;

SELECT 'Timetable History Table' AS component,
       CASE WHEN COUNT(*) > 0 THEN 'Created' ELSE 'Not Found' END AS status
FROM information_schema.tables 
WHERE table_schema = DATABASE() AND table_name = 'timetable_history'
UNION ALL
SELECT 'Conflicts Log Table',
       CASE WHEN COUNT(*) > 0 THEN 'Created' ELSE 'Not Found' END
FROM information_schema.tables 
WHERE table_schema = DATABASE() AND table_name = 'timetable_conflicts'
UNION ALL
SELECT 'Proxy Assignments Table',
       CASE WHEN COUNT(*) > 0 THEN 'Created' ELSE 'Not Found' END
FROM information_schema.tables 
WHERE table_schema = DATABASE() AND table_name = 'proxy_assignments'
UNION ALL
SELECT 'Course Lecture Duration Column',
       CASE WHEN COUNT(*) > 0 THEN 'Added' ELSE 'Not Found' END
FROM information_schema.columns 
WHERE table_schema = DATABASE() 
  AND table_name = 'courses' 
  AND column_name = 'lecture_duration_minutes'
UNION ALL
SELECT 'Faculty Shift Management Columns',
       CASE WHEN COUNT(*) > 0 THEN 'Added' ELSE 'Not Found' END
FROM information_schema.columns 
WHERE table_schema = DATABASE() 
  AND table_name = 'faculty_availability' 
  AND column_name = 'teaching_hours_per_day';

SELECT '=== READY FOR ENTERPRISE TIMETABLE GENERATION ===' AS status;
