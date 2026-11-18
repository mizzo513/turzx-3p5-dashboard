@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title TURZX 3.5 - One Click Setup and Run
chcp 65001 >nul 2>&1
echo =============================================================
echo  TURZX 3.5 - ONE CLICK SETUP AND RUN [V3.6]
echo  USB35INCHIPSV2 / Windows 10 or 11 64-bit
echo =============================================================
echo.
echo This script may install Python from an official source,
echo create a private Python environment, install Pillow/pyserial,
echo detect your display and start the dashboard.
echo Internet connection is needed for first-time installation.
echo.
set "PSFILE=%~dp0tools\bootstrap.ps1"
if not exist "%PSFILE%" (
  echo ERROR: tools\bootstrap.ps1 not found. Extract the full ZIP.
  pause
  exit /b 2
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PSFILE%" -Root "%~dp0." -AutoLaunch
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" (
    echo SETUP FAILED. Check logs\setup_install.log
) else (
    echo SETUP FINISHED. Check display and logs\dashboard.log.
)
pause
exit /b %RESULT%
