@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo =============================================================
echo TURZX V3.3 - Resume setup with existing Python environment
echo =============================================================
if not exist "tools\bootstrap.ps1" (
 echo ERROR: Missing tools\bootstrap.ps1
 pause
 exit /b 2
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\bootstrap.ps1" -Root "%~dp0." -AutoLaunch
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo ERROR: check logs\setup_install.log
pause
exit /b %RESULT%
