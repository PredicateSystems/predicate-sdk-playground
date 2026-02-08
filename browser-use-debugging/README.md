# browser-use + SentienceDebugger (Playground Demo)

This demo shows how to attach **SentienceDebugger** as a *verification + trace sidecar* to a browser-use-driven browser session, with:
- **Per-step verification** (fail-fast on drift)
- **Task completion verification** (explicit “done” condition)
- **Consistent visuals**: per-step screenshots + optional element bbox annotation + token overlay video
- **Best-effort Playwright video artifact** (when recording is enabled in the underlying context)

## Why use Sentience with browser-use?

browser-use is great at **planning + acting**. Sentience adds the pieces you want around it for reliable evaluation/debugging:

- **Deterministic verification**: run machine-checkable assertions (URL/domain, element existence, etc.) and fail the run even if the LLM “says” it succeeded.
- **High-quality snapshots**: structured page snapshots (roles + element IDs + bboxes) + optional screenshot overlays to ground what happened.
- **Bounded JS introspection**: small safe signals via `evaluate_js` (title, flags, counters) instead of scraping with unbounded DOM dumps.
- **Trace + artifacts**: step timeline with `record_action(...)`, snapshots, screenshots, and stitched videos — easy to audit in Sentience Studio.
- **Stable backend abstraction**: `AgentRuntime` talks to a backend (browser-use CDP or Playwright). Your verification/snapshot pipeline stays consistent even if agent/page APIs vary across versions.
- **Separation of concerns**: browser-use drives the browser; Sentience acts as a verification + evidence sidecar.

## What you’ll get
- `artifacts/<timestamp>/trace.jsonl`
- `artifacts/<timestamp>/screenshots/*.png` (+ optional `*_annotated.png`)
- `artifacts/<timestamp>/video/demo.mp4` (stitched from screenshots)
- (optional) `artifacts/<timestamp>/video/playwright.mp4` if Playwright recording is enabled

## How it works (architecture)

- **browser-use owns the browser session** (`BrowserSession` + CDP).
- Sentience attaches via `BrowserUseAdapter(session)` to create a Sentience **CDP backend**.
- That backend is wrapped in `AgentRuntime`, and the sidecar is `SentienceDebugger(runtime=...)`.
- The demo takes snapshots, runs assertions, and emits trace + visual artifacts.

## Install

From repo root (recommended: use your existing playground venv):

```bash
pip install "sentienceapi[browser-use]" python-dotenv moviepy pillow
playwright install chromium
```

## Configure environment

This demo loads env vars from:

- `sentience-sdk-playground/.env`
- `./.env` (current working directory)

Minimum required:

- `SENTIENCE_API_KEY`
- `BROWSER_USE_API_KEY`

## Run

Set your Sentience API key (Pro tier) so traces upload and can be opened in Sentience Studio:

```bash
export SENTIENCE_API_KEY="sk_pro_..."
```

Choose a demo mode:

- `DEMO_MODE=fail`: forces a **required** verification failure (great for recording the Studio walkthrough)
- `DEMO_MODE=fix`: normal run (PASS if the agent succeeds)

```bash
export DEMO_MODE=fail
```

```bash
python sentience-sdk-playground/browser-use-debugging/main.py
```

## Demo modes: what “fail” vs “fix” means

At the end of the run (step index `99`), the script runs a required `task_complete` check:

- In **`DEMO_MODE=fix`**, it checks a reasonable completion condition for this DW task (e.g., still on `dw.com`).
- In **`DEMO_MODE=fail`**, it intentionally injects an always-false required assertion (`demo_intentional_failure`) so the Studio timeline clearly shows a failing verification step even if the agent produced an answer.

## How to set up a browser-use agent with SentienceDebugger + AgentRuntime

The core wiring is small. This is the pattern used by the demo:

```python
import os

from browser_use import BrowserProfile, BrowserSession

from sentience import SentienceDebugger, get_extension_dir
from sentience.agent_runtime import AgentRuntime
from sentience.backends import BrowserUseAdapter
from sentience.models import SnapshotOptions
from sentience.verification import any_of, exists, url_contains

# 1) Start browser-use with the Sentience extension loaded
profile = BrowserProfile(args=[f"--load-extension={get_extension_dir()}"], headless=False)
session = BrowserSession(browser_profile=profile)
await session.start()

# 2) Create a Sentience backend from the browser-use session (CDP)
adapter = BrowserUseAdapter(session)
backend = await adapter.create_backend()

# 3) Wrap in AgentRuntime + SentienceDebugger (verification sidecar)
runtime = AgentRuntime(
    backend=backend,
    tracer=None,  # optional (use create_tracer(...) in the demo)
    sentience_api_key=os.getenv("SENTIENCE_API_KEY"),
    snapshot_options=SnapshotOptions(use_api=True, limit=100, screenshot=True, show_overlay=True),
)
dbg = SentienceDebugger(runtime=runtime)

# 4) Use snapshots + checks around your agent steps
await dbg.snapshot(goal="verify:landing", use_api=True, limit=80, show_overlay=True)
await dbg.check(
    any_of(url_contains("dw.com"), exists("text~'DW'")),
    label="on_dw_domain",
    required=True,
).eventually(timeout_s=10)
```

## Recommended “vision vs verification” story to record

This demo is designed to show a common real-world failure mode:

- The **vision-based agent** finishes and “thinks” it succeeded (it returns without error, sometimes with an answer).
- Sentience then runs **deterministic verification** over snapshots and can prove the task is not actually complete.

## Open the run in Sentience Studio

After the script prints `run_id=...` (UUID) and exits, open Sentience Studio and find the run by that run_id.

In the Studio walkthrough, focus on:
- the **step timeline**
- the **recorded action strings** from `dbg.record_action(...)`
- the **failed required assertion** (in `DEMO_MODE=fail`)
- the **snapshot evidence** for why the assertion failed

## Notes
- This demo requires the Sentience extension (loaded via `--load-extension=...`) for snapshots.
- Playwright video recording must be enabled at **context creation time**. browser-use may or may not expose this; we still persist `page.video.path()` if available.

