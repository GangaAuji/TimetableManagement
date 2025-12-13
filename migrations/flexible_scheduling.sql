-- ============================================================================
-- FLEXIBLE TIMETABLE SCHEDULING - CONFIGURATION & UTILITIES
-- ============================================================================
-- Purpose: Support flexible session counts based on faculty availability
-- Requirement: "In a week, sometimes 22 or 24 sessions - schedule one after another"
-- ============================================================================

USE college_timetable_db;

-- ============================================================================
-- 1. CREATE SESSION REQUIREMENTS TABLE (Flexible Target Sessions)
-- ============================================================================

CREATE TABLE IF NOT EXISTS timetable_session_targets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    course_id INT NOT NULL,
    class_id INT,
    division_id INT,
    week_start_date DATE NOT NULL,
    target_sessions INT NOT NULL DEFAULT 24 COMMENT 'Ideal number of sessions to schedule',
    minimum_sessions INT NOT NULL DEFAULT 20 COMMENT 'Minimum acceptable sessions',
    actual_sessions INT DEFAULT 0 COMMENT 'Actually scheduled sessions',
    generation_status ENUM('pending', 'in_progress', 'completed', 'failed') DEFAULT 'pending',
    generation_timestamp DATETIME,
    generation_notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_course_class (course_id, class_id, division_id),
    INDEX idx_week_start (week_start_date),
    FOREIGN KEY (course_id) REFERENCES courses(id),
    FOREIGN KEY (class_id) REFERENCES classes(id),
    FOREIGN KEY (division_id) REFERENCES divisions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 2. CREATE UNSCHEDULED SESSIONS LOG
-- ============================================================================

