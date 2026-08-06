@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"

set "PYTHON_CMD="
call :try_python py -3.11
if defined PYTHON_CMD goto :python_found
call :try_python py -3.10
if defined PYTHON_CMD goto :python_found
call :try_python python
if defined PYTHON_CMD goto :python_found
call :try_python python3
if defined PYTHON_CMD goto :python_found
set "ERROR_KEY=python_not_found"
set "EXIT_CODE=1"
goto :error

:python_found
set "LAUNCHER_PYTHON_VERSION=%PYTHON_VERSION%"
set "LAUNCHER_PYTHON_COMMAND=%PYTHON_CMD%"
call :message using_python
set "VENV_PY=.venv\Scripts\python.exe"
if exist "%VENV_PY%" goto :venv_ready
call :message create_venv
call %PYTHON_CMD% -m venv .venv
if errorlevel 1 goto :venv_create_error

:venv_ready
"%VENV_PY%" -c "import sys" >nul 2>nul
if errorlevel 1 goto :venv_invalid_error
call :message upgrade_pip
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 goto :pip_upgrade_error
call :message install_requirements
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 goto :requirements_error
call :message compile_sources
"%VENV_PY%" -m py_compile app.py browser.py asteroids.py models.py reports.py storage.py self_test.py
if errorlevel 1 goto :compile_error
call :message run_self_test
"%VENV_PY%" self_test.py
if errorlevel 1 goto :self_test_error
call :message install_success
if /i "%~1"=="--pause" pause
endlocal & exit /b 0

:venv_create_error
set "ERROR_KEY=venv_create_error"
goto :command_error
:venv_invalid_error
set "ERROR_KEY=venv_invalid_error"
goto :command_error
:pip_upgrade_error
set "ERROR_KEY=pip_upgrade_error"
goto :command_error
:requirements_error
set "ERROR_KEY=requirements_error"
goto :command_error
:compile_error
set "ERROR_KEY=compile_error"
goto :command_error
:self_test_error
set "ERROR_KEY=self_test_error"

:command_error
set "EXIT_CODE=%ERRORLEVEL%"
if "%EXIT_CODE%"=="0" set "EXIT_CODE=1"

:error
echo.
call :message %ERROR_KEY%
pause
endlocal & exit /b %EXIT_CODE%

:try_python
set "CANDIDATE_VERSION="
set "CANDIDATE_BITS="
for /f "tokens=1,2 delims=|" %%A in ('%* -c "import sys, struct; print(str(sys.version_info[0])+'.'+str(sys.version_info[1])+'|'+str(struct.calcsize('P')*8))" 2^>nul') do (
  set "CANDIDATE_VERSION=%%A"
  set "CANDIDATE_BITS=%%B"
)
if not defined CANDIDATE_VERSION exit /b 1
if not "%CANDIDATE_BITS%"=="64" exit /b 1
for /f "tokens=1,2 delims=." %%A in ("%CANDIDATE_VERSION%") do (
  set "CANDIDATE_MAJOR=%%A"
  set "CANDIDATE_MINOR=%%B"
)
if %CANDIDATE_MAJOR% LSS 3 exit /b 1
if %CANDIDATE_MAJOR% EQU 3 if %CANDIDATE_MINOR% LSS 10 exit /b 1
set "PYTHON_CMD=%*"
set "PYTHON_VERSION=%CANDIDATE_VERSION%"
exit /b 0

:message
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher_messages.ps1" "%~1"
exit /b %ERRORLEVEL%
