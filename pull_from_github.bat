@echo off
setlocal EnableExtensions
cd /d "%~dp0"

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo This folder is not a Git repository.
    pause
    exit /b 1
)

for /f "delims=" %%A in ('git status --porcelain') do (
    echo Local changes were found. Upload or commit them before downloading updates.
    pause
    exit /b 1
)

git pull --ff-only origin main
if errorlevel 1 (
    echo Download failed. Your local copy may need manual conflict resolution.
    pause
    exit /b 1
)

echo Project was downloaded successfully.
pause
