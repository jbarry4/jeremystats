@echo off
title BARRY GUI - Setup
cd /d "%~dp0"

echo.
echo   BARRY GUI setup
echo   ---------------
echo.

rem Find a usable Python. The py launcher is the reliable one on Windows.
set "PYEXE="
where py >nul 2>&1
if %errorlevel%==0 set "PYEXE=py -3"
if not defined PYEXE (
    where python >nul 2>&1
    if %errorlevel%==0 set "PYEXE=python"
)

if not defined PYEXE (
    echo   Python was not found on this machine.
    echo.
    echo   Install it, then run this setup again:
    echo.
    echo     Option A - winget:   winget install Python.Python.3.12
    echo     Option B - download: https://www.python.org/downloads/windows/
    echo.
    echo   IMPORTANT: tick "Add Python to PATH" in the installer.
    echo.
    pause
    exit /b 1
)

%PYEXE% setup.py
if %errorlevel% neq 0 (
    echo.
    echo   Setup did not finish cleanly. See the messages above.
    pause
)