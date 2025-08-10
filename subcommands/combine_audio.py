import sys
import os
import json
import datetime

# --- Required Metadata ---

# 1. DEPENDENCIES
REQUIRES = [
    "pydub",
]

# 2. N8N UI SCHEMA
INPUT_SCHEMA = [
    {
        "name": "output_path",
        "displayName": "Output File Path or Directory",
        "type": "string",
        "required": True,
        "description": "The absolute path for the final combined audio file. If a directory is provided, a unique filename will be generated."
    },
    {
        "name": "tracks",
        "displayName": "Audio Tracks",
        "type": "collection",
        "required": True,
        "placeholder": "Add Track",
        "default": {},
        "description": "The list of audio files to combine in order.",
        "options": [
            {
                "name": "track_details",
                "displayName": "Track Details",
                "values": [
                    {
                        "name": "file",
                        "displayName": "Audio File Path",
                        "type": "string",
                        "required": True,
                        "default": "",
                        "description": "The absolute path to this audio file."
                    },
                    {
                        "name": "transition_type",
                        "displayName": "Transition to Next Track",
                        "type": "options",
                        "default": "append",
                        "options": [
                            {"name": "Append (Hard Cut)", "value": "append"},
                            {"name": "Crossfade", "value": "crossfade"},
                            {"name": "Overlap", "value": "overlap"},
                            {"name": "Silence", "value": "silence"},
                        ],
                        "description": "The transition from this track to the next one."
                    },
                    {
                        "name": "transition_duration",
                        "displayName": "Transition Duration (s)",
                        "type": "number",
                        "default": 2.0,
                        "description": "The duration of the transition in seconds."
                    }
                ]
            }
        ]
    }
]


# --- Helper Functions ---

def generate_output_filename():
    """Generate a unique filename for the output file"""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"combined_audio_{timestamp}.mp3"

def apply_transitions(tracks, output_path):
    """Apply the specified transitions between audio files"""
    # Import heavy libraries here to keep the 'list' command fast
    from pydub import AudioSegment

    if not tracks:
        raise ValueError("No tracks were provided to process.")

    # --- Path Resolution ---
    if os.path.isdir(output_path):
        unique_filename = generate_output_filename()
        final_output_path = os.path.join(output_path, unique_filename)
    else:
        final_output_path = output_path
    
    output_dir = os.path.dirname(final_output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # --- Audio Processing ---
    # Load the first track
    first_track_details = tracks[0].get("track_details", {})
    if not first_track_details.get("file"):
        raise ValueError("The first track is missing a file path.")
    
    print(f"Loading initial track: {first_track_details.get('file')}")
    combined_audio = AudioSegment.from_file(first_track_details.get("file"))

    # Loop through the rest of the tracks to apply transitions
    for i in range(len(tracks) - 1):
        # Details from the current track determine the transition to the next
        current_track_details = tracks[i].get("track_details", {})
        next_track_details = tracks[i+1].get("track_details", {})

        current_file = current_track_details.get("file")
        next_file = next_track_details.get("file")
        if not next_file:
            print(f"Warning: Skipping transition from '{current_file}' as the next track has no file path.")
            continue

        transition_type = current_track_details.get("transition_type", "append")
        duration_ms = int(current_track_details.get("transition_duration", 2.0) * 1000)
        
        print(f"Applying '{transition_type}' of {duration_ms}ms from '{current_file}' to '{next_file}'")
        
        next_audio = AudioSegment.from_file(next_file)

        if transition_type == "crossfade":
            combined_audio = combined_audio.append(next_audio, crossfade=duration_ms)
        elif transition_type == "overlap":
            combined_audio = combined_audio.overlay(next_audio, position=len(combined_audio) - duration_ms)
        elif transition_type == "silence":
            silence_segment = AudioSegment.silent(duration=duration_ms)
            combined_audio += silence_segment + next_audio
        else: # Default to 'append'
            combined_audio += next_audio
            
    # Export the final combined audio
    print(f"Exporting final audio to: {final_output_path}")
    combined_audio.export(final_output_path, format="mp3")

    return {
        "status": "success",
        "output_file": final_output_path,
        "processed_files_count": len(tracks),
    }

# --- Main Execution Logic ---

def main(input_data, tool_path):
    try:
        # This subcommand only makes sense in batch mode, but we'll handle both cases.
        # It expects a specific structure from the n8n 'collection' type.
        if "@items" in input_data:
            # In batch mode, we only care about the parameters from the first item.
            item_data = input_data.get("@items")[0]
        elif "@item" in input_data:
            item_data = input_data.get("@item")
        else:
            raise ValueError("Invalid input format. Expected '@item' or '@items' key.")
        
        output_path = item_data.get("output_path")
        tracks = item_data.get("tracks", {}).get("track_details", [])

        if not output_path:
            raise ValueError("'Output File Path or Directory' is a required parameter.")
        if not tracks:
            raise ValueError("No tracks were provided in the 'Audio Tracks' collection.")

        result = apply_transitions(tracks, output_path)
        
        # Print the clean JSON result to stdout for n8n
        print(json.dumps(result, indent=2))

    except Exception as e:
        # Print any errors as JSON to stderr
        error_message = {"status": "error", "message": str(e)}
        print(json.dumps(error_message, indent=2), file=sys.stderr)
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
