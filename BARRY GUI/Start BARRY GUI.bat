@echo off
title BARRY GUI
cd /d "%~dp0"

set "PYEXE="
where py >nul 2>&1
if %errorlevel%==0 set "PYEXE=py -3"
if not defined PYEXE (
    where python >nul 2>&1
    if %errorlevel%==0 set "PYEXE=python"
)

if not defined PYEXE (
    echo   Python was not found. Run "Setup Windows.bat" first.
    pause
    exit /b 1
)

%PYEXE% start.py

if %errorlevel% neq 0 (
    echo.
    echo   BARRY GUI exited with an error. See the messages above.
    echo   If packages are missing, run "Setup Windows.bat".
    pause
)