@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (echo Please run START_HERE_Setup_and_Run.bat first.&pause&exit /b 1)
start "" wscript.exe "%~dp0Open_Live_Settings.vbs"
exit /b 0
