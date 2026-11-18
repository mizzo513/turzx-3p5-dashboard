@echo off
setlocal
cd /d "%~dp0"
call "%~dp0START_HERE_Setup_and_Run.bat"
exit /b %ERRORLEVEL%
