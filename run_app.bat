@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
set "VENV_PY=.venv\Scripts\python.exe"
if not exist "%VENV_PY%" goto :need_install
"%VENV_PY%" -c "import sys" >nul 2>nul
if errorlevel 1 goto :need_install
goto :run_app

:need_install
call :message venv_missing
call :message install_question
choice /C YN /N /M "Y=yes, N=no"
if errorlevel 2 goto :setup_cancelled
call "%~dp0install.bat"
set "INSTALL_EXIT=%ERRORLEVEL%"
set "LAUNCHER_INSTALL_EXIT=%INSTALL_EXIT%"
if not "%INSTALL_EXIT%"=="0" goto :install_failed
if not exist "%VENV_PY%" goto :install_failed

:run_app
"%VENV_PY%" app_entry.py
set "APP_EXIT=%ERRORLEVEL%"
if not "%APP_EXIT%"=="0" goto :app_failed
endlocal & exit /b 0

:setup_cancelled
call :message setup_cancelled
pause
endlocal & exit /b 1
:install_failed
call :message install_failed
pause
endlocal & exit /b %INSTALL_EXIT%
:app_failed
set "LAUNCHER_APP_EXIT=%APP_EXIT%"
call :message app_failed
call :message logs_location
pause
endlocal & exit /b %APP_EXIT%
:message
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher_messages.ps1" "%~1"
exit /b %ERRORLEVEL%
