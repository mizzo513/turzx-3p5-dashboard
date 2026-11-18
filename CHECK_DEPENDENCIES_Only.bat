@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Application virtual environment not found. Run START_HERE_Setup_and_Run.bat.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" "tools\verify_env.py"
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo Validation failed. Run START_HERE_Setup_and_Run.bat.
pause
exit /b %RESULT%
