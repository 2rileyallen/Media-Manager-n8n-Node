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
# This schema now includes all original transition types.
INPUT_SCHEMA = [
    {
        "name": "file",
        "displayName": "Audio File Path",
        "type": "string",
        "required": True,
        "default": "",
        "description": "The absolute path to this audio file segment."
    },
    {
        "name": "output_path",
        "displayName": "Final Output Path or Directory",
        "type": "string",
        "required": True,
        "description": "In batch mode, the path from the FIRST item is used for the final combined file."
    },
    {
        "name": "transition_type",
        "displayName": "Transition/Effect Type",
        "type": "options",
        "default": "append",
        "options": [
            {"name": "Append (Hard Cut)", "value": "append"},
            {"name": "Crossfade", "value": "crossfade"},
            {"name": "Dual-Fade", "value": "dual-fade"},
            {"name": "Fade In", "value": "fadein"},
            {"name": "Fade Out", "value": "fadeout"},
            {"name": "Overlap", "value": "overlap"},
            {"name": "Silence", "value": "silence"},
        ],
        "description": "The effect to apply to this track or the transition to the next."
    },
    {
        "name": "transition_duration",
        "displayName": "Transition/Effect Duration (s)",
        "type": "number",
        "default": 2.0,
        "description": "The duration of the transition or effect in seconds."
    }
]


# --- Helper Functions ---

def generate_output_filename():
    """Generate a unique filename for the output file"""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"combined_audio_{timestamp}.mp3"

def apply_and_combine(items, final_output_path):
    """
    Apply transitions and effects based on the original, more complex logic.
    """
    from pydub import AudioSegment

    if not items:
        raise ValueError("No items were provided to process.")

    # --- Path Resolution ---
    if os.path.isdir(final_output_path):
        unique_filename = generate_output_filename()
        resolved_path = os.path.join(final_output_path, unique_filename)
    else:
        resolved_path = final_output_path
    
    output_dir = os.path.dirname(resolved_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # --- Audio Processing ---
    # 1. Load the first audio track
    first_item = items[0]
    first_audio = AudioSegment.from_file(first_item.get("file"))
    first_transition_type = first_item.get("transition_type", "append")
    first_duration_ms = int(first_item.get("transition_duration", 2.0) * 1000)

    # Apply effects to the beginning of the first track
    if first_transition_type in ["fadein", "dual-fade"]:
        print(f"Applying initial '{first_transition_type}' to {first_item.get('file')}")
        first_audio = first_audio.fade_in(first_duration_ms)
    
    combined_audio = first_audio

    # 2. Loop through the remaining tracks to apply transitions
    for i in range(1, len(items)):
        previous_item = items[i-1]
        current_item = items[i]
        
        # The transition is defined by the *previous* item
        transition_type = previous_item.get("transition_type", "append")
        duration_ms = int(previous_item.get("transition_duration", 2.0) * 1000)

        # Apply effects to the end of the combined audio so far
        if transition_type in ["fadeout", "dual-fade"]:
            print(f"Applying fade out from '{transition_type}' on {previous_item.get('file')}")
            combined_audio = combined_audio.fade_out(duration_ms)
        
        # Load the current audio track
        current_audio = AudioSegment.from_file(current_item.get("file"))
        
        # Apply effects to the beginning of the current track
        current_transition_type = current_item.get("transition_type", "append")
        current_duration_ms = int(current_item.get("transition_duration", 2.0) * 1000)
        
        if current_transition_type in ["fadein", "dual-fade"]:
            print(f"Applying fade in from '{current_transition_type}' on {current_item.get('file')}")
            current_audio = current_audio.fade_in(current_duration_ms)
            
        print(f"Applying transition '{transition_type}' from {previous_item.get('file')} to {current_item.get('file')}")
        
        # Apply the two-track transitions
        if transition_type == "crossfade":
            combined_audio = combined_audio.append(current_audio, crossfade=duration_ms)
        elif transition_type == "overlap":
            combined_audio = combined_audio.overlay(current_audio, position=len(combined_audio) - duration_ms)
        elif transition_type == "silence":
            silence_segment = AudioSegment.silent(duration=duration_ms)
            combined_audio += silence_segment + current_audio
        else: # append, fadein, fadeout, dual-fade all result in simple concatenation at this stage
            combined_audio += current_audio

    # 3. Handle the final effect on the very last track
    last_item = items[-1]
    final_transition_type = last_item.get("transition_type", "append")
    final_duration_ms = int(last_item.get("transition_duration", 2.0) * 1000)

    if final_transition_type in ["fadeout", "dual-fade"]:
        print(f"Applying final '{final_transition_type}' to {last_item.get('file')}")
        combined_audio = combined_audio.fade_out(final_duration_ms)
    elif final_transition_type == "crossfade": # A crossfade on the last item is just a fadeout
        print(f"Applying final fadeout (from crossfade) to {last_item.get('file')}")
        combined_audio = combined_audio.fade_out(final_duration_ms)
    elif final_transition_type == "silence":
        print(f"Applying final silence to {last_item.get('file')}")
        silence_segment = AudioSegment.silent(duration=final_duration_ms)
        combined_audio += silence_segment
        
    # Export the final combined audio
    print(f"Exporting final audio to: {resolved_path}")
    combined_audio.export(resolved_path, format="mp3")

    return {
        "status": "success",
        "message": f"{len(items)} tracks combined successfully.",
        "output_file": resolved_path,
        "processed_files_count": len(items),
    }

# --- Main Execution Logic ---

def main(input_data, tool_path):
    try:
        items_to_process = []
        if "@items" in input_data:
            items_to_process = input_data.get("@items", [])
        elif "@item" in input_data:
            items_to_process = [input_data.get("@item")]
        else:
            raise ValueError("Invalid input format. Expected '@item' or '@items' key.")
        
        if not items_to_process:
            raise ValueError("No items were provided to the subcommand.")

        final_output_path = items_to_process[0].get("output_path")
        if not final_output_path:
            raise ValueError("'Final Output Path or Directory' is a required parameter and was missing from the first item.")

        result = apply_and_combine(items_to_process, final_output_path)
        
        print(json.dumps(result, indent=2))

    except Exception as e:
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
