# LangChain + SentienceDebugger (Playground Demo)

This playground shows how to attach **SentienceDebugger** to a **SentienceBrowser**
page while a **LangChain / LangGraph** agent drives the browser.

You get:
- per-step **verification** in Sentience Studio
- screenshots + optional overlay annotations
- optional Playwright video artifact

## New: LangGraph “serious loop” demo (recommended)

There is now a LangGraph-based demo that makes the integration meaningful for browser automation:

- explicit loop: **plan → act → observe → verify → replan → done**
- **required verification** gates progress (less drift)
- outputs **verified_success** (measured accuracy)
- failures are labeled + backed by snapshot evidence in Studio (debuggable)

Task used: **WebBench 425** (`encyclopedia.com`): search **"Artificial Intelligence"** and extract related news/magazine/media references from the entry.

### What makes this demo reliable (guardrails)

Two real-world failure modes were hardened into deterministic guardrails:

- **empty query results**: clicking “Search” can land on `https://www.encyclopedia.com/gsearch?q=` (empty `q`).  
  The demo forces `goto(/gsearch?q=Artificial%20Intelligence)` so it doesn’t loop on an empty results page.
- **result clicks not navigating**: result-card clicks can be flaky.  
  The demo extracts a top result URL (bounded JS) and opens it via `goto(top_result_url)`.

### Verification semantics (what is required, when)

- **Always required**: `on_encyclopedia_domain`
- **Required only on an entry page** (not `/gsearch`):
  - `ai_title_visible`
  - `related_items_present`

This keeps the Studio timeline intuitive: navigation verifies domain; the entry page verifies task completion.

### Known-good traces (Studio run_ids)

- **PASS (all-green timeline)**: `18647a04-3a63-42bd-8eed-0ecc3ef71248`
- **FAIL (intentional, `DEMO_MODE=fail`)**: `2831dfdf-8450-438f-891f-36feb76099ec` (observed ~19 steps / 5 red verify steps due to retries)

## Install

From repo root (recommended: use your existing playground venv):

```bash
pip install sentienceapi langchain langchain-openai langgraph playwright python-dotenv moviepy pillow
playwright install chromium
```

## Run

Set required env vars:

```bash
export SENTIENCE_API_KEY="sk_pro_..."
export OPENAI_API_KEY="sk_..."
export OPENAI_MODEL="gpt-4o"
```

Choose demo mode:

- `DEMO_MODE=fail`: forces a **required** verification failure (great for Studio walkthrough)
- `DEMO_MODE=fix`: normal run (PASS if the agent succeeds)

```bash
export DEMO_MODE=fail
python sentience-sdk-playground/langchain-debugging/main.py
```

### Run the LangGraph demo

```bash
export DEMO_MODE=fail
python sentience-sdk-playground/langchain-debugging/langgraph_demo.py
```

## Notes

- `main.py` uses **DW task (WebBench ID 391)**: top news headline + time.
- `langgraph_demo.py` uses **encyclopedia.com task (WebBench ID 425)**: search AI + extract related references.
- Both use `use_api=True` and `show_overlay=True` for snapshots.
- If you want a Playwright recording, set `PLAYWRIGHT_RECORD_VIDEO=true`.
