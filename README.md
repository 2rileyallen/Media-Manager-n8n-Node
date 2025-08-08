Media Manager: An Extensible Framework for n8n
1. Project Overview
Media Manager is a self-managing, modular framework designed to run Python scripts as subcommands, primarily for use within a custom n8n node. It automates dependency and environment management, allowing developers and AI to rapidly create and deploy new tools without manual setup.

The core principle is modularity. By simply adding a new Python file to the subcommands/ directory, the framework automatically handles:

Isolated Environments: Creates a dedicated virtual environment for each subcommand with dependencies, preventing conflicts.

Automatic Dependency Installation: Reads a REQUIRES list in each subcommand and installs the specified packages.

Persistent Tool Storage: Provides a dedicated tools directory for each subcommand to store models, assets, or other large files.

Automated Cleanup: Removes orphaned environments and tool folders when a subcommand is deleted.

2. Project Structure
The entire project is organized to be self-contained and easy to understand.

media_manager/
├── venv/                   # Main virtual environment for the manager itself
├── subcommands/            # <<< All subcommand .py files go here.
│   └── example_tool.py
├── subcommands_envs/       # Auto-managed: Isolated Python environments.
│   └── example_tool/
├── subcommands_tools/      # Auto-managed: Persistent storage for tools.
│   └── example_tool/
├── manager.py              # The central orchestrator script. Do not modify.
├── setup.bat               # One-time setup script for Windows.
├── setup.sh                # One-time setup script for Linux/macOS.
└── README.md               # This documentation.

3. Development Workflow
Follow these steps to set up the project and develop new subcommands.

Step 1: Initial Environment Setup
This only needs to be done once to prepare the manager.py script's main environment.

On Windows:

setup.bat

On Linux/macOS:

chmod +x setup.sh
./setup.sh

Step 2: Activate the Environment
Before running any commands, you must activate the main virtual environment.

On Windows:

call venv\Scripts\activate

On Linux/macOS:

source venv/bin/activate

Step 3: Use the Manager CLI
The manager.py script is your primary interface for testing and development.

Command

Description

python manager.py list

Shows all available subcommands and their status.

python manager.py update

Scans for new subcommands, installs their dependencies, and cleans up any files left behind by deleted ones. Run this after adding or removing a subcommand.

python manager.py <name> '[JSON_STRING]'

Executes a subcommand. The input can be a JSON string, a path to a .json file, or a direct file path. If no input is needed, this argument can be omitted.

4. Subcommand Authoring Guide (The Contract)
To create a new tool, create a new .py file in the subcommands/ directory. This file must adhere to the following contract to be recognized and run by the manager.

The Most Important Rule
CRITICAL: Do not import packages from the REQUIRES list at the top of your file. Instead, import them inside the functions that need them. This allows the manager to read your REQUIRES list before the import is attempted.

Subcommand Template
This is the required boilerplate for every subcommand file. It demonstrates the correct import practice.

import sys
import os
import json

# --- Required Metadata ---

# 1. DEPENDENCIES: A list of Python packages required by this script.
#    The manager will install these into a dedicated environment.
#    For stability, ALWAYS pin versions (e.g., "pydub==0.25.1").
REQUIRES = [
    "pydub==0.25.1",
]

# 2. N8N UI SCHEMA: A list of dictionaries defining the UI for the n8n node.
#    This schema is read by n8n to dynamically generate input fields.
INPUT_SCHEMA = [
    {
        "name": "input_file",
        "displayName": "Input File Path",
        "type": "string",
        "required": True,
        "description": "The full path to the audio file to be processed."
    },
]

# --- Helper Functions ---

def some_helper_function(file_path):
    # CORRECT: Import the required module inside the function that uses it.
    from pydub import AudioSegment
    
    audio = AudioSegment.from_file(file_path)
    return len(audio)

# --- Main Execution Logic ---

def main(input_data, tool_path):
    """
    The primary function executed by the manager.

    Args:
        input_data (dict): A dictionary containing the user's input.
        tool_path (str): The absolute path to a dedicated folder for this tool.
    """
    try:
        # --- 1. Access Input Data ---
        input_file = input_data["input_file"]

        # --- 2. Your Logic Here ---
        # Example: Construct a path for an output file within the tool directory.
        output_file_path = os.path.join(tool_path, "processed_audio.mp3")
        
        length_in_ms = some_helper_function(input_file)

        # --- 3. Return Clean JSON Output ---
        # This JSON is captured by n8n as the node's output.
        # It MUST be the only thing printed to standard output (stdout).
        result = {
            "status": "success",
            "message": f"Successfully processed {input_file}.",
            "length_ms": length_in_ms,
        }
        print(json.dumps(result, indent=4))

    except Exception as e:
        # Catch any exceptions and report them clearly as JSON to stderr.
        error_message = {"status": "error", "message": str(e)}
        print(json.dumps(error_message), file=sys.stderr)

# --- Boilerplate for Direct Execution ---
# This allows the script to be run and receive input from the manager.
if __name__ == "__main__":
    if len(sys.argv) > 1:
        input_json = sys.argv[1]
        try:
            data = json.loads(input_json)
            tool_folder = os.environ.get("SUBCOMMAND_TOOL_PATH")
            if not tool_folder:
                raise RuntimeError("Tool path environment variable not set.")
            main(data, tool_folder)
        except json.JSONDecodeError:
            print(json.dumps({"status": "error", "message": "Invalid JSON input"}), file=sys.stderr)
    else:
        print(json.dumps({"status": "error", "message": "No JSON input provided"}), file=sys.stderr)


5. AI Development Guide
Objective: Create a new Python script in the subcommands/ directory that fulfills a user's request.

Instructions:

Understand the Goal: Clarify the user's request. What is the input? What is the desired output?

Identify Dependencies: Determine which third-party Python libraries are needed. Find their latest stable versions on PyPI for version pinning (e.g., requests==2.28.1).

Define the UI: Create the INPUT_SCHEMA list to define the necessary user inputs for the n8n interface.

Write the Logic: Implement the core functionality within the main(input_data, tool_path) function.

Use the input_data dictionary to get user parameters.

Use the tool_path variable for any file system operations (reading/writing models, assets, temporary files, etc.).

Produce JSON Output: Ensure the only output to stdout is a single, clean JSON string representing the result.

Handle Errors: Use try...except blocks to catch potential errors. Print all error messages as JSON to stderr.

Final Check: Review the full script to ensure it matches the template and fulfills all requirements.