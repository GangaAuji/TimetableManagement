-- Add missing registration_invitations table to existing database
-- Run this to add the invitation system to your current database

USE college_timetable_db;

-- Create the registration_invitations table
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Update users table to include 'Super Admin' role if not already present
ALTER TABLE `users` MODIFY COLUMN `role` ENUM('Admin', 'Super Admin', 'Teacher', 'Student') NOT NULL;

-- Verify the table was created
SHOW TABLES LIKE 'registration_invitations';
DESCRIBE registration_invitations;