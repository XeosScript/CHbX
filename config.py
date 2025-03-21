import os

DEFAULT_SAVE_PATH = "downloaded_site"
REQUEST_TIMEOUT = 10 

# Request headers (change as you wish)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36"

# List of file extensions to download
RESOURCE_EXTENSIONS = ['.css', '.js', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.eot']

def get_config():
    return {
        "save_path": os.environ.get("SAVE_PATH", DEFAULT_SAVE_PATH),
        "request_timeout": int(os.environ.get("REQUEST_TIMEOUT", REQUEST_TIMEOUT)),
        "user_agent": USER_AGENT,
        "resource_extensions": RESOURCE_EXTENSIONS
    }