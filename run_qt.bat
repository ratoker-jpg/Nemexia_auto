@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
set "VENV_PY=.venv\Scripts\python.exe"

if exist "%VENV_PY%" (
  "%VENV_PY%" -c "import PySide6, app_qt" >nul 2>nul
  if not errorlevel 1 goto :run_qt
)

call :message launcher_install
call "%~dp0install.bat"
set "INSTALL_EXIT=%ERRORLEVEL%"
set "LAUNCHER_INSTALL_EXIT=%INSTALL_EXIT%"
if not "%INSTALL_EXIT%"=="0" goto :install_failed

:run_qt
"%VENV_PY%" app_qt.py
set "APP_EXIT=%ERRORLEVEL%"
if not "%APP_EXIT%"=="0" (
  set "LAUNCHER_APP_EXIT=%APP_EXIT%"
  call :message qt_app_failed
  call :message qt_logs_location
)
endlocal & exit /b %APP_EXIT%

:install_failed
call :message install_failed
pause
endlocal & exit /b %INSTALL_EXIT%

:message
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher_messages.ps1" "%~1"
exit /b %ERRORLEVEL%
