# Demo 5: Form Validation + Submission

This demo completes a multi-step onboarding form on Local Llama Land with validation gating at each step.

## Overview

**Task:** Fill a 4-step onboarding form with validation and verify successful submission.

**Site:** https://sentience-sdk-playground.vercel.app/forms/onboarding

## Form Steps

1. **Email** (Step 1)
   - Must be valid email format (contains @)
   - Next button disabled until valid email entered

2. **Display Name** (Step 2)
   - Must be at least 2 characters
   - Next button disabled until valid name entered

3. **Plan Selection** (Step 3)
   - Select plan (radio button: "free" or "pro")
   - Check Terms checkbox
   - Next button disabled until both plan selected AND terms checked

4. **Review & Submit** (Step 4)
   - Review entered data
   - Submit button
   - Success message appears after submission

## Key Features Demonstrated

- **State-aware assertions**: `is_enabled()`, `is_disabled()`, `value_contains()`, `is_checked()`
- **Validation gating**: Assert button state at each step
- **Multi-step navigation**: Handle step transitions with delays (450-1100ms)
- **Success verification**: Wait for and verify success message
- **Local LLM**: Qwen 2.5 3B for element identification
- **Human-like interaction**: Cursor movement and typing delays
- **Cloud tracing**: Full trace upload for debugging

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
cd form_validation_submission
python main.py
```

## Expected Output

The demo will:
1. Navigate to the onboarding form
2. Fill email field and verify Next button becomes enabled
3. Click Next and transition to Step 2
4. Fill display name and verify Next button becomes enabled
5. Click Next and transition to Step 3
6. Select plan (radio button)
7. Check Terms checkbox and verify Next button becomes enabled
8. Click Next and transition to Step 4 (Review)
9. Click Submit button
10. Verify success message: "Success! Your profile is ready."

## Screenshots & Video

Screenshots are saved to `screenshots/<timestamp>/` and a video is generated in `video/form_validation_<timestamp>.mp4`.

## Assertions Used

- `exists()`: Verify form elements and success message
- `is_enabled()` / `is_disabled()`: Verify button state transitions
- `value_contains()`: Verify field values match expected
- `is_checked()`: Verify radio button and checkbox selection
- `url_contains()`: Verify correct page
- `.eventually()`: Wait for state transitions and success message

## Token Usage

The demo tracks token usage per step and provides a summary at the end. Typical usage:
- ~3,000-5,000 total tokens for complete form submission
- Most tokens used for element identification (LLM finding form fields)
