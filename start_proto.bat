@echo off
title Proto v3 - Shop Management System
cd /d "%~dp0"

REM Activate virtual environment
if not exist "venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found.
    echo Please run install_windows.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

REM Open browser then start server
start "" http://localhost:8000
python manage.py runserver 127.0.0.1:8000