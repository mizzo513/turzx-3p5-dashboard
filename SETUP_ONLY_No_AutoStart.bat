@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\bootstrap.ps1" -Root "%~dp0." -SetupOnly
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" echo Setup failed. See logs\setup_install.log
pause
exit /b %CODE%
