@echo off
title Attendance Studio 2.0 - Desktop Application
cd /d "%~dp0"
echo =================================================================
echo   Starting Attendance Studio Desktop Application (Tkinter GUI)...
echo =================================================================
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Trying direct Python 3.10 path...
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" main.py
)
pause
