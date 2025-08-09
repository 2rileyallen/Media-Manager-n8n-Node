import sys
import os
import json

# --- Required Metadata ---

# 1. DEPENDENCIES
REQUIRES = [
    "ffmpeg-python==0.2.0",
]

# 2. N8N UI SCHEMA
# All subcommands now use a MODES dictionary. For simple tools,
# it contains just one mode.
MODES = {
    "default": {
        "displayName": "Default",
        "input_schema": [
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
    }
}

# --- Helper Functions ---

def format_duration(seconds, format_type="seconds"):
    if format_type == "seconds": return f"{seconds:.2f}"
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if format_type == "hours": return f"{int(hours)}h {int(minutes)}m {seconds:.2f}s"
    total_minutes = hours * 60 + minutes
    return f"{int(total_minutes)}m {seconds:.2f}s"

def get_file_duration(file_path):
    import ffmpeg
    try:
        probe = ffmpeg.probe(file_path)
        return float(probe["format"]["duration"])
    except ffmpeg.Error as e:
        raise RuntimeError(f"ffmpeg error: {e.stderr.decode('utf8').strip()}")
    except Exception as e:
        raise RuntimeError(f"An unexpected error occurred: {str(e)}")

# --- Main Execution Logic ---

def main(input_data, tool_path):
    try:
        # For single-mode tools, the parameters are nested under the '@item' key.
        item_data = input_data.get("@item", {})
        file_path = item_data.get("file_path")
        format_type = item_data.get("format", "seconds")

        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at '{file_path}'")

        duration_seconds = get_file_duration(file_path)
        
        result = {
            "status": "success",
            "file": file_path,
            "duration_seconds": duration_seconds,
            "duration_formatted": format_duration(duration_seconds, format_type)
        }
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
            tool_folder = os.environ.get("SUBCOMMAND_TOOL_PATH", "")
            main(data, tool_folder)
        except json.JSONDecodeError:
            print(json.dumps({"status": "error", "message": "Invalid JSON input"}), file=sys.stderr)
            sys.exit(1)
    else:
        print(json.dumps({"status": "error", "message": "No JSON input provided"}), file=sys.stderr)
        sys.exit(1)
