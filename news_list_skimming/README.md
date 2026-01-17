# Demo 1: News List Skimming

This demo finds the top story on a dynamic news page (Hacker News Show) using local LLM inference.

## Overview

**Task:** Find the top story on a dynamic news page (like Hacker News Show).

**Site:** https://news.ycombinator.com/show

This demo showcases:
- Structure-first snapshot handles layout
- Local model parsing text
- Vision fallback only if the site layout changes radically
- Good demo for token savings + correctness

## Dependencies

From `sentience-sdk-playground/`:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r news_list_skimming/requirements.txt

# Install Sentience SDK
pip install sentienceapi

# Install Playwright browsers
playwright install chromium
```

Required packages (from `news_list_skimming/requirements.txt`):
- `python-dotenv>=1.0.0`
- `playwright>=1.57.0`
- `playwright-stealth>=1.0.6`
- `torch>=2.2.0` (for local LLM)
- `transformers>=4.46.0` (for local LLM)
- `accelerate>=0.30.0` (for local LLM)
- `pillow>=10.0.0` (for image processing)
- `mlx-vlm>=0.1.0` (optional, for Apple Silicon vision fallback)

## Environment Variables

Create a `.env` file or export these variables:

```bash
# Optional but recommended: enables Gateway refinement + cloud trace upload
# Get your free API key at https://www.sentienceapi.com
export SENTIENCE_API_KEY="sk_..."

# Local text model (default: Qwen/Qwen2.5-3B-Instruct)
export LOCAL_TEXT_MODEL="Qwen/Qwen2.5-3B-Instruct"

# Optional: HuggingFace token to avoid rate limits
export HF_TOKEN="hf_..."

# Vision fallback: pick ONE (optional)
# (A) MLX-VLM (best for Apple Silicon quantized)
export LOCAL_VISION_PROVIDER="mlx"
export LOCAL_VISION_MODEL="mlx-community/Qwen3-VL-8B-Instruct-3bit"

# (B) HF Transformers vision model
# export LOCAL_VISION_PROVIDER="hf"
# export LOCAL_VISION_MODEL="Qwen/Qwen3-VL-8B-Instruct"
```

## Running the Demo

```bash
cd news_list_skimming
python main.py
```

## Notes

- This demo intentionally uses **Hacker News "Show"** because it's stable and fast, which makes it ideal for public demos.
- If you want to force vision fallback for a recording, lower `max_snapshot_attempts` and raise `min_confidence` in `main.py`.
