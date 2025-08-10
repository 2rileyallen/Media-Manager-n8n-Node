import sys
import os
import json
import re
import time
import logging

# --- Required Metadata ---
# This section defines the contract with the Media Manager framework.

# 1. DEPENDENCIES
# The manager will install these packages. PyTorch is now excluded because
# it must be installed manually with a specific CUDA version.
REQUIRES = [
    "fastvideo==0.1.5"
]

# 2. N8N UI SCHEMA
# This list of dictionaries defines the input fields that will be displayed
# in the n8n user interface for this node.
INPUT_SCHEMA = [
    {
        "name": "prompt",
        "displayName": "Prompt",
        "type": "string",
        "required": True,
        "description": "The text description of the video you want to create.",
        "default": "A majestic eagle soaring through a cloudy sky at sunset."
    },
    {
        "name": "output_path",
        "displayName": "Output Path",
        "type": "string",
        "required": True,
        "description": "The absolute path for the output video. Can be a directory (e.g., 'C:\\videos') or a full file path (e.g., 'C:\\videos\\my_video.mp4').",
        "default": ""
    },
    {
        "name": "attention_backend",
        "displayName": "Attention Backend (Performance)",
        "type": "options",
        "options": [
            {"name": "Sliding Tile Attention (Recommended)", "value": "SLIDING_TILE_ATTN"},
            {"name": "Video Sparse Attention (Fastest)", "value": "VIDEO_SPARSE_ATTN"},
            {"name": "Default Pytorch (Compatible)", "value": "DEFAULT"},
        ],
        "description": "Select the attention mechanism. Sliding Tile is a good balance of speed and VRAM usage.",
        "default": "SLIDING_TILE_ATTN"
    }
]

# 3. SPECIAL SETUP INSTRUCTIONS
# This tool requires a one-time manual installation of the GPU-enabled PyTorch library.
# After the manager creates the environment for this tool, run these commands in your terminal:
#
# --- Windows ---
# cd C:\path\to\your\Media-Manager-n8n-Node
# call subcommands_envs\fastwan_t2v_gen\Scripts\activate
# pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
#
# --- Linux/macOS ---
# cd /path/to/your/Media-Manager-n8n-Node
# source subcommands_envs/fastwan_video_gen/bin/activate
# pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121


# --- Helper Functions ---
def sanitize_filename(name):
    """Removes invalid characters from a string to make it a valid filename."""
    return re.sub(r'[\\/*?:"<>|]', "", name)

def prepare_output_path(user_path, prompt):
    """
    Prepares a full, valid output file path from user input.
    """
    if os.path.isdir(user_path) or not os.path.splitext(user_path)[1]:
        output_dir = user_path
        sanitized_prompt = sanitize_filename(prompt)[:50]
        timestamp = int(time.time())
        filename = f"{sanitized_prompt}_{timestamp}.mp4"
    else:
        output_dir = os.path.dirname(user_path)
        base_name = os.path.basename(user_path)
        filename = os.path.splitext(base_name)[0] + ".mp4"

    os.makedirs(output_dir, exist_ok=True)
    return os.path.join(output_dir, filename)


# --- Main Execution Logic ---
def main(input_data, tool_path):
    """
    Main function to process input and generate videos using the FastVideo library.
    """
    logging.basicConfig(level=logging.ERROR)
    logging.getLogger("fastvideo").setLevel(logging.ERROR)
    logging.getLogger("torch").setLevel(logging.ERROR)

    from fastvideo import VideoGenerator

    processed_results = []

    if "@items" in input_data:
        script_items = input_data.get("@items", [])
    elif "@item" in input_data:
        script_items = [input_data.get("@item", {})]
    else:
        raise ValueError("Invalid input format. Input JSON must contain either an '@item' or '@items' key.")

    for item in script_items:
        prompt = item.get("prompt")
        user_output_path = item.get("output_path")
        if not prompt or not user_output_path:
            raise ValueError("Missing required parameters in item: 'prompt' and 'output_path' are required.")

        # Hardcode the model since we are only supporting this one for now.
        model_name = "FastVideo/FastWan2.1-T2V-1.3B-Diffusers"
        attention_backend = item.get("attention_backend", "SLIDING_TILE_ATTN")

        os.environ["FASTVIDEO_ATTENTION_BACKEND"] = attention_backend

        generator = VideoGenerator.from_pretrained(model_name, num_gpus=1)
        final_video_path = prepare_output_path(user_output_path, prompt)
        
        gen_kwargs = {
            "prompt": prompt,
            "return_frames": False,
            "output_path": final_video_path,
            "save_video": True
        }
        
        generator.generate_video(**gen_kwargs)

        processed_results.append({
            "status": "success",
            "prompt": prompt,
            "modelUsed": model_name,
            "generatedVideoPath": final_video_path
        })

    print(json.dumps({"results": processed_results}, indent=4))


# --- Boilerplate for Direct Execution ---
if __name__ == "__main__":
    stdin_content = sys.stdin.read()
    if stdin_content:
        try:
            parsed_data = json.loads(stdin_content)
            subcommand_tool_path = os.environ.get("SUBCOMMAND_TOOL_PATH")
            if not subcommand_tool_path:
                raise EnvironmentError("SUBCOMMAND_TOOL_PATH environment variable not set by manager.")
            
            os.makedirs(subcommand_tool_path, exist_ok=True)
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
