@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHON="
if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"
if not defined PYTHON (
  py -3 --version >nul 2>nul
  if not errorlevel 1 set "PYTHON=py -3"
)
if not defined PYTHON (
  where python >nul 2>nul
  if not errorlevel 1 set "PYTHON=python"
)
if not defined PYTHON (
  echo Python is not found. Run START_HERE_Setup_and_Run.bat first.
  pause
  exit /b 1
)
echo ====================================================
echo TURZX 3.5 v3.6.2 - EXE and UPDATE ZIP BUILDER
echo ====================================================
%PYTHON% tools\build_release.py
if errorlevel 1 goto failure
if not exist "dist\TURZX_3p5_Dashboard.exe" goto failure
echo.
echo SUCCESS: dist\TURZX_3p5_Dashboard.exe
echo Update ZIP: dist\TURZX_Update_v3.6.2.zip
echo This application manages updates from its Settings screen.
echo.
pause
exit /b 0
:failure
echo ERROR: Build failed. See above output.
pause
exit /b 1
