@echo off
REM Windows Batch Script to Start the Training System
REM This provides a foolproof way to start the application on Windows

echo ==========================================
echo   TRAINING SYSTEM - STARTUP SCRIPT
echo ==========================================

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://python.org
    pause
    exit /b 1
)

REM Change to the script directory
cd /d "%~dp0"

REM Check if app.py exists
if not exist "app.py" (
    echo ERROR: app.py not found in current directory
    echo Current directory: %cd%
    pause
    exit /b 1
)

REM Try to start the server using the dedicated runner first
if exist "run_server.py" (
    echo Starting server using run_server.py...
    python run_server.py
) else (
    REM Fallback to direct app.py execution
    echo Starting server using app.py directly...
    python app.py
)

REM If we get here, the server has stopped
echo.
echo Server has stopped.
pause
