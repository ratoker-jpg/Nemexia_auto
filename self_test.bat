@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Сначала запусти install.bat
  pause
  exit /b 1
)
".venv\Scripts\python.exe" self_test.py
pause
