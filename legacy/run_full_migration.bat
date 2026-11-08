@echo off
setlocal

cd /d "%~dp0.."
python legacy\run_full_migration.py

if errorlevel 1 (
  echo.
  echo Migration failed.
  exit /b 1
)

echo.
echo Migration completed successfully.
endlocal
