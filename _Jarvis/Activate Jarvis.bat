@echo off
setlocal
title Jarvis
rem Everything but the launchers lives in app\ beside this file.
cd /d "%~dp0app"

rem The same search as "Setup Windows.bat": a Python that really runs.
call :findpy
if not defined PYEXE (
    echo   Python was not found. Run "Setup Windows.bat" first.
    pause
    exit /b 1
)

"%PYEXE%" start.py
if errorlevel 1 (
    echo.
    echo   Jarvis exited with an error. See the messages above.
    echo   If packages are missing, run "Setup Windows.bat".
    pause
)
exit /b

:findpy
set "PYEXE="
for /f "usebackq delims=" %%i in (`py -3 -c "import sys; print(sys.executable)" 2^>nul`) do set "PYEXE=%%i"
if defined PYEXE goto :eof
for /f "usebackq delims=" %%i in (`python -c "import sys; print(sys.executable)" 2^>nul`) do set "PYEXE=%%i"
if defined PYEXE goto :eof
for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%d\python.exe" set "PYEXE=%%d\python.exe"
if defined PYEXE goto :eof
for /d %%d in ("%ProgramFiles%\Python3*") do if exist "%%d\python.exe" set "PYEXE=%%d\python.exe"
goto :eof
