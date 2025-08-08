@echo off
REM setup.bat
REM A simple, robust setup script for Windows to create the main virtual environment.

setlocal

echo =================================
echo     Media Manager CLI Setup
echo =================================
echo.

REM Set working directory to where this script is located
cd /d "%~dp0"

REM --- Step 1: Check for Python ---
echo [1/3] Checking for Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not found in your system's PATH.
    echo Please install Python 3.7 or newer and ensure it's added to your PATH.
    goto :end
)
echo   + Python installation found.
echo.

REM --- Step 2: Create Virtual Environment ---
echo [2/3] Setting up virtual environment in '.\venv\'...
if exist venv (
    echo   + Virtual environment 'venv' already exists. Skipping creation.
) else (
    echo   + Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create the virtual environment.
        goto :end
    )
    echo   + Virtual environment created successfully.
)
echo.

REM --- Step 3: Install Core Dependencies ---
echo [3/3] Installing/upgrading core packages...
if not exist "venv\Scripts\python.exe" (
    echo ERROR: Could not find the Python executable in the virtual environment.
    goto :end
)

REM Use the venv's python to run pip, which is the most reliable method
call venv\Scripts\python.exe -m pip install --upgrade pip
if %errorlevel% neq 0 (
    echo WARNING: Failed to upgrade pip, but continuing setup.
) else (
    echo   + Pip has been updated.
)
echo   + Core environment setup is complete.
echo.

echo =================================
echo     Setup Complete! 🚀
echo =================================
echo.
echo Your Media Manager is ready to go!
echo.
echo Next Steps:
echo   1. Activate the environment by running this command in your terminal:
echo      call venv\Scripts\activate
echo.
echo   2. Then you can use the manager:
echo      python manager.py list
echo      python manager.py update
echo.

:end
endlocal
pause
