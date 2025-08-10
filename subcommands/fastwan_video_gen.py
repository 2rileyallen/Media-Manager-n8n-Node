import sys
import os
import json
import re
import time

# --- Required Metadata ---
# This section defines the contract with the Media Manager framework.

# 1. DEPENDENCIES
# The manager will install these packages into a dedicated virtual environment
# for this subcommand. 'fastvideo' will pull in its own dependencies like
# torch, diffusers, and transformers.
REQUIRES = [
    "fastvideo==0.1.5",
    "torch",
    "torchvision",
    "torchaudio"
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
        "name": "image_path",
        "displayName": "Input Image Path (Optional for 5B)",
        "type": "string",
        "description": "The absolute path to an input image for image-to-video generation. This is only used by models that support it (e.g., FastWan 2.2).",
        "default": ""
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
        "name": "model_name",
        "displayName": "Pre-trained Model",
        "type": "options",
        "options": [
            {"name": "FastWan 2.2 - 5B (Text/Image-to-Video)", "value": "FastVideo/FastWan2.2-TI2V-5B"},
            {"name": "FastWan 2.1 - 1.3B (Text-to-Video)", "value": "FastVideo/FastWan2.1-T2V-1.3B-Diffusers"}
        ],
        "required": True,
        "description": "Select the base model for video generation. The 5B model supports both text and images as input.",
        "default": "FastVideo/FastWan2.2-TI2V-5B"
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

# --- Helper Functions ---
def sanitize_filename(name):
    """Removes invalid characters from a string to make it a valid filename."""
    return re.sub(r'[\\/*?:"<>|]', "", name)

def prepare_output_path(user_path, prompt):
    """
    Prepares a full, valid output file path from user input.
    - If user_path is a directory, it creates a default filename.
    - If user_path is a file, it uses it.
    - Ensures the final path has a .mp4 extension.
    """
    # Check if the provided path is a directory
    if os.path.isdir(user_path) or not os.path.splitext(user_path)[1]:
        output_dir = user_path
        # Create a default filename from the prompt
        sanitized_prompt = sanitize_filename(prompt)[:50] # Truncate for safety
        timestamp = int(time.time())
        filename = f"{sanitized_prompt}_{timestamp}.mp4"
    else:
        output_dir = os.path.dirname(user_path)
        base_name = os.path.basename(user_path)
        # Ensure the extension is .mp4
        filename = os.path.splitext(base_name)[0] + ".mp4"

    # Create the output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    return os.path.join(output_dir, filename)


# --- Main Execution Logic ---
def main(input_data, tool_path):
    """
    Main function to process input and generate videos using the FastVideo library.
    """
    # CRITICAL: Import heavyweight dependencies here, not at the top level.
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

        model_name = item.get("model_name", "FastVideo/FastWan2.2-TI2V-5B")
        attention_backend = item.get("attention_backend", "SLIDING_TILE_ATTN")
        image_path = item.get("image_path")

        os.environ["FASTVIDEO_ATTENTION_BACKEND"] = attention_backend

        generator = VideoGenerator.from_pretrained(
            model_name,
            num_gpus=1, # Hardcoded to 1 as requested
            cache_dir=tool_path
        )

        # Prepare the final output path
        final_video_path = prepare_output_path(user_output_path, prompt)
        
        # Build the generation arguments
        gen_kwargs = {
            "prompt": prompt,
            "return_frames": False,
            "output_path": final_video_path,
            "save_video": True
        }

        # Add image_path to arguments ONLY if it's provided and the model supports it
        if image_path and os.path.exists(image_path) and "TI2V" in model_name:
            gen_kwargs["image_path"] = image_path
        
        # Generate the video using keyword arguments
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
