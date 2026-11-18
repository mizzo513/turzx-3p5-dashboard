@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" CHECK_NTP_CONNECTION.py
) else (
  py -3 CHECK_NTP_CONNECTION.py
)
pause
