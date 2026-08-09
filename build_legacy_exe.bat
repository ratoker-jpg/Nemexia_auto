@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
set "VENV_PY=.venv\Scripts\python.exe"
if not exist "%VENV_PY%" goto :missing_venv
"%VENV_PY%" -c "import app_entry" >nul 2>nul
if errorlevel 1 goto :missing_venv
call :message build_requirements
"%VENV_PY%" -m pip install -r requirements-build.txt
if errorlevel 1 goto :build_requirements_error
rmdir /s /q build\NemexiaRaidManagerLegacy 2>nul
del /q dist\NemexiaRaidManagerLegacy.exe 2>nul
"%VENV_PY%" -m PyInstaller NemexiaRaidManagerLegacy.spec --noconfirm
if errorlevel 1 goto :pyinstaller_error
echo Готово: dist\NemexiaRaidManagerLegacy.exe
if /i "%~1"=="--pause" pause
endlocal & exit /b 0

:missing_venv
set "ERROR_KEY=venv_missing_build"
goto :error
:build_requirements_error
set "ERROR_KEY=build_requirements_error"
goto :error
:pyinstaller_error
set "ERROR_KEY=pyinstaller_error"
:error
set "EXIT_CODE=%ERRORLEVEL%"
if "%EXIT_CODE%"=="0" set "EXIT_CODE=1"
echo.
call :message %ERROR_KEY%
pause
endlocal & exit /b %EXIT_CODE%
:message
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher_messages.ps1" "%~1"
exit /b %ERRORLEVEL%
