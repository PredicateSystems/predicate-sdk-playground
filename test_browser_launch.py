"""
Simple test to verify browser launches without crashing
"""
import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Load environment
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from predicate import PredicateBrowser

print("Testing browser launch...")
print("This will open a browser window for 5 seconds then close it.")
print()

try:
    with PredicateBrowser(headless=False) as browser:
        print("✅ Browser launched successfully!")
        print(f"   Browser type: {browser.context.browser.browser_type.name}")

        # Navigate to a simple page
        browser.page.goto("https://example.com")
        print("✅ Navigation successful!")

        # Wait a moment
        import time
        time.sleep(5)

    print("✅ Browser closed successfully!")
    print("\n🎉 All tests passed! The browser works without crashes.")

except Exception as e:
    print(f"\n❌ Browser test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
