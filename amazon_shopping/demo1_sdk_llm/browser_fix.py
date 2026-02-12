"""
Temporary browser fix for macOS sandbox crash issue
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from predicate import PredicateBrowser
import tempfile
import shutil
import time
from playwright.sync_api import sync_playwright

# Monkey-patch the start method to remove --no-sandbox on macOS
original_start = PredicateBrowser.start

def patched_start(self):
    """Patched start method that removes --no-sandbox flag on macOS"""
    import platform

    # Find extension directory
    package_ext_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'predicate', 'extension')
    dev_ext_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '..', 'sentience-chrome', 'dist')

    if os.path.exists(package_ext_path):
        extension_source = package_ext_path
    elif os.path.exists(dev_ext_path):
        extension_source = dev_ext_path
    else:
        raise FileNotFoundError("Extension not found")

    # Create temporary extension bundle
    self._extension_path = tempfile.mkdtemp(prefix="predicate-ext-")
    shutil.copytree(extension_source, self._extension_path, dirs_exist_ok=True)

    self.playwright = sync_playwright().start()

    # Build launch arguments - REMOVE --no-sandbox on macOS
    args = [
        f"--disable-extensions-except={self._extension_path}",
        f"--load-extension={self._extension_path}",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
    ]

    # Only add --no-sandbox on Linux (where it's needed)
    if platform.system() == 'Linux':
        args.append("--no-sandbox")

    # Handle headless mode
    if self.headless:
        args.append("--headless=new")

    # Launch persistent context
    self.context = self.playwright.chromium.launch_persistent_context(
        user_data_dir="",
        headless=False,
        args=args,
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )

    self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

    # Wait for extension
    time.sleep(0.5)

# Apply the patch
PredicateBrowser.start = patched_start
