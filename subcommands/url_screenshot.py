import sys
import os
import json
import time
import subprocess

# --- Required Metadata ---
# This section defines the contract with the Media Manager framework.

# 1. DEPENDENCIES
# The manager will install these packages.
REQUIRES = [
    "playwright"
]

# 2. N8N UI SCHEMA
# This defines the input fields for the n8n user interface.
INPUT_SCHEMA = [
    {
        "name": "url",
        "displayName": "Website URL",
        "type": "string",
        "required": True,
        "description": "The full URL of the website to capture.",
        "default": "https://github.com/n8n-io/n8n"
    },
    {
        "name": "output_path",
        "displayName": "Output File Path",
        "type": "string",
        "required": True,
        "description": "The absolute path to save the screenshot (e.g., 'C:\\screenshots\\output.png').",
        "default": ""
    }
]

# --- Helper Functions ---
def _ensure_playwright_browsers_installed():
    """
    Runs `playwright install` to ensure browser binaries are present.
    This is designed to be run once automatically.
    """
    try:
        # Use sys.executable to ensure we're using the python from the correct virtual env
        subprocess.run([sys.executable, "-m", "playwright", "install"], check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        # This error is often noisy but doesn't mean failure if browsers are already there.
        # A more reliable check is to see if the launch command works.
        # For simplicity here, we'll assume the user can see the error if it's critical.
        print(f"Playwright install command finished. Stderr: {e.stderr}", file=sys.stderr)
        return True # Proceed even if there are warnings, as browsers might be installed.
    except Exception as e:
        print(f"Failed to run Playwright install: {str(e)}", file=sys.stderr)
        return False

# --- Main Execution Logic ---
def main(input_data, tool_path):
    """
    Main function to take a screenshot of a given URL.
    """
    # It's good practice to import heavyweight libraries inside the main function.
    from playwright.sync_api import sync_playwright

    processed_results = []

    if "@items" in input_data:
        script_items = input_data.get("@items", [])
    elif "@item" in input_data:
        script_items = [input_data.get("@item", {})]
    else:
        raise ValueError("Invalid input format. Input JSON must contain either an '@item' or '@items' key.")

    # Run the one-time browser installation check.
    if not _ensure_playwright_browsers_installed():
        raise RuntimeError("Failed to install or verify Playwright browsers. Cannot proceed.")

    for item in script_items:
        url = item.get("url")
        output_path = item.get("output_path")

        if not url or not output_path:
            raise ValueError("Missing required parameters: 'url' and 'output_path' are required.")

        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Navigate to the page and wait for it to be mostly loaded.
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # A simple loop to scroll to the bottom a few times.
            # This helps trigger lazy-loaded images on many static sites.
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2) # Wait for content to potentially load

            # Take the final screenshot.
            page.screenshot(path=output_path, full_page=True)
            browser.close()

        processed_results.append({
            "status": "success",
            "url": url,
            "output_file": os.path.abspath(output_path)
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
