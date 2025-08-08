#!/bin/bash
# setup.sh
# A simple, robust setup script for Linux/macOS to create the main virtual environment.

echo "================================="
echo "    Media Manager CLI Setup"
echo "================================="
echo

# --- Step 1: Check for Python ---
echo "[1/3] Checking for Python 3 installation..."
if ! command -v python3 &> /dev/null
then
    echo "ERROR: Python 3 could not be found. Please install it first."
    exit 1
fi
echo "  + Python 3 installation found."
echo

# --- Step 2: Create Virtual Environment ---
echo "[2/3] Setting up virtual environment in './venv/'..."
if [ ! -d "venv" ]; then
    echo "  + Creating virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create virtual environment."
        exit 1
    fi
    echo "  + Virtual environment created successfully."
else
    echo "  + Virtual environment 'venv' already exists. Skipping creation."
fi
echo

# --- Step 3: Install Core Dependencies ---
echo "[3/3] Installing/upgrading core packages..."
# Use the venv's python to run pip for reliability
./venv/bin/python3 -m pip install --upgrade pip &> /dev/null
if [ $? -ne 0 ]; then
    echo "WARNING: Failed to upgrade pip, but continuing setup."
else
    echo "  + Pip has been updated."
fi
echo "  + Core environment setup is complete."
echo

echo "================================="
echo "    Setup Complete! 🚀"
echo "================================="
echo
echo "Your Media Manager is ready to go!"
echo
echo "Next Steps:"
echo "  1. Activate the environment by running this command in your terminal:"
echo "     source venv/bin/activate"
echo
echo "  2. Then you can use the manager:"
echo "     python manager.py list"
echo "     python manager.py update"
echo
