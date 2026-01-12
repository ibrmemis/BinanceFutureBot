@echo off
REM Git Push Script for Windows
REM This script adds all changes, commits with a message, and pushes to GitHub

echo ========================================
echo Git Push Script
echo ========================================
echo.

REM Check if git is installed
git --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Git is not installed or not in PATH
    echo Please install Git from https://git-scm.com/
    pause
    exit /b 1
)

REM Check if we're in a git repository
git rev-parse --git-dir >nul 2>&1
if errorlevel 1 (
    echo ERROR: Not a git repository
    echo Please run 'git init' first
    pause
    exit /b 1
)

REM Show current status
echo Current Git Status:
echo -------------------
git status
echo.

REM Add all changes
echo Adding all changes...
git add .
if errorlevel 1 (
    echo ERROR: Failed to add changes
    pause
    exit /b 1
)
echo Changes added successfully!
echo.

REM Get commit message from user
set /p commit_msg="Enter commit message (or press Enter for default): "
if "%commit_msg%"=="" (
    set commit_msg=Update: %date% %time%
)

REM Commit changes
echo Committing changes...
git commit -m "%commit_msg%"
if errorlevel 1 (
    echo WARNING: Nothing to commit or commit failed
    echo.
)

REM Get current branch
for /f "tokens=*" %%i in ('git branch --show-current') do set current_branch=%%i
echo Current branch: %current_branch%
echo.

REM Push to remote
echo Pushing to GitHub...
git push origin %current_branch%
if errorlevel 1 (
    echo.
    echo ERROR: Push failed!
    echo.
    echo Possible reasons:
    echo 1. Remote repository not configured
    echo 2. Authentication failed
    echo 3. Network connection issue
    echo.
    echo To configure remote, run:
    echo git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo SUCCESS! Changes pushed to GitHub
echo ========================================
echo.
pause
