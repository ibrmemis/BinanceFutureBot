@echo off
REM Git Pull Script for Windows
REM This script pulls the latest changes from GitHub

echo ========================================
echo Git Pull Script
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

REM Check for uncommitted changes
git diff-index --quiet HEAD --
if errorlevel 1 (
    echo WARNING: You have uncommitted changes!
    echo.
    set /p continue="Do you want to stash changes and continue? (Y/N): "
    if /i "%continue%"=="Y" (
        echo Stashing changes...
        git stash
        if errorlevel 1 (
            echo ERROR: Failed to stash changes
            pause
            exit /b 1
        )
        echo Changes stashed successfully!
        echo.
    ) else (
        echo Pull cancelled. Please commit or stash your changes first.
        pause
        exit /b 1
    )
)

REM Get current branch
for /f "tokens=*" %%i in ('git branch --show-current') do set current_branch=%%i
echo Current branch: %current_branch%
echo.

REM Fetch latest changes
echo Fetching latest changes from remote...
git fetch origin
if errorlevel 1 (
    echo ERROR: Failed to fetch from remote
    pause
    exit /b 1
)
echo.

REM Pull changes
echo Pulling changes from GitHub...
git pull origin %current_branch%
if errorlevel 1 (
    echo.
    echo ERROR: Pull failed!
    echo.
    echo Possible reasons:
    echo 1. Remote repository not configured
    echo 2. Authentication failed
    echo 3. Network connection issue
    echo 4. Merge conflicts
    echo.
    echo To configure remote, run:
    echo git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo SUCCESS! Latest changes pulled from GitHub
echo ========================================
echo.

REM Check if there were stashed changes
git stash list | findstr "stash@{0}" >nul 2>&1
if not errorlevel 1 (
    echo.
    echo You have stashed changes. To apply them, run:
    echo git stash pop
    echo.
)

pause
