# Demo 2: Shopping Cart Checkout Flow

This demo navigates to amazon.com, performs a search, picks a product from search results, goes to its product details page, adds it to cart, and verifies the checkout form.

## Overview

**Task:** Navigate a JS-heavy ecommerce site `amazon.com`, perform search, pick a product from the search results, go to its product details page, then add it to cart + verify checkout form.

**Site:** https://www.amazon.com

This demo showcases:
- Multiple pages (home → search results → product page → cart → checkout)
- Dynamic content loading (search results, product details)
- Real semantic actions (click, fill, verify)
- Anti-bot detection evasion with stealth mode

## Flow

1. Navigate to amazon.com → wait for page load
2. Find and click Amazon search box → use stealth typing pattern
3. Type search query with human-like jitter → "laptop" (example)
4. Submit search → wait for search results
5. Pick first product from search results → LLM identifies product link
6. Navigate to product details page → verify URL change (check for `/dp/{sku}` pattern)
7. Add product to cart → click "Add to Cart" button
   - If "Add to Your Order" drawer appears → click "No thanks" to dismiss
   - Wait for redirect to cart page (amazon.com/cart/...)
   - Verify "Added to cart" message on cart page
   - Click "Proceed to checkout" button
8. Verify checkout form appears → assert form elements exist

## Key Features Demonstrated

- **Multi-page navigation**: Handle transitions between home, search, product, cart, and checkout pages
- **Stealth typing pattern**: Human-like typing with jitter and pauses to avoid bot detection
- **Product selection**: LLM identifies and clicks product links from search results
- **Cart verification**: Assert cart contains items before checkout
- **Checkout form verification**: Verify checkout form elements are present
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
- `playwright-stealth>=1.0.6` (for anti-bot detection evasion)
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
cd amazon_shopping_with_assertions
python main.py
```

## Expected Output

The demo will:
1. Navigate to amazon.com
2. Find and click the search box
3. Type "laptop" with human-like typing pattern
4. Submit search and wait for results
5. Click the first product from search results
6. Navigate to product details page (verify `/dp/{sku}` URL pattern)
7. Click "Add to Cart" button
8. If "Add to Your Order" drawer appears, click "No thanks" to dismiss it
9. Wait for redirect to cart page and verify "Added to cart" message
10. Click "Proceed to checkout" button
11. Verify checkout form elements are present

## Screenshots & Video

Screenshots are saved to `screenshots/<timestamp>/` and a video is generated in `video/amazon_shopping_<timestamp>.mp4`.

## Assertions Used

- `exists()`: Verify page elements and form fields
- `url_contains()`: Verify correct page navigation
- `.eventually()`: Wait for dynamic content to load
- Custom assertions: Verify cart items and checkout form elements

## Token Usage

The demo tracks token usage per step and provides a summary at the end. Typical usage:
- ~5,000-8,000 total tokens for complete shopping flow
- Most tokens used for element identification (LLM finding search box, products, buttons)

## Notes

- **Anti-bot Detection**: Amazon.com has sophisticated anti-bot detection. This demo uses:
  - `playwright-stealth` (automatically applied by AsyncSentienceBrowser if installed)
  - Human-like typing pattern with jitter and pauses (40-140ms between keystrokes)
  - Persistent user data directory to maintain session state
  - Human-like cursor movement with overshoot and jitter

- **Flakiness Warning**: Amazon.com is known to be flaky due to:
  - Bot defenses that may block automated access
  - DOM churn and A/B tests
  - Dynamic content loading that varies by region
  - CAPTCHA challenges that may appear

- **Search Query**: The demo searches for "laptop" by default. You can modify `SEARCH_QUERY` in `main.py` to test with different products.
