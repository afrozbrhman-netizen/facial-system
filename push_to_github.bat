@echo off
title Push Facial System to GitHub
cd /d "%~dp0"
echo =================================================================
echo   Current Folder: %CD%
echo   Pushing to: https://github.com/afrozbrhman-netizen/facial-system.git
echo =================================================================
echo.
git push -u origin main
echo.
echo =================================================================
pause
