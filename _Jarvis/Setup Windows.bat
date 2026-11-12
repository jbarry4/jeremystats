@echo off
setlocal
title Jarvis - Setup
rem Everything but the launchers lives in app\ beside this file.
cd /d "%~dp0app"

echo.
echo   Jarvis setup
echo   ------------
echo.

rem A Python that really runs. Not just "where python": on a new computer that
rem finds the Microsoft Store's stand-in, which runs nothing. And not inside a
rem bracketed block either, where %%errorlevel%% is read before the block runs.
call :findpy
if defined PYEXE goto havepy

echo   Python is not on this computer yet. Installing it for you...
echo.
call :installpy
call :findpy
if defined PYEXE goto havepy

echo.
echo   Python could not be installed from here.
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

:havepy
echo   Using %PYEXE%
"%PYEXE%" setup.py
if errorlevel 1 (
    echo.
    echo   Setup did not finish cleanly. See the messages above.
    pause
)
exit /b

rem ---------------------------------------------------------------------------
rem The full path of a Python that runs, in PYEXE, or PYEXE left empty. Asked
rem of the py launcher, then of "python", then of the places an installer
rem puts it -- the last so that a Python installed a moment ago by this very
rem window is found without the window being closed and opened again.
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

rem winget when there is one: no questions, no admin, just this person.
rem Otherwise the Microsoft Store's page, and a wait here until it is in --
rem the Store's Python answers to "python" in this same window afterwards.
:installpy
where winget >nul 2>&1
if errorlevel 1 goto storepy
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
goto :eof
:storepy
echo   Opening the Microsoft Store at Python 3.12. Press Get, wait for it to
echo   finish installing, then come back here.
start "" "ms-windows-store://pdp/?productid=9NCVDN91XZQP"
echo.
pause
goto :eof
