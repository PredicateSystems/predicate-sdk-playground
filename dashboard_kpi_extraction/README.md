# Demo 4: Interactive SPA Dashboard - KPI Extraction

This demo navigates to the dashboard page of a fake Next.js site (Local Llama Land) and extracts KPI values. It builds upon Demo 3 (Login + Profile) by demonstrating extraction from a dynamic SPA dashboard.

## Overview

**Task:** Extract main KPI values from a dashboard (e.g., analytics).

**Site:** https://sentience-sdk-playground.vercel.app/dashboard

SPAs and dynamic content are where traditional scraping + vision agents fail; Sentience's structure inference helps extract semantic data reliably.

## Site Characteristics

The demo site includes intentional challenges:

- **Delayed hydration**: Dashboard KPI cards and content load after ~900-1500ms (setTimeout)
- **Dynamic KPI cards**: Three KPI cards with labels, values, and hints
- **Late-loading table**: Event table loads after separate delay
- **Optional live mode**: `?live=1` causes continuous DOM churn every 400ms (for stress testing)
- **SVG chart**: Engagement chart with polyline (tests handling of non-text elements)

## Target KPIs to Extract

- **Llama Coins**: 128 (Monthly balance)
- **Active Herds**: 7 (Groups you follow)
- **Messages**: 3 (Unread)

## Flow

1. Navigate to login page → wait for form hydration
2. Fill username field → LLM identifies textbox, types "testuser"
3. Fill password field → LLM identifies password input, types "password123"
4. Click login button → LLM identifies "Sign in" button, waits for navigation
5. Navigate to dashboard page → click "Dashboard" link from profile page
6. Wait for KPI cards to load → use `eventually(exists("text~'Llama Coins'"))` with retries
7. Extract all three KPI values → verify each value matches expected
8. Verify event table loaded → check for "Recent events" and row content
9. Enable live mode & re-extract KPIs → stress test: prove snapshot stability during DOM churn

## Key Features Demonstrated

- SPA dashboard handling with delayed hydration
- Semantic KPI extraction from dynamic cards
- Verification assertions for extracted values
- Retry semantics with `eventually()` for late-loading content
- Snapshot stability during DOM churn (live mode stress test)
- Local LLM for element identification (Qwen 2.5 3B)
- Cloud tracing for debugging and replay

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
cd dashboard_kpi_extraction
python main.py
```

## Expected Output

The demo will:
1. Navigate to login page and wait for form hydration
2. Fill username and password fields
3. Click login button
4. Navigate to dashboard page
5. Wait for KPI cards to load (900-1500ms delay)
6. Extract all three KPI values (Llama Coins: 128, Active Herds: 7, Messages: 3)
7. Verify event table loaded
8. Enable live mode and re-extract KPIs during DOM churn

## Screenshots & Video

Screenshots are saved to `screenshots/<timestamp>/` and a video is generated in `video/dashboard_kpi_<timestamp>.mp4`.

## Assertions Used

- `exists()`: Verify KPI elements and table content
- `url_contains()`: Verify correct page
- `.eventually()`: Wait for delayed hydration and late-loading content
- Custom assertions: Verify extracted KPI values match expected

## Token Usage

The demo tracks token usage per step and provides a summary at the end. Typical usage:
- ~3,000-5,000 total tokens for complete dashboard extraction
- Most tokens used for element identification (LLM finding KPI cards and navigation elements)
