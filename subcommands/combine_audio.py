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
            {"name": "Append (Default if not chosen)", "value": "append"},
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

def resolve_path(output_path):
    """Resolves a directory or file path into a final, absolute file path."""
    if os.path.isdir(output_path):
        unique_filename = generate_output_filename()
        resolved_path = os.path.join(output_path, unique_filename)
    else:
        resolved_path = output_path
    
    output_dir = os.path.dirname(resolved_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    return resolved_path

def apply_and_combine(items):
    """
    Applies transitions and effects, now with robust duration handling and improved output.
    """
    from pydub import AudioSegment

    if not items:
        raise ValueError("No items were provided to process.")

    # --- Single Item Logic ---
    if len(items) == 1:
        item = items[0]
        final_output_path = resolve_path(item.get("output_path"))
        audio = AudioSegment.from_file(item.get("file"))
        
        transition_type = item.get("transition_type", "append")
        duration_ms = int(item.get("transition_duration", 2.0) * 1000)

        print(f"Processing single item with effect: '{transition_type}'", file=sys.stderr)

        if duration_ms > len(audio):
            print(f"Warning: Duration ({duration_ms}ms) is longer than the audio clip ({len(audio)}ms). Capping duration.", file=sys.stderr)
            duration_ms = len(audio)

        if transition_type in ["fadein", "dual-fade"]:
            audio = audio.fade_in(duration_ms)
        if transition_type in ["fadeout", "dual-fade", "crossfade"]:
            audio = audio.fade_out(duration_ms)
        
        # UPDATED: Dynamically determine output format from file extension
        output_format = os.path.splitext(final_output_path)[1][1:]
        print(f"Exporting single processed file to: {final_output_path}", file=sys.stderr)
        audio.export(final_output_path, format=output_format)
        return {
            "status": "success",
            "message": "Single file processed successfully.",
            "output_file": final_output_path,
            "total_duration_seconds": round(len(audio) / 1000, 2),
            "processed_files_count": 1,
        }

    # --- Batch Processing Logic ---
    final_output_path = resolve_path(items[0].get("output_path"))

    first_item = items[0]
    combined_audio = AudioSegment.from_file(first_item.get("file"))
    first_transition_type = first_item.get("transition_type", "append")
    first_duration_ms = int(first_item.get("transition_duration", 2.0) * 1000)

    if first_transition_type in ["fadein", "dual-fade"]:
        safe_duration = min(first_duration_ms, len(combined_audio))
        print(f"Applying initial '{first_transition_type}' to {first_item.get('file')}", file=sys.stderr)
        combined_audio = combined_audio.fade_in(safe_duration)

    for i in range(1, len(items)):
        previous_item = items[i-1]
        current_item = items[i]
        
        transition_type = previous_item.get("transition_type", "append")
        duration_ms = int(previous_item.get("transition_duration", 2.0) * 1000)
        
        current_audio = AudioSegment.from_file(current_item.get("file"))

        safe_duration_ms = min(duration_ms, len(combined_audio), len(current_audio))
        if safe_duration_ms < duration_ms:
            print(f"Warning: Transition duration ({duration_ms}ms) is too long. Capping to {safe_duration_ms}ms.", file=sys.stderr)

        if transition_type in ["fadeout", "dual-fade"]:
            print(f"Applying fade out from '{transition_type}' on {previous_item.get('file')}", file=sys.stderr)
            combined_audio = combined_audio.fade_out(min(duration_ms, len(combined_audio)))
        
        current_transition_type = current_item.get("transition_type", "append")
        current_duration_ms = int(current_item.get("transition_duration", 2.0) * 1000)
        
        if current_transition_type in ["fadein", "dual-fade"]:
            print(f"Applying fade in from '{current_transition_type}' on {current_item.get('file')}", file=sys.stderr)
            current_audio = current_audio.fade_in(min(current_duration_ms, len(current_audio)))
            
        print(f"Applying transition '{transition_type}' from {previous_item.get('file')} to {current_item.get('file')}", file=sys.stderr)
        
        if transition_type == "crossfade":
            combined_audio = combined_audio.append(current_audio, crossfade=safe_duration_ms)
        elif transition_type == "overlap":
            combined_audio = combined_audio.overlay(current_audio, position=len(combined_audio) - safe_duration_ms)
        elif transition_type == "silence":
            combined_audio += AudioSegment.silent(duration=duration_ms) + current_audio
        else:
            combined_audio += current_audio

    last_item = items[-1]
    final_transition_type = last_item.get("transition_type", "append")
    final_duration_ms = int(last_item.get("transition_duration", 2.0) * 1000)
    safe_final_duration_ms = min(final_duration_ms, len(combined_audio))

    if final_transition_type in ["fadeout", "dual-fade", "crossfade"]:
        print(f"Applying final fade out from '{final_transition_type}' to {last_item.get('file')}", file=sys.stderr)
        combined_audio = combined_audio.fade_out(safe_final_duration_ms)
    elif final_transition_type == "silence":
        print(f"Applying final silence to {last_item.get('file')}", file=sys.stderr)
        combined_audio += AudioSegment.silent(duration=final_duration_ms)
        
    # UPDATED: Dynamically determine output format from file extension
    output_format = os.path.splitext(final_output_path)[1][1:]
    print(f"Exporting final combined audio to: {final_output_path}", file=sys.stderr)
    combined_audio.export(final_output_path, format=output_format)

    return {
        "status": "success",
        "message": f"{len(items)} tracks combined successfully.",
        "output_file": final_output_path,
        "total_duration_seconds": round(len(combined_audio) / 1000, 2),
        "processed_files_count": len(items),
    }

# --- Main Execution Logic ---

def main(input_data, tool_path):
    try:
        transition_map = {
            "Append (Default if not chosen)": "append",
            "Crossfade": "crossfade",
            "Dual-Fade": "dual-fade",
            "Fade In": "fadein",
            "Fade Out": "fadeout",
            "Overlap": "overlap",
            "Silence": "silence",
        }

        items_to_process = []
        if "@items" in input_data:
            items_to_process = input_data.get("@items", [])
        elif "@item" in input_data:
            items_to_process = [input_data.get("@item")]
        else:
            raise ValueError("Invalid input format. Expected '@item' or '@items' key.")
        
        if not items_to_process:
            raise ValueError("No items were provided to the subcommand.")

        for item in items_to_process:
            human_readable_type = item.get("transition_type", "Append (Default if not chosen)")
            item["transition_type"] = transition_map.get(human_readable_type, "append")

        result = apply_and_combine(items_to_process)
        
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
