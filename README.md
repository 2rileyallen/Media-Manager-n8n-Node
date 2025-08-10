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

The New Standard: A Single INPUT_SCHEMA
CRITICAL: Every subcommand must define a single INPUT_SCHEMA list. This list is the single source of truth for the n8n user interface fields. The n8n node itself provides a "Processing Mode" dropdown that controls how the data is sent to your script (single item vs. batch of items). Your script's logic should handle both cases.

The Most Important Rule
CRITICAL: Do not import packages from the REQUIRES list at the top-level of your file. Instead, import them inside the functions that need them. This allows the manager to read your REQUIRES list before the import is attempted.

Subcommand Template
This is the required boilerplate for any new subcommand.

import sys
import os
import json

# --- Required Metadata ---

# 1. DEPENDENCIES
REQUIRES = ["ffmpeg-python==0.2.0"]

# 2. N8N UI SCHEMA
INPUT_SCHEMA = [
    {
        "name": "file_path",
        "displayName": "Media File Path",
        "type": "string",
        "required": True,
        "description": "The absolute path to the audio or video file."
    },
    # Add a helpful note to the UI using the 'notice' type.
    {
        "name": "_note",
        "displayName": "Note: This is an example notice that will appear in the n8n UI.",
        "type": "notice",
        "default": ""
    }
]

# --- Main Execution Logic ---
def main(input_data, tool_path):
    try:
        # The n8n node controls the delivery. Your script just checks what it received.
        if "@items" in input_data:
            # BATCH MODE: A list of items was received.
            script_items = input_data.get("@items", [])
            # ... logic to loop through script_items ...
        elif "@item" in input_data:
            # SINGLE MODE: A single item was received.
            script_items = [input_data.get("@item", {})]
            # ... logic to process the single item ...
        else:
            raise ValueError("Invalid input format. Expected '@item' or '@items' key.")
            
        # Example of accessing a parameter from the first item
        first_item_path = script_items[0].get("file_path") if script_items else None

        # ... your logic here ...

        result = {"status": "success", "processed_file": first_item_path}
        print(json.dumps(result, indent=4))

    except Exception as e:
        error_message = {"status": "error", "message": str(e)}
        print(json.dumps(error_message), file=sys.stderr)
        sys.exit(1)

# --- Boilerplate for Direct Execution ---
if __name__ == "__main__":
    stdin_content = sys.stdin.read()
    if stdin_content:
        try:
            data = json.loads(stdin_content)
            # The manager provides a dedicated folder for the tool to use
            tool_folder = os.environ.get("SUBCOMMAND_TOOL_PATH", "")
            main(data, tool_folder)
        except json.JSONDecodeError:
            print(json.dumps({"status": "error", "message": "Invalid JSON input"}), file=sys.stderr)
            sys.exit(1)
    else:
        print(json.dumps({"status": "error", "message": "No JSON input provided"}), file=sys.stderr)
        sys.exit(1)

5. AI Development Guide
Objective: Create a new Python script in the subcommands/ directory that fulfills a user's request.

Instructions:

Understand the Goal: Clarify the user's request. What is the input? What is the desired output?

Identify Dependencies: Determine which third-party Python libraries are needed. Find their latest stable versions on PyPI for version pinning (e.g., requests==2.28.1).

Define the UI: Create a single INPUT_SCHEMA list to generate the n8n UI fields. You can add a notice field at the end to provide helpful context to the user.

Write the Logic: Implement the core functionality within the main(input_data, tool_path) function.

Your script must be able to handle both single and batch processing.

Check for the @items key in input_data to handle a batch of items.

Check for the @item key to handle a single item.

Produce JSON Output: Ensure the only output to stdout is a single, clean JSON string representing the result.

Handle Errors: Use try...except blocks to catch potential errors. Print all error messages as JSON to stderr and exit with sys.exit(1).

Final Check: Ensure the script uses the correct boilerplate to read from sys.stdin, as shown in the template above.