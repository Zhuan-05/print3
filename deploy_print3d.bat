@echo off
setlocal
chcp 65001 >nul
title Print3D - Automatic Deployment
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\deploy_windows.ps1" -Mode "%~1"
set "DEPLOY_RESULT=%ERRORLEVEL%"
if not "%DEPLOY_RESULT%"=="0" (
  echo Deployment stopped. Read the message above, fix it, and double-click again.
  pause
)
exit /b %DEPLOY_RESULT%
