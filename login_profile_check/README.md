# Demo 3: Login + Profile Check

This demo navigates to a fake Next.js site (Local Llama Land) and completes a login flow, then extracts username and email from the profile page.

## Overview

**Task:**
1. Log in to the site
2. Navigate to profile
3. Extract username and email

**Site:** https://sentience-sdk-playground.vercel.app/login

## Site Characteristics

The demo site (Local Llama Land) includes intentional challenges to test agent robustness:

- **Delayed hydration**: Login form loads after ~600ms (setTimeout/Suspense)
- **Button disabled→enabled**: Login button starts disabled, becomes enabled only after both username and password fields are filled
- **Profile page late-load**: Profile card content loads after 800-1200ms
- **Iframe**: The page includes an iframe element to test agent frame handling
- **Artificial navigation delay**: Login action has delay before redirecting

## Flow

1. Navigate to login page → wait for hydration with `eventually(exists("role=textbox"))`
2. Fill username field → LLM finds textbox, human-like typing
3. Fill password field → LLM finds password input, verify button becomes enabled
4. Click login button → verify button is enabled, LLM clicks, wait for navigation
5. Navigate to profile page → handle if not auto-redirected
6. Extract username AND email from profile card → wait for late-loading content

## Key Features Demonstrated

- State-aware assertions (`is_enabled`, `is_disabled`)
- Retry semantics with `eventually()`
- Local LLM for element identification
- Human-like cursor movement and typing
- Cloud tracing for debugging

## Dependencies

From `sentience-sdk-playground/`:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Install Sentience SDK
pip install sentienceapi

# Install Playwright browsers
playwright install chromium
```

Required packages (from `requirements.txt`):
- `python-dotenv>=1.0.0`
- `playwright>=1.57.0`
- `torch>=2.2.0` (for local LLM)
- `transformers>=4.46.0` (for local LLM)
- `accelerate>=0.30.0` (for local LLM)
- `pillow>=10.0.0` (for image processing)

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
```

## Running the Demo

```bash
cd login_profile_check
python main.py
```

## Expected Output

The demo will:
1. Navigate to login page and wait for form hydration
2. Fill username field ("testuser")
3. Fill password field ("password123")
4. Click login button (after verifying it's enabled)
5. Navigate to profile page
6. Extract username and email from profile card

## Screenshots & Video

Screenshots are saved to `screenshots/<timestamp>/` and a video is generated in `video/login_profile_<timestamp>.mp4`.

## Assertions Used

- `exists()`: Verify form elements and profile content
- `is_enabled()` / `is_disabled()`: Verify button state transitions
- `url_contains()`: Verify correct page
- `.eventually()`: Wait for delayed hydration and late-loading content

## Token Usage

The demo tracks token usage per step and provides a summary at the end. Typical usage:
- ~2,000-4,000 total tokens for complete login and profile extraction
- Most tokens used for element identification (LLM finding form fields and profile elements)
