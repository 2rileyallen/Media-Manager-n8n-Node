Media Manager: An Extensible Framework for n8n
1. Project Overview
Media Manager is a self-managing, modular framework designed to run Python scripts as subcommands, primarily for use within a custom n8n node. It automates dependency and environment management, allowing developers and AI to rapidly create and deploy new tools without manual setup.

The core principle is modularity. By simply adding a new Python file to the subcommands/ directory, the framework automatically handles:

Isolated Environments: Creates a dedicated virtual environment for each subcommand, preventing dependency conflicts.

Automatic Dependency Installation: Reads a REQUIRES list in each subcommand and installs the specified packages.

Persistent Tool Storage: Provides a dedicated tools directory for each subcommand to store models, assets, or other large files.

Automated Cleanup: Removes orphaned environments and tool folders when a subcommand is deleted.

2. Project Structure
The entire project is organized to be self-contained and easy to understand.

Media-Manager-n8n-Node/
├── venv/                 # Main virtual environment for the manager itself
├── subcommands/          # <<< All subcommand .py files go here.
│   └── example_tool.py
├── subcommands_envs/     # Auto-managed: Isolated Python environments.
│   └── example_tool/
├── subcommands_tools/    # Auto-managed: Persistent storage for tools.
│   └── example_tool/
├── manager.py            # The central orchestrator script. Do not modify.
├── setup.bat             # One-time setup script for Windows.
└── README.md             # This documentation.

3. Development Workflow
Follow these steps to set up the project and develop new subcommands.

Step 1: Initial Environment Setup
This only needs to be done once to prepare the manager.py script's main environment.

On Windows: setup.bat

On Linux/macOS: chmod +x setup.sh && ./setup.sh

Step 2: Use the Manager CLI
The manager.py script is your primary interface for testing and development. You must first activate the main virtual environment.

On Windows: call venv\Scripts\activate

On Linux/macOS: source venv/bin/activate

Command

Description

python manager.py list

Shows all available subcommands and their status.

python manager.py update

Scans for new subcommands, installs their dependencies, and cleans up old files.

echo '{"json":"data"}' | python manager.py <name>

Executes a subcommand by piping JSON data to it. This is the recommended testing method.

4. Subcommand Authoring Guide (The Contract)
To create a new tool, create a new .py file in the subcommands/ directory. This file must adhere to the following contract to be recognized and run by the manager.

The Most Important Rule
CRITICAL: Do not import packages from the REQUIRES list at the top-level of your file. Instead, import them inside the functions that need them. This allows the manager to read your REQUIRES list before the import is attempted.

Subcommand Template
This is the required boilerplate for every subcommand file.

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
    {
        "name": "format",
        "displayName": "Output Format",
        "type": "options",
        "options": [
            { "name": "Seconds", "value": "seconds" },
            { "name": "Minutes", "value": "minutes" }
        ],
        "default": "seconds",
        "description": "The desired format for the output duration."
    }
]

# --- Helper Functions (Optional) ---

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
    # CORRECT: Read from standard input (stdin) instead of command-line arguments.
    stdin_content = sys.stdin.read()
    
    if stdin_content:
        try:
            data = json.loads(stdin_content)
            # The manager provides the tool path via an environment variable.
            tool_folder = os.environ.get("SUBCOMMAND_TOOL_PATH", "")
            main(data, tool_folder)
        except json.JSONDecodeError:
            print(json.dumps({"status": "error", "message": "Invalid JSON input from stdin"}), file=sys.stderr)
    else:
        # Handle case where no input is provided.
        print(json.dumps({"status": "error", "message": "No JSON input provided to stdin"}), file=sys.stderr)


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

Final Check: Ensure the script uses the correct boilerplate to read from sys.stdin, as shown in the template above.