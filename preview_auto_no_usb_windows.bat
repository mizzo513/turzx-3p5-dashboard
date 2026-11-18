@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run START_HERE_Setup_and_Run.bat first.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" turzx_dashboard.py --no-usb
pause
