@echo off
setlocal

cd /d "%~dp0"
title Cargo Transport Demo

set "PY_CMD="
where py >nul 2>nul
if %errorlevel%==0 set "PY_CMD=py"

if not defined PY_CMD (
    where python >nul 2>nul
    if %errorlevel%==0 set "PY_CMD=python"
)

if not defined PY_CMD (
    echo Python was not found.
    echo Install Python 3.11+ and run this file again.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo Installing dependencies...
call ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
)

echo Applying migrations...
call ".venv\Scripts\python.exe" manage.py migrate
if errorlevel 1 (
    echo Failed to apply migrations.
    pause
    exit /b 1
)

echo Loading demo data...
call ".venv\Scripts\python.exe" manage.py seed_demo
if errorlevel 1 (
    echo Failed to load demo data.
    pause
    exit /b 1
)

start "" http://127.0.0.1:8000/
echo Starting Django server on http://127.0.0.1:8000/
echo To stop the server, close this window or press Ctrl+C.
call ".venv\Scripts\python.exe" manage.py runserver

endlocal
