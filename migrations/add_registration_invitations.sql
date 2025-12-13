-- Migration: Add registration invitation system
-- Run this SQL to add the invitation table

USE college_timetable_db;

-- Table for registration invitations
CREATE TABLE IF NOT EXISTS `registration_invitations` (
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
