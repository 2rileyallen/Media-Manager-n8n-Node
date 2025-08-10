import sys
import os
import json
import tempfile
import subprocess

# --- Required Metadata ---

# 1. DEPENDENCIES: A list of pip-installable packages this subcommand needs.
# These will be installed in a dedicated virtual environment.
REQUIRES = [
    "chatterbox-tts==0.1.2",
    "torchaudio",
    "torch",
    "ffmpeg-python==0.2.0",
    "setuptools",
]

# 2. INPUT SCHEMA: Defines the UI fields for this subcommand in n8n.
# This single schema is used for both individual and batch processing.
INPUT_SCHEMA = [
    {
        "name": "text",
        "displayName": "Text",
        "type": "string",
        "required": True,
        "description": "The line of text to be spoken."
    },
    {
        "name": "speaker_audio_path",
        "displayName": "Speaker Reference Audio",
        "type": "string",
        "required": True,
        "description": "The absolute path to the speaker's reference audio file (e.g., C:\\voices\\speaker.wav)."
    },
    {
        "name": "output_file_path",
        "displayName": "Output File Path or Directory",
        "type": "string",
        "required": True,
        "description": "The absolute path for the output audio (e.g., C:\\output\\final.mp3). If a directory is provided, a default filename will be used."
    },
    {
        "name": "exaggeration",
        "displayName": "Exaggeration",
        "type": "number",
        "default": 0.5,
        "description": "Controls the expressiveness of the speech (0.0 to 1.0)."
    },
    {
        "name": "cfg_weight",
        "displayName": "CFG Weight",
        "type": "number",
        "default": 0.5,
        "description": "Classifier-Free Guidance weight. Higher values are more faithful to the prompt."
    },
    {
    "name": "_chatterbox_note",
    "displayName": "Note: In batch mode, the 'Output File Path' from the first item will be used for the final combined audio. If a directory is provided, a default filename will be used.",
    "type": "notice",
    "default": ""
    }
]


# --- Main Execution Logic ---

