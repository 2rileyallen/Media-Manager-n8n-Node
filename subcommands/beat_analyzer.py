import sys
import os
import json

# --- Required Metadata ---

# 1. DEPENDENCIES
REQUIRES = [
    "librosa==0.10.1",
    "numpy==1.26.4",
    "setuptools", 
]

# 2. N8N UI SCHEMA
# All subcommands now use a MODES dictionary. For simple tools,
# it contains just one mode.
MODES = {
    "default": {
        "displayName": "Process Each Item Individually",
        "input_schema": [
            {
                "name": "audio_file",
                "displayName": "Audio File Path",
                "type": "string",
                "required": True,
                "description": "The absolute path to the audio file to analyze."
            },
            {
                "name": "beats_per_second",
                "displayName": "Beats Per Second",
                "type": "number",
                "default": 2.0,
                "description": "The frequency of beats to analyze per second."
            },
            {
                "name": "smoothing_factor",
                "displayName": "Smoothing Factor",
                "type": "number",
                "default": 0.1,
                "description": "A value between 0.0 and 1.0 to smooth the beat analysis."
            }
        ]
    }
}

# --- Helper Functions ---

def analyze_beats(audio_file, beats_per_second, smoothing_factor=0.1):
    """
    Analyze an audio file and return beat strengths at a specified frequency.
    """
    # CORRECT: Import required modules inside the function that uses them.
    import librosa
    import numpy as np

    try:
        y, sr = librosa.load(audio_file)
        
        rms = librosa.feature.rms(y=y)[0]
        mean_rms = np.mean(rms)
        
        if mean_rms < 0.05: loudness_category = 1
        elif mean_rms < 0.1: loudness_category = 2
        elif mean_rms < 0.2: loudness_category = 3
        else: loudness_category = 4
        
        duration = librosa.get_duration(y=y, sr=sr)
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        frames_per_second = len(onset_env) / duration
        
        num_beats = int(duration * beats_per_second)
        timestamps = np.arange(num_beats) / beats_per_second
        
        window_size = 0.1
        beat_strengths = []
        
        for timestamp in timestamps:
            start_time = max(0, timestamp - window_size)
            end_time = min(duration, timestamp + window_size)
            start_frame = int(start_time * frames_per_second)
            end_frame = int(end_time * frames_per_second)
            
            if start_frame >= len(onset_env): break
            end_frame = min(end_frame, len(onset_env))
            
            if start_frame < end_frame:
                window_max = np.max(onset_env[start_frame:end_frame])
            else:
                window_max = onset_env[start_frame] if start_frame < len(onset_env) else 0
            
            beat_strengths.append(window_max)
        
        smoothed_strengths = np.array(beat_strengths)
        for i in range(1, len(beat_strengths)):
            smoothed_strengths[i] = (1 - smoothing_factor) * beat_strengths[i] + smoothing_factor * smoothed_strengths[i-1]
        
        if len(smoothed_strengths) > 0:
            min_val, max_val = np.min(smoothed_strengths), np.max(smoothed_strengths)
            if max_val > min_val:
                normalized = ((smoothed_strengths - min_val) / (max_val - min_val)) * 100
            else:
                normalized = np.zeros_like(smoothed_strengths)
        else:
            normalized = []
            
        return normalized.astype(int).tolist(), loudness_category
        
    except Exception as e:
        # Re-raise the exception to be caught by the main function's error handler
        raise RuntimeError(f"Error analyzing audio file: {e}")

# --- Main Execution Logic ---

def main(input_data, tool_path):
    """
    The primary function executed by the manager.
    """
    try:
        # --- 1. Access Input Data ---
        # For single-mode tools, the parameters are nested under the '@item' key.
        item_data = input_data.get("@item", {})
        audio_file = item_data.get("audio_file")
        beats_per_second = item_data.get("beats_per_second", 2.0)
        smoothing = item_data.get("smoothing_factor", 0.1)

        if not audio_file or not os.path.exists(audio_file):
            raise FileNotFoundError(f"Audio file not found at '{audio_file}'")

        # --- 2. Your Logic Here ---
        beat_strengths, loudness_category = analyze_beats(audio_file, beats_per_second, smoothing)
        
        loudness_descriptions = {
            1: "Very quiet (e.g., ambient, soft classical)",
            2: "Moderate (e.g., acoustic, soft pop)",
            3: "Loud (e.g., rock, electronic)",
            4: "Very loud (e.g., metal, hard electronic)"
        }
        
        beat_data = [
            {"time": round(i / beats_per_second, 2), "strength": strength}
            for i, strength in enumerate(beat_strengths)
        ]
        
        # --- 3. Return Clean JSON Output ---
        result = {
            "status": "success",
            "input": audio_file,
            "beats_per_second": beats_per_second,
            "loudness_category": loudness_category,
            "loudness_description": loudness_descriptions.get(loudness_category, "Unknown"),
            "total_beats": len(beat_strengths),
            "beat_data": beat_data
        }
        # The result is printed to stdout for n8n to capture.
        print(json.dumps(result, indent=4))

    except Exception as e:
        # Catch any exceptions and report them clearly as JSON to stderr.
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
            print(json.dumps({"status": "error", "message": "Invalid JSON input from stdin"}), file=sys.stderr)
            sys.exit(1)
    else:
        print(json.dumps({"status": "error", "message": "No JSON input provided to stdin"}), file=sys.stderr)
        sys.exit(1)
