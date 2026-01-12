#!/bin/bash

# Git Pull Only Different Files Script for Linux/Mac
# This script fetches changes and pulls only files that are different from remote

echo "========================================"
echo "Git Pull Only Different Files"
echo "========================================"
echo

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo "ERROR: Git is not installed"
    echo "Please install Git first"
    exit 1
fi

# Check if we're in a git repository
if ! git rev-parse --git-dir &> /dev/null; then
    echo "ERROR: Not a git repository"
    echo "Please run 'git init' first"
    exit 1
fi

# Show current status
echo "Current Git Status:"
echo "-------------------"
git status --porcelain
echo

# Fetch latest changes from remote
echo "Fetching latest changes from remote..."
if ! git fetch origin; then
    echo "ERROR: Failed to fetch from remote"
    exit 1
fi
echo

# Get current branch
current_branch=$(git branch --show-current)
echo "Current branch: $current_branch"
echo

# Check if there are differences between local and remote
echo "Checking for differences with remote..."
git diff --name-only origin/$current_branch > temp_diff_files.txt 2>/dev/null

if [ $? -ne 0 ]; then
    echo "No remote branch found or no differences."
    echo
    echo "If remote is not configured, run:"
    echo "git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git"
    echo
    rm -f temp_diff_files.txt
    exit 1
fi

# Count different files
file_count=$(wc -l < temp_diff_files.txt)

if [ $file_count -eq 0 ]; then
    echo "No different files found between local and remote."
    echo "Your repository is up to date."
    rm -f temp_diff_files.txt
    echo
    exit 0
fi

echo "Found $file_count different files:"
echo "----------------------------------"
cat temp_diff_files.txt
echo

# Ask user if they want to proceed
read -p "Do you want to pull these different files? (Y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Operation cancelled."
    rm -f temp_diff_files.txt
    exit 0
fi

echo
echo "Pulling only different files..."

# Backup current changes if any
if ! git diff --quiet; then
    echo
    echo "You have uncommitted changes. Creating backup..."
    git stash push -m "Auto-backup before selective pull $(date)"
    stashed_changes=1
    echo "Changes backed up successfully!"
    echo
fi

# Pull only the different files
while IFS= read -r file; do
    echo "Pulling: $file"
    if ! git checkout origin/$current_branch -- "$file"; then
        echo "ERROR: Failed to pull $file"
    fi
done < temp_diff_files.txt

# Clean up
rm -f temp_diff_files.txt

echo
echo "========================================"
echo "SUCCESS! Different files pulled from remote"
echo "========================================"
echo

# Show final status
echo "Final status:"
echo "-------------"
git status --porcelain
echo

if [ "$stashed_changes" = "1" ]; then
    echo
    echo "NOTE: Your previous changes were backed up."
    echo "To restore them, run: git stash pop"
    echo "To see backup: git stash list"
    echo
fi