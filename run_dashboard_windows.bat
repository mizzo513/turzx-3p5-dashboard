@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (echo Please run START_HERE_Setup_and_Run.bat first.&pause&exit /b 1)
start "" wscript.exe "%~dp0Start_Display_Hidden.vbs"
echo Started the dashboard without a console.
echo Use Open_Live_Settings.vbs to change options or stop the program.
exit /b 0
