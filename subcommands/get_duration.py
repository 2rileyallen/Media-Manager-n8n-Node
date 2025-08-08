import sys
import os
import json
# The ffmpeg import is now moved inside the function that uses it.

# --- Required Metadata ---

# 1. DEPENDENCIES: A list of Python packages required by this script.
#    The manager will install these into a dedicated environment.
#    For stability, ALWAYS pin versions (e.g., "ffmpeg-python==0.2.0").
REQUIRES = [
    "ffmpeg-python==0.2.0"
]

# 2. N8N UI SCHEMA: A list of dictionaries defining the UI for the n8n node.
#    This schema is read by n8n to dynamically generate input fields.
INPUT_SCHEMA = [
    {
        "name": "file_path",
        "displayName": "Media File Path",
        "type": "string",
        "required": True,
        "description": "The absolute path to the audio or video file."
    },
    {
        "name": "format",
        "displayName": "Output Format",
        "type": "options",
        "options": [
            { "name": "Seconds", "value": "seconds" },
            { "name": "Minutes", "value": "minutes" },
            { "name": "Hours", "value": "hours" }
        ],
        "default": "seconds",
        "description": "The desired format for the output duration."
    }
]

# --- Helper Functions ---

def format_duration(seconds, format_type="seconds"):
    """Format duration based on the specified format type."""
    if format_type == "seconds":
        return f"{seconds:.2f}"
    
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if format_type == "hours":
        return f"{int(hours)}h {int(minutes)}m {seconds:.2f}s"
    elif format_type == "minutes":
        total_minutes = hours * 60 + minutes
        return f"{int(total_minutes)}m {seconds:.2f}s"
    else:
        return f"{seconds:.2f}"  # Default to seconds

def get_file_duration(file_path):
    """Get duration of a media file using ffmpeg."""
    # FIX: Import the required module inside the function.
    # This allows the manager to load the file for metadata inspection
    # without failing on the import.
    import ffmpeg

    try:
        probe = ffmpeg.probe(file_path)
        duration = float(probe["format"]["duration"])
        return duration
    except ffmpeg.Error as e:
        # ffmpeg-python often prints detailed errors to stderr
        error_details = e.stderr.decode('utf8').strip()
        raise RuntimeError(f"ffmpeg error: {error_details}")
    except Exception as e:
        raise RuntimeError(f"An unexpected error occurred: {str(e)}")


# --- Main Execution Logic ---

def main(input_data, tool_path):
    """
    The primary function executed by the manager.

    Args:
        input_data (dict): A dictionary containing the user's input,
                           matching the structure defined in INPUT_SCHEMA.
        tool_path (str): The absolute path to a dedicated, persistent
                         folder for this subcommand. (Not used in this script).
    """
    try:
        # --- 1. Access Input Data ---
        file_path = input_data["file_path"]
        format_type = input_data.get("format", "seconds")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"The specified file was not found at '{file_path}'")

        # --- 2. Your Logic Here ---
        duration_seconds = get_file_duration(file_path)
        
        # --- 3. Return Clean JSON Output ---
        # This JSON is captured by n8n as the node's output.
        result = {
            "status": "success",
            "file": file_path,
            "duration_seconds": duration_seconds,
            "duration_formatted": format_duration(duration_seconds, format_type)
        }
        print(json.dumps(result, indent=4))

    except KeyError as e:
        # If a required key is missing, provide a clear error.
        error_message = {"status": "error", "message": f"Missing required parameter: {e}"}
        print(json.dumps(error_message), file=sys.stderr)
    except Exception as e:
        # Catch any other exceptions and report them clearly.
        error_message = {"status": "error", "message": str(e)}
        print(json.dumps(error_message), file=sys.stderr)


# --- Boilerplate for Direct Execution ---
# This allows the script to be run and receive input from the manager.
if __name__ == "__main__":
    if len(sys.argv) > 1:
        input_json = sys.argv[1]
        try:
            data = json.loads(input_json)
            # The manager provides the tool path via an environment variable.
            tool_folder = os.environ.get("SUBCOMMAND_TOOL_PATH", "")
            main(data, tool_folder)
        except json.JSONDecodeError:
            print(json.dumps({"status": "error", "message": "Invalid JSON input"}), file=sys.stderr)
    else:
        # Handle case where no input is provided, if necessary.
        print(json.dumps({"status": "error", "message": "No JSON input provided"}), file=sys.stderr)
