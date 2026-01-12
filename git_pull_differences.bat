@echo off
REM Git Pull Only Different Files Script for Windows
REM This script fetches changes and pulls only files that are different from remote

echo ========================================
echo Git Pull Only Different Files
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
git status --porcelain
echo.

REM Fetch latest changes from remote
echo Fetching latest changes from remote...
git fetch origin
if errorlevel 1 (
    echo ERROR: Failed to fetch from remote
    pause
    exit /b 1
)
echo.

REM Get current branch
for /f "tokens=*" %%i in ('git branch --show-current') do set current_branch=%%i
echo Current branch: %current_branch%
echo.

REM Check if there are differences between local and remote
echo Checking for differences with remote...
git diff --name-only origin/%current_branch% > temp_diff_files.txt 2>nul
if errorlevel 1 (
    echo No remote branch found or no differences.
    echo.
    echo If remote is not configured, run:
    echo git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
    echo.
    del temp_diff_files.txt 2>nul
    pause
    exit /b 1
)

REM Count different files
for /f %%c in ('find /c /v "" ^< temp_diff_files.txt') do set file_count=%%c

if %file_count%==0 (
    echo No different files found between local and remote.
    echo Your repository is up to date.
    del temp_diff_files.txt
    echo.
    pause
    exit /b 0
)

echo Found %file_count% different files:
echo ----------------------------------
type temp_diff_files.txt
echo.

REM Ask user if they want to proceed
set /p proceed="Do you want to pull these different files? (Y/N): "
if /i not "%proceed%"=="Y" (
    echo Operation cancelled.
    del temp_diff_files.txt
    pause
    exit /b 0
)

echo.
echo Pulling only different files...

REM Backup current changes if any
git diff --quiet
if errorlevel 1 (
    echo.
    echo You have uncommitted changes. Creating backup...
    git stash push -m "Auto-backup before selective pull %date% %time%"
    set stashed_changes=1
    echo Changes backed up successfully!
    echo.
)

REM Pull only the different files
for /f "tokens=*" %%f in (temp_diff_files.txt) do (
    echo Pulling: %%f
    git checkout origin/%current_branch% -- %%f
    if errorlevel 1 (
        echo ERROR: Failed to pull %%f
    )
)

REM Clean up
del temp_diff_files.txt

echo.
echo ========================================
echo SUCCESS! Different files pulled from remote
echo ========================================
echo.

REM Show final status
echo Final status:
echo -------------
git status --porcelain
echo.

if defined stashed_changes (
    echo.
    echo NOTE: Your previous changes were backed up.
    echo To restore them, run: git stash pop
    echo To see backup: git stash list
    echo.
)

pause
