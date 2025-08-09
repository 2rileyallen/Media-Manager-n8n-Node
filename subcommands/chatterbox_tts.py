import sys
import os
import json
import tempfile
import subprocess

# --- Required Metadata ---

# 1. DEPENDENCIES
REQUIRES = [
    "chatterbox-tts==0.1.2",
    "torchaudio",
    "torch",
    "ffmpeg-python==0.2.0",
    "setuptools",
]

# 2. N8N UI SCHEMA - NOW WITH MODES
MODES = {
    "single": {
        "displayName": "Process Each Item Individually",
        "input_schema": [
            {
                "name": "text",
                "displayName": "Text",
                "type": "string",
                "required": True,
                "description": "The single line of text to be spoken."
            },
            {
                "name": "speaker_audio_path",
                "displayName": "Speaker Reference Audio",
                "type": "string",
                "required": True,
                "description": "The absolute path to the speaker's reference audio file."
            },
            {
                "name": "output_file_path",
                "displayName": "Output File Path",
                "type": "string",
                "required": True,
                "description": "The absolute path for the final output audio file (e.g., C:\\temp\\output.m4a)."
            },
            {
                "name": "exaggeration",
                "displayName": "Exaggeration",
                "type": "number",
                "default": 0.5,
                "description": "Controls the expressiveness of the speech."
            },
            {
                "name": "cfg_weight",
                "displayName": "CFG Weight",
                "type": "number",
                "default": 0.5,
                "description": "Classifier-Free Guidance weight."
            }
        ]
    },
    "batch": {
        "displayName": "Array: Process All Items Together",
        "input_schema": [
            {
                "name": "speakers",
                "displayName": "Speakers Dictionary",
                "type": "json",
                "required": True,
                "default": '{\n  "speaker_1": "path/to/voice.wav"\n}',
                "description": "A JSON object mapping speaker IDs to their reference audio file paths."
            },
            {
                "name": "output_file_path",
                "displayName": "Final Output File Path",
                "type": "string",
                "required": True,
                "description": "The absolute path for the final combined audio file."
            }
        ]
    }
}


# --- Main Execution Logic ---

def main(input_data, tool_path):
    import torchaudio as ta
    from chatterbox.tts import ChatterboxTTS
    import ffmpeg

    temp_files_to_clean = []
    generated_output_files = []

    try:
        # --- 1. Determine Mode and Prepare Script ---
        mode = input_data.get("@mode", "single")
        
        if mode == "batch":
            # In batch mode, the script comes from the array of all n8n items.
            tts_script = input_data.get("@items", [])
            speakers_dict = input_data.get("speakers", {})
            output_file_path = input_data.get("output_file_path")
            
            # The n8n UI for batch mode doesn't have these, so we use defaults.
            exaggeration = 0.5
            cfg_weight = 0.5

        else: # single mode
            item_data = input_data.get("@item", {})
            text = item_data.get("text")
            speaker_audio = item_data.get("speaker_audio_path")
            output_file_path = item_data.get("output_file_path")
            exaggeration = input_data.get("exaggeration", 0.5)
            cfg_weight = input_data.get("cfg_weight", 0.5)

            if not text or not speaker_audio or not output_file_path:
                raise ValueError("For single line mode, 'Text', 'Speaker Reference', and 'Output File Path' are required.")
            
            speakers_dict = {"default_speaker": speaker_audio}
            tts_script = [{"speaker": "default_speaker", "text": text}]

        if not output_file_path:
            raise ValueError("output_file_path is a required field.")

        # --- 2. Your Logic Here ---
        speaker_temp_wavs = {}
        for speaker_id, audio_path in speakers_dict.items():
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"Reference audio for '{speaker_id}' not found at: {audio_path}")
            
            tmp_input_wav_path = tempfile.mktemp(suffix=f"_{speaker_id}.wav")
            temp_files_to_clean.append(tmp_input_wav_path)
            ffmpeg.input(audio_path).output(tmp_input_wav_path, acodec='pcm_s16le', ar=24000).run(overwrite_output=True, quiet=True)
            speaker_temp_wavs[speaker_id] = tmp_input_wav_path
        
        model = ChatterboxTTS.from_pretrained(device="cpu")

        temp_wav_files = []
        for item in tts_script:
            text = item.get("text")
            speaker_id = item.get("speaker")
            if not text or not speaker_id: continue

            reference_wav_path = speaker_temp_wavs.get(speaker_id)
            if not reference_wav_path:
                raise ValueError(f"Invalid speaker_id '{speaker_id}' in script.")

            wav = model.generate(
                text, 
                audio_prompt_path=reference_wav_path,
                exaggeration=item.get("exaggeration", exaggeration),
                cfg_weight=item.get("cfg_weight", cfg_weight),
                temperature=0.7
            )
            
            tmp_wav_path = tempfile.mktemp(suffix=".wav")
            temp_files_to_clean.append(tmp_wav_path)
            ta.save(tmp_wav_path, wav, model.sr)
            temp_wav_files.append({"path": tmp_wav_path})

        # Process output
        if temp_wav_files:
            list_file_path = tempfile.mktemp(suffix=".txt")
            temp_files_to_clean.append(list_file_path)
            with open(list_file_path, "w", encoding='utf-8') as f:
                for wav_file in temp_wav_files:
                    safe_path = wav_file['path'].replace("'", "'\\''")
                    f.write(f"file '{safe_path}'\n")

            ffmpeg_command = ["ffmpeg", "-f", "concat", "-safe", "0", "-i", list_file_path, "-c:a", "aac", "-b:a", "128k", "-loglevel", "quiet", "-y", output_file_path]
            subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True)
            generated_output_files.append(output_file_path)
        
        # --- 3. Return Clean JSON Output ---
        result = {
            "status": "success",
            "message": "Audio processing completed successfully.",
            "output_files": generated_output_files
        }
        print(json.dumps(result, indent=4))

    except Exception as e:
        error_message = {"status": "error", "message": str(e)}
        print(json.dumps(error_message), file=sys.stderr)
        sys.exit(1)
    finally:
        for file_path in temp_files_to_clean:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass

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
