@echo off
setlocal EnableExtensions
cd /d "%~dp0"

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo This folder is not a Git repository.
    pause
    exit /b 1
)

git add -A
git diff --cached --quiet
if not errorlevel 1 (
    echo There are no changes to upload.
    pause
    exit /b 0
)

set "COMMIT_MESSAGE=%~1"
if not defined COMMIT_MESSAGE set "COMMIT_MESSAGE=Update project"

git commit -m "%COMMIT_MESSAGE%"
if errorlevel 1 (
    echo Commit failed. Nothing was uploaded.
    pause
    exit /b 1
)

git pull --rebase origin main
if errorlevel 1 (
    echo Remote changes could not be combined automatically.
    echo If Git reported conflicts, resolve them and run the script again.
    pause
    exit /b 1
)

git push origin main
if errorlevel 1 (
    echo Upload failed. Check your Internet connection and GitHub access.
    pause
    exit /b 1
)

echo Project was uploaded successfully.
pause
