# Setup Instructions

## Virtual Environment Setup (Already Complete!)

A virtual environment has been created with MoviePy 1.x and all dependencies installed.

### What's Already Done

✅ Virtual environment created (`venv/`)
✅ MoviePy 1.0.3 installed (compatible version)
✅ All dependencies installed
✅ Predicate SDK installed
✅ Playwright browsers downloaded
✅ Shell scripts created for easy execution

## Quick Verification

```bash
source venv/bin/activate
python test_setup.py
```

Expected output:
```
✅ .env file found
✅ OPENAI_API_KEY found
✅ PREDICATE_API_KEY found
✅ openai installed
✅ playwright installed
✅ sentience SDK importable
✅ moviepy installed
```

## Running the Demos

### Easy Way (Using Shell Scripts)

```bash
# Run both demos with comparison
./run_both.sh

# Or run individually
./run_demo1.sh  # SDK + LLM demo
./run_demo2.sh  # Vision + LLM demo
```

### Manual Way

```bash
# Always activate venv first
source venv/bin/activate

# Then run
python demo1_sdk_llm/main.py
# or
python demo2_vision_llm/main.py
# or
python run_both_demos.py
```

## Troubleshooting

### If venv doesn't exist or is broken

Recreate it:
```bash
# Remove old venv
rm -rf venv

# Create new venv
python -m venv venv

# Activate it
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install -e ..
playwright install chromium
```

### MoviePy Import Error

Make sure you're using the venv:
```bash
source venv/bin/activate
python -c "import moviepy; print(moviepy.__version__)"
# Should output: 1.0.3
```

If you see 2.x version, reinstall:
```bash
pip uninstall moviepy -y
pip install moviepy==1.0.3
```

### ImageMagick Not Found (TextClip error)

MoviePy needs ImageMagick for text rendering:

**macOS:**
```bash
brew install imagemagick
```

**Linux:**
```bash
sudo apt-get install imagemagick
```

**Windows:**
Download from: https://imagemagick.org/script/download.php

### Playwright Browser Not Found

Reinstall browsers:
```bash
source venv/bin/activate
playwright install chromium
```

## Dependencies Summary

### Installed in venv:
- **python-dotenv**: Environment variables
- **openai**: LLM API client (2.14.0)
- **playwright**: Browser automation (1.41.0)
- **moviepy**: Video generation (1.0.3) ⚠️ Version 1.x required!
- **Pillow**: Image processing (10.2.0)
- **predicate-sdk**: SDK (installed from parent directory)

### System Dependencies:
- **ImageMagick**: Text rendering for MoviePy
- **FFmpeg**: Video encoding (installed by Playwright)

## File Structure

```
playground/
├── venv/                    # Virtual environment (DO NOT COMMIT)
├── run_demo1.sh            # Helper script for Demo 1
├── run_demo2.sh            # Helper script for Demo 2
├── run_both.sh             # Helper script for both demos
├── .env                    # API keys (DO NOT COMMIT)
├── requirements.txt        # Python dependencies
└── test_setup.py           # Setup verification
```

## Environment Variables (.env)

Make sure your `.env` file contains:
```
OPENAI_API_KEY=sk-...
PREDICATE_API_KEY=...  # Optional, will use free tier if not set
```

## Ready to Run!

Everything is set up. Just run:
```bash
./run_both.sh
```

Or follow the [QUICKSTART.md](QUICKSTART.md) for detailed instructions.
