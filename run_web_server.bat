@echo off
title Attendance Studio 2.0 - Web Server
cd /d "%~dp0"
echo =================================================================
echo   Starting Attendance Management Studio Web Server...
echo   URL: http://localhost:5000
echo =================================================================
start http://localhost:5000
python run_server.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Trying direct Python 3.10 path...
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" run_server.py
)
pause
