"""Catch-up: tables the code uses that college_timetable_db does not have.

Revision ID: 0002_catch_up
Revises: 0001_baseline
Create Date: 2026-11-08

faculty_attendance and faculty_attendance_logs are read and written by mobile
sync and the attendance admin screens. They exist in the MySQL 8.2 dump of
2026-04-03 but not on the MariaDB server. The definitions below follow that
dump, written for MariaDB: int(11) widths and utf8mb4_unicode_ci, which every
text column already used. The statements are idempotent, so a database that
already has the tables is left as it is.

Downgrade drops both tables and their rows.
"""
from alembic import op

revision = '0002_catch_up'
down_revision = '0001_baseline'
branch_labels = None
depends_on = None

FACULTY_ATTENDANCE = """
CREATE TABLE IF NOT EXISTS `faculty_attendance` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `faculty_id` int(11) NOT NULL,
  `faculty_user_id` int(11) NOT NULL,
  `attendance_date` date NOT NULL,
  `day_of_week` tinyint(4) NOT NULL COMMENT '1=Monday, 7=Sunday',
  `shift_key` int(11) NOT NULL DEFAULT 0 COMMENT 'shift_pattern_id, or derived custom shift key',
  `shift_pattern_id` int(11) DEFAULT NULL,
  `shift_name` varchar(100) DEFAULT NULL,
  `shift_code` varchar(20) DEFAULT NULL,
  `shift_start_time` time DEFAULT NULL,
  `shift_end_time` time DEFAULT NULL,
  `status` enum('Present','Absent','Late') NOT NULL DEFAULT 'Present',
  `marked_by_user_id` int(11) NOT NULL,
  `source` enum('mobile_face','manual','admin') NOT NULL DEFAULT 'mobile_face',
  `captured_at` datetime DEFAULT NULL,
  `confidence` decimal(5,4) DEFAULT NULL,
  `remarks` varchar(255) DEFAULT NULL,
  `marked_at` timestamp NULL DEFAULT current_timestamp(),
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_faculty_attendance_unique` (`faculty_id`,`attendance_date`,`shift_key`),
  KEY `idx_faculty_attendance_user_date` (`faculty_user_id`,`attendance_date`),
  KEY `idx_faculty_attendance_shift_pattern` (`shift_pattern_id`),
  KEY `fk_faculty_attendance_marked_by_user` (`marked_by_user_id`),
  CONSTRAINT `fk_faculty_attendance_faculty` FOREIGN KEY (`faculty_id`) REFERENCES `faculty` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_faculty_attendance_faculty_user` FOREIGN KEY (`faculty_user_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_faculty_attendance_marked_by_user` FOREIGN KEY (`marked_by_user_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_faculty_attendance_shift_pattern` FOREIGN KEY (`shift_pattern_id`) REFERENCES `shift_patterns` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

FACULTY_ATTENDANCE_LOGS = """
CREATE TABLE IF NOT EXISTS `faculty_attendance_logs` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `event_uuid` varchar(64) NOT NULL,
  `device_id` varchar(128) NOT NULL,
  `faculty_id` int(11) NOT NULL,
  `faculty_user_id` int(11) NOT NULL,
  `attendance_date` date NOT NULL,
  `day_of_week` tinyint(4) NOT NULL COMMENT '1=Monday, 7=Sunday',
  `shift_key` int(11) NOT NULL DEFAULT 0 COMMENT 'shift_pattern_id, or derived custom shift key',
  `shift_pattern_id` int(11) DEFAULT NULL,
  `shift_name` varchar(100) DEFAULT NULL,
  `shift_code` varchar(20) DEFAULT NULL,
  `shift_start_time` time DEFAULT NULL,
  `shift_end_time` time DEFAULT NULL,
  `status` enum('Present','Absent','Late') NOT NULL DEFAULT 'Present',
  `marked_by_user_id` int(11) NOT NULL,
  `captured_at` datetime DEFAULT NULL,
  `confidence` decimal(5,4) DEFAULT NULL,
  `face_model` varchar(120) DEFAULT NULL,
  `detector_model` varchar(120) DEFAULT NULL,
  `remarks` varchar(255) DEFAULT NULL,
  `processing_status` enum('pending','processed','failed') NOT NULL DEFAULT 'pending',
  `error_message` varchar(500) DEFAULT NULL,
  `raw_payload` longtext DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `processed_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_faculty_attendance_logs_event_uuid` (`event_uuid`),
  KEY `idx_faculty_attendance_logs_processing_status` (`processing_status`),
  KEY `idx_faculty_attendance_logs_created_at` (`created_at`),
  KEY `idx_faculty_attendance_logs_faculty_date` (`faculty_id`,`attendance_date`),
  KEY `idx_faculty_attendance_logs_shift` (`attendance_date`,`shift_key`),
  KEY `fk_faculty_attendance_logs_faculty_user` (`faculty_user_id`),
  KEY `fk_faculty_attendance_logs_shift_pattern` (`shift_pattern_id`),
  KEY `fk_faculty_attendance_logs_marked_by_user` (`marked_by_user_id`),
  CONSTRAINT `fk_faculty_attendance_logs_faculty` FOREIGN KEY (`faculty_id`) REFERENCES `faculty` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_faculty_attendance_logs_faculty_user` FOREIGN KEY (`faculty_user_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_faculty_attendance_logs_marked_by_user` FOREIGN KEY (`marked_by_user_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_faculty_attendance_logs_shift_pattern` FOREIGN KEY (`shift_pattern_id`) REFERENCES `shift_patterns` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def upgrade():
    op.execute(FACULTY_ATTENDANCE)
    op.execute(FACULTY_ATTENDANCE_LOGS)


def downgrade():
    op.execute('DROP TABLE IF EXISTS `faculty_attendance_logs`')
    op.execute('DROP TABLE IF EXISTS `faculty_attendance`')
