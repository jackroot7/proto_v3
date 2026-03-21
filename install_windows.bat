@echo off
title Proto v3 - Windows Installation
cd /d "%~dp0"
echo ============================================
echo  Proto v3 - Shop Management System
echo  Windows Installer
echo ============================================
echo.

REM Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://python.org
    echo Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo Python found. Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo Running database migrations...
python manage.py migrate
if errorlevel 1 (
    echo ERROR: Migration failed.
    pause
    exit /b 1
)

echo.
echo Setting up initial data (shops, owner, categories)...
python manage.py setup_proto

echo.
echo Adding Proto v3 to Windows startup...
echo Set oWS = WScript.CreateObject("WScript.Shell") > %TEMP%\mkshortcut.vbs
echo sLinkFile = oWS.SpecialFolders("Startup") ^& "\Proto v3.lnk" >> %TEMP%\mkshortcut.vbs
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> %TEMP%\mkshortcut.vbs
echo oLink.TargetPath = "%~dp0start_proto.bat" >> %TEMP%\mkshortcut.vbs
echo oLink.WorkingDirectory = "%~dp0" >> %TEMP%\mkshortcut.vbs
echo oLink.Description = "Proto v3 Shop Management" >> %TEMP%\mkshortcut.vbs
echo oLink.WindowStyle = 7 >> %TEMP%\mkshortcut.vbs
echo oLink.Save >> %TEMP%\mkshortcut.vbs
cscript /nologo %TEMP%\mkshortcut.vbs
del %TEMP%\mkshortcut.vbs

echo.
echo ============================================
echo  Installation complete!
echo.
echo  Proto v3 will now start automatically
echo  every time you turn on this computer.
echo.
echo  Open your browser and go to:
echo  http://localhost:8000
echo.
echo  Username : owner
echo  Password : proto2024
echo ============================================
echo.
echo Starting Proto v3 now...
start "" http://localhost:8000
python manage.py runserver 127.0.0.1:8000
