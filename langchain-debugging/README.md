# LangChain + SentienceDebugger (Playground Demo)

This demo shows how to attach **SentienceDebugger** to a **SentienceBrowser**
page while a **LangChain agent** drives the browser.

You get:
- per-step **verification** in Sentience Studio
- screenshots + optional overlay annotations
- optional Playwright video artifact

## Install

From repo root (recommended: use your existing playground venv):

```bash
pip install sentienceapi langchain langchain-openai playwright python-dotenv moviepy pillow
playwright install chromium
```

## Run

Set required env vars:

```bash
export SENTIENCE_API_KEY="sk_pro_..."
export OPENAI_API_KEY="sk_..."
```

Choose demo mode:

- `DEMO_MODE=fail`: forces a **required** verification failure (great for Studio walkthrough)
- `DEMO_MODE=fix`: normal run (PASS if the agent succeeds)

```bash
export DEMO_MODE=fail
python sentience-sdk-playground/langchain-debugging/main.py
```

## Notes

- Uses **DW task (WebBench ID 391)**: top news headline + time.
- Uses `use_api=True` and `show_overlay=True` for all snapshots.
- If you want a Playwright recording, set `PLAYWRIGHT_RECORD_VIDEO=true`.
