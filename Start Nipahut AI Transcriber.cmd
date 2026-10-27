@echo off
cd /d "%~dp0"
if exist "Nipahut AI Transcriber.exe" (
  start "" "%~dp0Nipahut AI Transcriber.exe"
  exit /b 0
)
if exist ".venv\Scripts\pythonw.exe" (
  start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0desktop.py"
  exit /b 0
)
echo The desktop executable is missing. Build it with scripts\build_desktop.ps1.
pause
exit /b 1
