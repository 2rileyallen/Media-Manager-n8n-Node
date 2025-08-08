import sys
import os
import importlib.util
import json
import subprocess
import shutil

# --- Configuration ---
# Get the absolute path of the directory where this script is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SUBCOMMANDS_DIR = os.path.join(BASE_DIR, "subcommands")
SUBCOMMAND_ENVS_DIR = os.path.join(BASE_DIR, "subcommands_envs")
SUBCOMMAND_TOOLS_DIR = os.path.join(BASE_DIR, "subcommands_tools")

# --- Cross-Platform Helpers ---
def get_python_executable(env_path):
    """Returns the correct Python executable path for the given environment based on the OS."""
    if sys.platform == "win32":
        return os.path.join(env_path, "Scripts", "python.exe")
    else:
        # Assumes a POSIX-compliant system (Linux, macOS)
        return os.path.join(env_path, "bin", "python")

def get_pip_executable(env_path):
    """Returns the correct pip executable path for the given environment based on the OS."""
    if sys.platform == "win32":
        return os.path.join(env_path, "Scripts", "pip.exe")
    else:
        return os.path.join(env_path, "bin", "pip")

# --- Subcommand Discovery and Management ---
def discover_subcommands():
    """
    Discovers all valid Python subcommands in the SUBCOMMANDS_DIR.
    A valid subcommand is a .py file that does not start with an underscore.
    """
    subcommands = {}
    if not os.path.exists(SUBCOMMANDS_DIR):
        print(f"Warning: Subcommands directory not found at '{SUBCOMMANDS_DIR}'. Creating it.", file=sys.stderr)
        os.makedirs(SUBCOMMANDS_DIR)
        return subcommands

    for fname in os.listdir(SUBCOMMANDS_DIR):
        if fname.endswith(".py") and not fname.startswith("_"):
            name = fname[:-3]
            path = os.path.join(SUBCOMMANDS_DIR, fname)
            try:
                spec = importlib.util.spec_from_file_location(name, path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                
                # Metadata extraction
                subcommands[name] = {
                    "input_schema": getattr(mod, "INPUT_SCHEMA", []),
                    "requires": getattr(mod, "REQUIRES", [])
                }
            except Exception as e:
                print(f"Error loading subcommand '{name}': {e}", file=sys.stderr)
                subcommands[name] = {"error": f"Error loading: {e}"}
    
    return subcommands

def install_dependencies(env_path, packages):
    """
    Installs a list of packages into a specific virtual environment.
    For stability, it's recommended that packages are pinned (e.g., 'requests==2.28.1').
    """
    if not packages:
        return True
    
    print(f"Installing/verifying packages in '{env_path}'...", file=sys.stderr)
    pip_exe = get_pip_executable(env_path)
    
    try:
        # Using --upgrade ensures we get the specified version
        command = [pip_exe, "install", "--upgrade"] + list(packages)
        result = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8')
        print(f"  + Dependencies are up to date for '{os.path.basename(env_path)}'.", file=sys.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to install dependencies in '{env_path}'.", file=sys.stderr)
        print(e.stderr, file=sys.stderr)
        return False
    except FileNotFoundError:
        print(f"ERROR: pip executable not found at '{pip_exe}'. Is the environment corrupted?", file=sys.stderr)
        return False

def create_environment(env_path):
    """Creates a Python virtual environment at the specified path."""
    if os.path.exists(env_path):
        return True # Environment already exists
    
    print(f"Creating new virtual environment at '{env_path}'...", file=sys.stderr)
    try:
        # Use the same Python that is running this manager script
        subprocess.run([sys.executable, "-m", "venv", env_path], check=True, capture_output=True, text=True)
        print("  + Environment created successfully.", file=sys.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to create environment at '{env_path}'.", file=sys.stderr)
        print(e.stderr, file=sys.stderr)
        return False

def cleanup_orphaned_files(subcommand_names):
    """
    Removes environment and tool folders for subcommands that no longer exist.
    This is the core of the self-cleaning mechanism.
    """
    print("Checking for orphaned files and environments...", file=sys.stderr)
    cleaned_count = 0
    
    # Clean up orphaned environments
    if os.path.exists(SUBCOMMAND_ENVS_DIR):
        for folder_name in os.listdir(SUBCOMMAND_ENVS_DIR):
            if folder_name not in subcommand_names:
                folder_path = os.path.join(SUBCOMMAND_ENVS_DIR, folder_name)
                print(f"  - Cleaning up orphaned environment for '{folder_name}'...", file=sys.stderr)
                shutil.rmtree(folder_path, ignore_errors=True)
                cleaned_count += 1

    # Clean up orphaned tool folders
    if os.path.exists(SUBCOMMAND_TOOLS_DIR):
        for folder_name in os.listdir(SUBCOMMAND_TOOLS_DIR):
            if folder_name not in subcommand_names:
                folder_path = os.path.join(SUBCOMMAND_TOOLS_DIR, folder_name)
                print(f"  - Cleaning up orphaned tools folder for '{folder_name}'...", file=sys.stderr)
                shutil.rmtree(folder_path, ignore_errors=True)
                cleaned_count += 1

    if cleaned_count == 0:
        print("  + No orphaned files found. Everything is tidy!", file=sys.stderr)

def run_subcommand(name, input_data):
    """
    Prepares the environment for and executes a specific subcommand.
    This is the main entry point for running a tool from n8n or the CLI.
    """
    subcommands = discover_subcommands()
    if name not in subcommands or "error" in subcommands[name]:
        print(f"ERROR: Subcommand '{name}' not found or could not be loaded.", file=sys.stderr)
        return

    subcommand_metadata = subcommands[name]
    requires = subcommand_metadata.get("requires", [])
    
    # Determine the correct python executable to use
    if requires:
        # This subcommand needs its own isolated environment
        env_path = os.path.join(SUBCOMMAND_ENVS_DIR, name)
        if not create_environment(env_path) or not install_dependencies(env_path, requires):
            return # Stop if environment setup fails
        python_exe = get_python_executable(env_path)
    else:
        # No special requirements, use the same python as the manager
        python_exe = sys.executable

    # --- Tool Path Management ---
    # Provide a dedicated, persistent storage folder for the subcommand
    subcommand_tool_path = os.path.join(SUBCOMMAND_TOOLS_DIR, name)
    if not os.path.exists(subcommand_tool_path):
        os.makedirs(subcommand_tool_path)

    # Pass the tool path to the subcommand via an environment variable.
    execution_env = os.environ.copy()
    execution_env["SUBCOMMAND_TOOL_PATH"] = subcommand_tool_path
    
    # Prepare for execution
    subcommand_script_path = os.path.join(SUBCOMMANDS_DIR, f"{name}.py")
    
    print(f"\n--- Running Subcommand: {name} ---", file=sys.stderr)
    try:
        # FIX: Use Popen to correctly stream data to the subcommand via stdin
        process = subprocess.Popen(
            [python_exe, subcommand_script_path], # The command to run
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            env=execution_env
        )
        # Send the JSON data and get the output
        stdout, stderr = process.communicate(input=json.dumps(input_data))
        
        # For n8n, clean JSON output must go to stdout
        print(stdout)
        
        # Stderr can be used for logging/debugging information in n8n
        if stderr:
            print(stderr, file=sys.stderr)
            
    except FileNotFoundError:
        print(f"ERROR: Python executable not found at '{python_exe}'.", file=sys.stderr)

# --- Main CLI Logic ---
def main():
    """The main command-line interface router."""
    if len(sys.argv) < 2:
        print("Usage: python manager.py <command> [args...]", file=sys.stderr)
        print("Available commands: list, update, <subcommand_name>", file=sys.stderr)
        return

    command = sys.argv[1]

    if command == "list":
        subcommands = discover_subcommands()
        # IMPORTANT: Output raw JSON for machine parsing by the n8n node.
        print(json.dumps(subcommands))

    elif command == "update":
        print("\n--- Running Full System Update and Cleanup ---", file=sys.stderr)
        subcommands = discover_subcommands()
        cleanup_orphaned_files(subcommands.keys())
        # Also run installation for all subcommands
        for name, data in subcommands.items():
            if data.get("requires"):
                env_path = os.path.join(SUBCOMMAND_ENVS_DIR, name)
                if create_environment(env_path):
                    install_dependencies(env_path, data["requires"])
        print("\nUpdate and cleanup complete.", file=sys.stderr)

    else:
        # This branch handles running a specific subcommand
        subcommand_name = command
        input_data = {}

        # Read the JSON data from standard input (stdin)
        # This is more robust and avoids command line length limits.
        try:
            stdin_content = sys.stdin.read()
            if stdin_content:
                input_data = json.loads(stdin_content)
        except json.JSONDecodeError:
            print(f"ERROR: Could not decode JSON from standard input.", file=sys.stderr)
            return

        run_subcommand(subcommand_name, input_data)

if __name__ == "__main__":
    main()
