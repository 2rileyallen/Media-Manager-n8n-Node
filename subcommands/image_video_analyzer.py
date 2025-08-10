import sys
import os
import json
import base64
import logging
import math

# --- Required Metadata ---
# This section defines the contract with the Media Manager framework.

# 1. DEPENDENCIES
# The manager will install these packages into a dedicated virtual environment.
REQUIRES = ["requests", "opencv-python", "numpy"]

# 2. N8N UI SCHEMA
# This defines the input fields for the n8n user interface.
INPUT_SCHEMA = [
    {
        "name": "file_path",
        "displayName": "Image or Video File Path",
        "type": "string",
        "required": True,
        "description": "The absolute path to the image or video file to analyze.",
        "default": ""
    },
    {
        "name": "prompt",
        "displayName": "Analysis Prompt",
        "type": "string",
        "description": "The specific question or instruction for the analysis model.",
        "default": "Provide a detailed summary of this video."
    },
    {
        "name": "keyframe_interval",
        "displayName": "Keyframe Interval (Seconds)",
        "type": "number",
        "description": "For videos, extract a frame for analysis every N seconds. Lower numbers are more detailed but slower.",
        "default": 2
    }
]

# --- AI Prompt Engineering ---
# Carefully crafted prompts for each stage of the analysis.
PROMPTS = {
    "image_analysis": "You are an expert image analyst. Analyze the following image and respond directly to the user's prompt.",
    "video_scene_analysis": "You are a video scene analyzer. The following image is a keyframe from a video. In a single, concise sentence, describe the primary action or subject in this frame. Do not add any preamble.",
    "video_chunk_summary": "You are a video summary assistant. The following is a list of sequential, one-sentence scene descriptions from a segment of a video. Synthesize these descriptions into a coherent paragraph that summarizes this video segment.",
    "video_final_analysis": "You are a helpful AI assistant. You will be given a detailed, chronologically-ordered summary of a video. Based *only* on this summary, answer the user's final question or request."
}

# --- Ollama Communication ---
def query_ollama(payload):
    """Sends a payload to the Ollama API and returns the response."""
    import requests
    try:
        response = requests.post("http://127.0.0.1:11434/api/generate", json=payload, timeout=600)
        response.raise_for_status()
        result = response.json()
        return result.get("response", "No response received.")
    except requests.exceptions.RequestException as e:
        # This will be caught and handled as an error in the calling function.
        raise ConnectionError(f"Error communicating with Ollama: {str(e)}")


# --- Image Analysis Logic ---
def analyze_image(file_path, prompt):
    """Analyzes a single image file."""
    with open(file_path, "rb") as f:
        image_data = f.read()
    image_b64 = base64.b64encode(image_data).decode("utf-8")

    payload = {
        "model": "gemma3:4b",
        "prompt": f"{PROMPTS['image_analysis']} User prompt: '{prompt}'",
        "images": [image_b64],
        "stream": False
    }
    analysis = query_ollama(payload)
    return {"file_path": file_path, "analysis": analysis}


# --- Hierarchical Video Analysis Logic ---
def analyze_video_hierarchically(file_path, user_prompt, keyframe_interval_seconds):
    """
    Analyzes a video using a multi-level summarization approach to handle
    long videos without exceeding the model's context window.
    """
    import cv2

    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        return {"error": f"Cannot open video file: {file_path}"}

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_seconds = frame_count / fps
    
    keyframe_interval_frames = int(keyframe_interval_seconds * fps)
    
    scene_descriptions = []
    current_frame_num = 0

    # Level 1: Analyze individual keyframes to get scene descriptions
    while cap.isOpened():
        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame_num)
        ret, frame = cap.read()
        if not ret:
            break

        _, buffer = cv2.imencode(".jpg", frame)
        frame_b64 = base64.b64encode(buffer).decode("utf-8")
        
        payload = {
            "model": "gemma3:4b",
            "prompt": PROMPTS['video_scene_analysis'],
            "images": [frame_b64],
            "stream": False
        }
        scene_desc = query_ollama(payload)
        scene_descriptions.append(scene_desc.strip())
        
        current_frame_num += keyframe_interval_frames
        if current_frame_num >= frame_count:
            break
    
    cap.release()

    if not scene_descriptions:
        return {"error": "Could not extract any keyframes or scene descriptions from the video."}

    # Level 2: Combine all scene descriptions into a final summary
    # For simplicity in this version, we'll combine all scenes at once.
    # A more complex implementation could add another summarization layer here for very long videos.
    full_summary_text = "\n".join(f"- {desc}" for desc in scene_descriptions)

    # Level 3: Ask the final question based on the generated summary
    final_payload = {
        "model": "gemma3:4b",
        "prompt": f"{PROMPTS['video_final_analysis']}\n\n--- VIDEO SUMMARY ---\n{full_summary_text}\n\n--- USER REQUEST ---\n{user_prompt}",
        "images": [], # No images needed for the final text-based analysis
        "stream": False
    }
    final_analysis = query_ollama(final_payload)

    return {"file_path": file_path, "analysis": final_analysis}


# --- Main Execution Logic ---
def main(input_data, tool_path):
    """
    Main function to process input from the n8n node.
    """
    processed_results = []

    if "@items" in input_data:
        script_items = input_data.get("@items", [])
    elif "@item" in input_data:
        script_items = [input_data.get("@item", {})]
    else:
        raise ValueError("Invalid input format. Input JSON must contain either an '@item' or '@items' key.")

    for item in script_items:
        file_path = item.get("file_path")
        if not file_path:
            processed_results.append({"error": "Missing 'file_path' in one of the input items."})
            continue
        
        prompt = item.get("prompt", "Provide a detailed summary.")
        keyframe_interval = item.get("keyframe_interval", 2)

        try:
            if not os.path.exists(file_path):
                 processed_results.append({"error": f"File not found: {file_path}"})
                 continue

            video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".flv"}
            is_video = any(file_path.lower().endswith(ext) for ext in video_extensions)

            if is_video:
                result = analyze_video_hierarchically(file_path, prompt, keyframe_interval)
            else:
                result = analyze_image(file_path, prompt)
            
            processed_results.append(result)

        except Exception as e:
            processed_results.append({"error": f"An unexpected error occurred processing {file_path}: {str(e)}"})

    print(json.dumps({"results": processed_results}, indent=4))

# --- Boilerplate for Direct Execution ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    
    stdin_content = sys.stdin.read()
    if stdin_content:
        try:
            parsed_data = json.loads(stdin_content)
            subcommand_tool_path = os.environ.get("SUBCOMMAND_TOOL_PATH", "")
            main(parsed_data, subcommand_tool_path)
        except json.JSONDecodeError:
            error_output = {"status": "error", "message": "Invalid JSON input from stdin."}
            print(json.dumps(error_output), file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            error_output = {"status": "error", "message": f"An error occurred during execution: {str(e)}"}
            print(json.dumps(error_output), file=sys.stderr)
            sys.exit(1)
    else:
        error_output = {"status": "error", "message": "No JSON input was provided via stdin."}
        print(json.dumps(error_output), file=sys.stderr)
        sys.exit(1)
