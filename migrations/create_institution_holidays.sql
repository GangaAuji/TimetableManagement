-- Create institution_holidays table if it does not exist
CREATE TABLE IF NOT EXISTS institution_holidays (
    id INT AUTO_INCREMENT PRIMARY KEY,
    holiday_date DATE DEFAULT NULL,
    day_of_week ENUM('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday') DEFAULT NULL,
    name VARCHAR(120) NOT NULL,
    applies_to_program ENUM('UG','PG','Both') DEFAULT 'Both',
    is_recurring TINYINT(1) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_holiday_date (holiday_date, applies_to_program),
    KEY idx_holiday_day (day_of_week)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Ensure at least one weekly holiday for Sunday
INSERT INTO institution_holidays (holiday_date, day_of_week, name, applies_to_program, is_recurring)
SELECT NULL, 'Sunday', 'Weekly Off', 'Both', 1
WHERE NOT EXISTS (
    SELECT 1 FROM institution_holidays
    WHERE day_of_week = 'Sunday' AND is_recurring = 1
);