CREATE TABLE IF NOT EXISTS unscheduled_sessions_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    generation_timestamp DATETIME NOT NULL,
    course_id INT NOT NULL,
    class_id INT,
    division_id INT,
    subject_id INT NOT NULL,
    session_type ENUM('Theory', 'Practical', 'Both') DEFAULT 'Theory',
    required_slots INT DEFAULT 1,
    reason VARCHAR(255) COMMENT 'Why it could not be scheduled',
    suggested_day VARCHAR(20),
    suggested_time_start TIME,
    suggested_time_end TIME,
    resolved TINYINT(1) DEFAULT 0,
    resolution_notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_generation (generation_timestamp),
    INDEX idx_subject (subject_id),
    INDEX idx_resolved (resolved)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 3. FLEXIBLE SCHEDULING SETTINGS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS timetable_generation_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    course_id INT NOT NULL,
    setting_key VARCHAR(100) NOT NULL,
    setting_value VARCHAR(255) NOT NULL,
    description TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_course_setting (course_id, setting_key),
    FOREIGN KEY (course_id) REFERENCES courses(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 4. INSERT DEFAULT FLEXIBLE SCHEDULING SETTINGS
-- ============================================================================

-- For MSc Data Analytics (course_id = 3)
INSERT INTO timetable_generation_settings (course_id, setting_key, setting_value, description)
VALUES 
    (3, 'allow_flexible_sessions', '1', 'Allow 20-24 sessions per week based on availability'),
    (3, 'min_sessions_per_week', '20', 'Minimum sessions that must be scheduled'),
    (3, 'target_sessions_per_week', '24', 'Ideal number of sessions to schedule'),
    (3, 'max_sessions_per_week', '24', 'Maximum sessions allowed per week'),
    (3, 'prefer_consecutive_slots', '1', 'Try to schedule same subject in consecutive slots'),
    (3, 'allow_multi_subject_per_day', '1', 'Allow same subject multiple times per day'),
    (3, 'min_slots_per_subject_per_week', '4', 'Each subject should have at least 4 slots'),
    (3, 'max_gap_between_sessions', '1', 'Maximum days gap between sessions of same subject')
ON DUPLICATE KEY UPDATE 
    setting_value = VALUES(setting_value),
    description = VALUES(description);

-- ============================================================================
-- 5. CREATE VIEW: SCHEDULING FLEXIBILITY REPORT
-- ============================================================================

CREATE OR REPLACE VIEW v_scheduling_flexibility AS
SELECT 
    c.code AS course_code,
    c.name AS course_name,
    COUNT(DISTINCT s.id) AS total_subjects,
    SUM(s.lectures_per_week) AS total_theory_lectures,
    SUM(CEIL(s.practical_hours_per_week / 2)) AS total_practical_sessions,
    SUM(s.lectures_per_week + CEIL(s.practical_hours_per_week / 2)) AS total_required_sessions,
    COALESCE(
        (SELECT setting_value FROM timetable_generation_settings 
         WHERE course_id = c.id AND setting_key = 'min_sessions_per_week'), 
        '20'
    ) AS min_acceptable_sessions,
    COALESCE(
        (SELECT setting_value FROM timetable_generation_settings 
         WHERE course_id = c.id AND setting_key = 'target_sessions_per_week'), 
        '24'
    ) AS target_sessions,
    (SELECT COUNT(*) FROM faculty_allocations fa 
     JOIN subjects s2 ON s2.id = fa.subject_id 
     WHERE s2.course_id = c.id) AS total_faculty_allocations
FROM courses c
LEFT JOIN subjects s ON s.course_id = c.id
GROUP BY c.id, c.code, c.name;

-- ============================================================================
-- 6. STORED PROCEDURE: UPDATE SESSION TARGET AFTER GENERATION
-- ============================================================================

DELIMITER $$

DROP PROCEDURE IF EXISTS sp_log_generation_result$$

CREATE PROCEDURE sp_log_generation_result(
    IN p_course_id INT,
    IN p_class_id INT,
    IN p_division_id INT,
    IN p_week_start DATE,
    IN p_actual_sessions INT,
    IN p_status VARCHAR(20),
    IN p_notes TEXT
)
BEGIN
    DECLARE v_target INT DEFAULT 24;
    
    -- Get target sessions from settings
    SELECT CAST(setting_value AS UNSIGNED) INTO v_target
    FROM timetable_generation_settings
    WHERE course_id = p_course_id 
      AND setting_key = 'target_sessions_per_week'
    LIMIT 1;
    
    -- Insert or update session target record
    INSERT INTO timetable_session_targets 
        (course_id, class_id, division_id, week_start_date, 
         target_sessions, actual_sessions, generation_status, 
         generation_timestamp, generation_notes)
    VALUES 
        (p_course_id, p_class_id, p_division_id, p_week_start,
         v_target, p_actual_sessions, p_status,
         NOW(), p_notes)
    ON DUPLICATE KEY UPDATE
        actual_sessions = p_actual_sessions,
        generation_status = p_status,
        generation_timestamp = NOW(),
        generation_notes = p_notes;
        
    -- Return success indicator
    SELECT 
        v_target AS target_sessions,
        p_actual_sessions AS actual_sessions,
        (p_actual_sessions >= v_target * 0.83) AS meets_minimum,
        CONCAT(ROUND(p_actual_sessions / v_target * 100, 1), '%') AS fulfillment_rate;
END$$

DELIMITER ;

-- ============================================================================
-- 7. QUERY: FIND BEST CONSECUTIVE SLOT OPPORTUNITIES
-- ============================================================================

-- This query finds days with consecutive free slots for scheduling
-- Use this to optimize "schedule one after another" requirement

CREATE OR REPLACE VIEW v_consecutive_slot_opportunities AS
SELECT 
    c.code AS course_code,
    c.name AS course_name,
    cl.name AS class_name,
    d.name AS division_name,
    days.day_name,
    TIME('09:00:00') AS slot_start,
    TIME('17:00:00') AS slot_end,
    TIMESTAMPDIFF(HOUR, TIME('09:00:00'), TIME('17:00:00')) AS available_hours,
    COALESCE(scheduled.occupied_hours, 0) AS occupied_hours,
    (TIMESTAMPDIFF(HOUR, TIME('09:00:00'), TIME('17:00:00')) - COALESCE(scheduled.occupied_hours, 0)) AS free_hours,
    FLOOR((TIMESTAMPDIFF(HOUR, TIME('09:00:00'), TIME('17:00:00')) - COALESCE(scheduled.occupied_hours, 0)) / 
          (c.lecture_duration_minutes / 60.0)) AS max_consecutive_sessions
FROM courses c
CROSS JOIN classes cl
CROSS JOIN divisions d
CROSS JOIN (
    SELECT 'Monday' AS day_name UNION
    SELECT 'Tuesday' UNION
    SELECT 'Wednesday' UNION
    SELECT 'Thursday' UNION
    SELECT 'Friday' UNION
    SELECT 'Saturday'
) days
LEFT JOIN (
    SELECT 
        course_id,
        class_id,
        division_id,
        day_of_week,
        SUM(TIMESTAMPDIFF(HOUR, start_time, end_time)) AS occupied_hours
    FROM timetable
    GROUP BY course_id, class_id, division_id, day_of_week
) scheduled ON 
    scheduled.course_id = c.id AND
    scheduled.class_id = cl.id AND
    scheduled.division_id = d.id AND
    scheduled.day_of_week = days.day_name
WHERE c.id = 3  -- MSc Data Analytics
  AND cl.id = 1  -- FY
  AND d.id = 1;  -- Division 1

-- ============================================================================
-- 8. PRACTICAL QUERY: DISTRIBUTE 22 SESSIONS ACROSS 6 DAYS
-- ============================================================================

-- Example distribution strategies:

-- Strategy 1: Balanced (3-4 sessions per day)
SELECT 'Strategy 1: Balanced Distribution' AS strategy;
SELECT 
    'Monday' AS day, 4 AS sessions UNION
    SELECT 'Tuesday', 4 UNION
    SELECT 'Wednesday', 4 UNION
    SELECT 'Thursday', 4 UNION
    SELECT 'Friday', 3 UNION
    SELECT 'Saturday', 3;

-- Strategy 2: Front-loaded (more at week start)
SELECT 'Strategy 2: Front-loaded Distribution' AS strategy;
SELECT 
    'Monday' AS day, 4 AS sessions UNION
    SELECT 'Tuesday', 4 UNION
    SELECT 'Wednesday', 4 UNION
    SELECT 'Thursday', 4 UNION
    SELECT 'Friday', 3 UNION
    SELECT 'Saturday', 3;

-- Strategy 3: Continuous blocks (minimize gaps)
SELECT 'Strategy 3: Continuous Block Distribution' AS strategy;
SELECT 
    'Monday' AS day, 5 AS sessions, 'Back-to-back slots' AS notes UNION
    SELECT 'Tuesday', 4, 'Consecutive subjects' UNION
    SELECT 'Wednesday', 4, 'Continuous flow' UNION
    SELECT 'Thursday', 4, 'Minimize breaks' UNION
    SELECT 'Friday', 3, 'Light day' UNION
    SELECT 'Saturday', 2, 'Weekend minimal';

-- ============================================================================
-- 9. UPDATE SUBJECT CONFIGURATION (OPTIONAL - FIX TO 24)
-- ============================================================================

-- Option A: Make all subjects 6 lectures each = 24 total
-- UPDATE subjects 
-- SET lectures_per_week = 6,
--     practical_hours_per_week = 0
-- WHERE course_id = 3;

-- Option B: Adjust one subject to reach 24
-- UPDATE subjects 
-- SET lectures_per_week = 6
-- WHERE course_id = 3 AND name LIKE '%Digital Footprints%';

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

SELECT '=== FLEXIBLE SCHEDULING CONFIGURATION ===' AS info;

SELECT * FROM timetable_generation_settings WHERE course_id = 3;

SELECT '=== SCHEDULING FLEXIBILITY REPORT ===' AS info;

SELECT * FROM v_scheduling_flexibility WHERE course_code = 'MSC-DA';

SELECT '=== CONSECUTIVE SLOT OPPORTUNITIES ===' AS info;

SELECT * FROM v_consecutive_slot_opportunities;

SELECT '=== READY FOR FLEXIBLE GENERATION ===' AS status;
