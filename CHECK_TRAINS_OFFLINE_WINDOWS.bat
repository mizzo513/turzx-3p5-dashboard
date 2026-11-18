@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" CHECK_TRAINS_OFFLINE.py
) else (
  py -3 CHECK_TRAINS_OFFLINE.py
)
echo.
echo If you share the diagnostic report, remove personal paths or identifiers first.
pause