def main(input_data, tool_path):
    """
    Main function to handle TTS generation for single or batch items.
    """
    # Import heavy libraries here so the 'list' command in manager.py is fast
    import torchaudio as ta
    from chatterbox.tts import ChatterboxTTS
    import ffmpeg

    # Redirect print() to stderr for logging, so stdout is clean for n8n JSON output
    original_stdout = sys.stdout
    sys.stdout = sys.stderr

    temp_files_to_clean = []
    final_output_path = None

    try:
        # --- 1. Determine Mode and Prepare Script ---
        if "@items" in input_data:
            tts_script = input_data.get("@items", [])
            if not tts_script:
                raise ValueError("Batch mode selected, but no items were provided.")
            base_output_path = tts_script[0].get("output_file_path")
        elif "@item" in input_data:
            item_data = input_data.get("@item", {})
            tts_script = [item_data]
            base_output_path = item_data.get("output_file_path")
        else:
            raise ValueError("Invalid input format. Expected '@item' or '@items' key.")

        if not base_output_path:
            raise ValueError("The 'Output File Path or Directory' is required but was not found in the input data.")

        # --- 2. Resolve Final Output Path ---
        if os.path.isdir(base_output_path):
            print(f"Provided path '{base_output_path}' is a directory. Using default filename 'chatterbox_output.m4a'.")
            final_output_path = os.path.join(base_output_path, "chatterbox_output.m4a")
        else:
            final_output_path = base_output_path
        
        output_dir = os.path.dirname(final_output_path)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # --- 3. Pre-process Speaker Audios ---
        speakers_dict = {}
        speaker_temp_wavs = {}
        for item in tts_script:
            speaker_path = item.get("speaker_audio_path")
            if speaker_path and speaker_path not in speakers_dict:
                speakers_dict[speaker_path] = f"speaker_{len(speakers_dict)}"

        for path, speaker_id in speakers_dict.items():
            if not os.path.exists(path):
                raise FileNotFoundError(f"Reference audio for '{speaker_id}' not found at: {path}")

            tmp_input_wav_path = tempfile.mktemp(suffix=f"_{speaker_id}.wav", dir=tool_path)
            temp_files_to_clean.append(tmp_input_wav_path)
            # Use ffmpeg to convert any input audio to the required format for the model
            ffmpeg.input(path).output(tmp_input_wav_path, acodec='pcm_s16le', ar=24000).run(overwrite_output=True, quiet=True)
            speaker_temp_wavs[speaker_id] = tmp_input_wav_path

        # --- 4. Generate Audio for Each Script Line ---
        model = ChatterboxTTS.from_pretrained(device="cpu")
        generated_wav_segments = []
        
        path_root, path_ext = os.path.splitext(final_output_path)

        for i, item in enumerate(tts_script):
            text = item.get("text")
            speaker_path = item.get("speaker_audio_path")
            if not text or not speaker_path:
                print(f"Skipping item {i+1} due to missing text or speaker path.")
                continue

            speaker_id = speakers_dict[speaker_path]
            reference_wav_path = speaker_temp_wavs.get(speaker_id)
            if not reference_wav_path:
                raise ValueError(f"Could not find processed reference wav for speaker '{speaker_id}'.")

            print(f"Generating segment {i+1}/{len(tts_script)} for speaker '{speaker_id}': '{text[:50]}...'")
            wav = model.generate(
                text,
                audio_prompt_path=reference_wav_path,
                exaggeration=item.get("exaggeration", 0.5),
                cfg_weight=item.get("cfg_weight", 0.5),
                temperature=0.7
            )

            tmp_segment_path = f"{path_root}_temp_{i+1}.wav"
            temp_files_to_clean.append(tmp_segment_path)
            ta.save(tmp_segment_path, wav, model.sr)
            generated_wav_segments.append(tmp_segment_path)

        # --- 5. Combine Segments and Finalize ---
        if not generated_wav_segments:
            raise ValueError("No audio segments were generated. Check input data.")

        if len(generated_wav_segments) == 1:
            print("Only one segment generated. Converting directly to final format.")
            # Let ffmpeg infer the codec from the output file extension
            ffmpeg.input(generated_wav_segments[0]).output(final_output_path).run(overwrite_output=True, quiet=True)
        else:
            list_file_path = tempfile.mktemp(suffix=".txt", dir=tool_path)
            temp_files_to_clean.append(list_file_path)
            with open(list_file_path, "w", encoding='utf-8') as f:
                for wav_path in generated_wav_segments:
                    safe_path = wav_path.replace("\\", "/").replace("'", "'\\''")
                    f.write(f"file '{safe_path}'\n")

            print(f"Concatenating {len(generated_wav_segments)} segments into final file: {final_output_path}")
            # Let ffmpeg infer the codec from the output file extension
            ffmpeg.input(list_file_path, format='concat', safe=0).output(final_output_path).run(overwrite_output=True, quiet=True)

        # --- 6. Return Success Output ---
        sys.stdout = original_stdout
        result = {
            "status": "success",
            "message": f"Audio processing completed. {len(generated_wav_segments)} segment(s) processed.",
            "output_file": final_output_path
        }
        print(json.dumps(result, indent=4))

    except Exception as e:
        sys.stdout = original_stdout
        error_message = {"status": "error", "message": str(e)}
        print(json.dumps(error_message), file=sys.stderr)
        sys.exit(1)

    finally:
        # --- 7. Cleanup ---
        sys.stdout = original_stdout
        for file_path in temp_files_to_clean:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError as e:
                    print(f"Warning: Could not remove temp file '{file_path}': {e}", file=sys.stderr)


# --- Boilerplate for Direct Execution ---
if __name__ == "__main__":
    stdin_content = sys.stdin.read()
    if stdin_content:
        try:
            input_json = json.loads(stdin_content)
            subcommand_tool_path = os.environ.get("SUBCOMMAND_TOOL_PATH", tempfile.gettempdir())
            main(input_json, subcommand_tool_path)
        except json.JSONDecodeError:
            print(json.dumps({"status": "error", "message": "Invalid JSON input"}), file=sys.stderr)
            sys.exit(1)
    else:
        print(json.dumps({"status": "error", "message": "No JSON input provided"}), file=sys.stderr)
        sys.exit(1)
