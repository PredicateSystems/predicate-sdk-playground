"""
Test script to verify setup before running demos
"""
import os
import sys
from dotenv import load_dotenv

print("Testing demo setup...\n")

# Check .env file
env_path = os.path.join(os.path.dirname(__file__), '.env')
if not os.path.exists(env_path):
    print(f"❌ .env file not found at: {env_path}")
    print("\nPlease create a .env file with:")
    print("OPENAI_API_KEY=your_key_here")
    print("PREDICATE_API_KEY=your_key_here  # Optional")
    sys.exit(1)
else:
    print(f"✅ .env file found")

# Load environment variables
load_dotenv(env_path)

# Check API keys
openai_key = os.getenv('OPENAI_API_KEY')
sentience_key = os.getenv('PREDICATE_API_KEY')

if not openai_key:
    print("❌ OPENAI_API_KEY not set in .env file")
    sys.exit(1)
else:
    print(f"✅ OPENAI_API_KEY found (length: {len(openai_key)})")

if sentience_key:
    print(f"✅ PREDICATE_API_KEY found (length: {len(sentience_key)})")
else:
    print("⚠️  PREDICATE_API_KEY not set (Demo 1 will use free tier)")

# Check imports
print("\nChecking Python packages...")

try:
    import openai
    print(f"✅ openai installed (version: {openai.__version__})")
except ImportError:
    print("❌ openai not installed. Run: pip install openai")
    sys.exit(1)

try:
    from playwright.sync_api import sync_playwright
    print("✅ playwright installed")
except ImportError:
    print("❌ playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from predicate import PredicateBrowser, snapshot
    print("✅ sentience SDK importable")
except ImportError as e:
    print(f"❌ sentience SDK not importable: {e}")
    print("Run: pip install -e . from the sdk-python root directory")
    sys.exit(1)

try:
    import moviepy
    print("✅ moviepy installed")
except ImportError:
    print("⚠️  moviepy not installed. Videos won't be generated.")
    print("To install: pip install moviepy")

print("\n" + "="*60)
print("✅ Setup verification complete!")
print("="*60)
print("\nYou can now run:")
print("  python demo1_sdk_llm/main.py")
print("  python demo2_vision_llm/main.py")
print("  python run_both_demos.py")
print()
