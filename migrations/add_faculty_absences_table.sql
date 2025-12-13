-- Create faculty_absences table for Teacher Panel
USE college_timetable_db;

CREATE TABLE IF NOT EXISTS `faculty_absences` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `faculty_id` INT NOT NULL,
  `absence_date` DATE NOT NULL,
  `reason` TEXT,
  `status` ENUM('PROCESSED', 'UNPROCESSED') DEFAULT 'UNPROCESSED',
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (`faculty_id`) REFERENCES `faculty`(`id`) ON DELETE CASCADE,
  INDEX idx_faculty_date (`faculty_id`, `absence_date`),
  INDEX idx_status (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Verify the table structure
DESCRIBE faculty_absences;
