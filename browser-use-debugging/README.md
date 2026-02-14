# browser-use + Predicate deterministic verification (Playground Demo)

This demo shows how to use the **browser-use plugin** built into `sdk-python` (PyPI package: `predicatelabs`) to attach **deterministic verification** to a browser-use agent.

At a high level, `PredicateBrowserUsePlugin` wires up `AgentRuntime` + `PredicateDebugger` *as a verification + trace sidecar* around your Browser Use steps, with:
- **Per-step verification** (fail-fast on drift)
- **Task completion verification** (explicit “done” condition)
- **Consistent visuals**: per-step screenshots + optional element bbox annotation + token overlay video
- **Best-effort Playwright video artifact** (when recording is enabled in the underlying context)

## Why use Predicate with browser-use?

browser-use is great at **planning + acting**. Predicate adds the pieces you want around it for reliable evaluation/debugging—especially the common failure mode where:

- the agent returns `done` with a confident answer,
- but the browser state is not provably correct (drift), or the answer is not grounded (hallucination).

- **Deterministic verification**: run machine-checkable assertions (URL/domain, element existence, etc.) and fail the run even if the LLM “says” it succeeded.
- **High-quality snapshots**: structured page snapshots (roles + element IDs + bboxes) + optional screenshot overlays to ground what happened.
- **Bounded JS introspection**: small safe signals via `evaluate_js` (title, flags, counters) instead of scraping with unbounded DOM dumps.
- **Trace + artifacts**: step timeline with `record_action(...)`, snapshots, screenshots, and stitched videos — easy to audit in Predicate Studio.
- **Stable backend abstraction**: `AgentRuntime` talks to a backend (browser-use CDP or Playwright). Your verification/snapshot pipeline stays consistent even if agent/page APIs vary across versions.
- **Separation of concerns**: browser-use drives the browser; Predicate acts as a verification + evidence sidecar.

## Quick start (recommended): `PredicateBrowserUsePlugin`

This is the easiest way to add per-step snapshots + checks to either `agent.run()` (hooks supported) or `agent.step()` (manual wrap).

```python
import os

from browser_use import Agent, BrowserProfile, BrowserSession, ChatBrowserUse

from predicate import get_extension_dir
from predicate.integrations.browser_use import (
    PredicateBrowserUsePlugin,
    PredicateBrowserUsePluginConfig,
    StepCheckSpec,
)
from predicate.models import SnapshotOptions
from predicate.verification import any_of, exists, url_contains

# 1) Start browser-use with the Predicate extension loaded (required for snapshots).
profile = BrowserProfile(args=[f"--load-extension={get_extension_dir()}"], headless=False)
session = BrowserSession(browser_profile=profile)
await session.start()

# 2) Bind the Predicate browser-use plugin to the session.
plugin = PredicateBrowserUsePlugin(
    config=PredicateBrowserUsePluginConfig(
        predicate_api_key=os.getenv("PREDICATE_API_KEY"),
        use_api=True,
        snapshot_options=SnapshotOptions(
            use_api=True,
            limit=120,
            screenshot=True,
            show_overlay=True,
            goal="browser-use-demo",
            predicate_api_key=os.getenv("PREDICATE_API_KEY"),
        ),
        auto_snapshot_each_step=True,
        auto_checks_each_step=True,
        auto_checks=[
            StepCheckSpec(
                predicate=any_of(url_contains("dw.com"), exists("text~'DW'")),
                label="on_dw_domain",
                required=True,
                eventually=True,
                timeout_s=10.0,
            )
        ],
        on_failure="raise",  # fail fast when a required check fails
    )
)
await plugin.bind(browser_session=session)

# 3) Run your normal browser-use agent.
agent = Agent(
    task="Visit dw.com and verify we’re on the DW homepage.",
    llm=ChatBrowserUse(api_key=os.getenv("BROWSER_USE_API_KEY")),
    browser_session=session,
)

# Preferred: `agent.run()` supports step hooks in browser-use.
result = await agent.run(on_step_start=plugin.on_step_start, on_step_end=plugin.on_step_end)
print("Final:", result)

# If you use `agent.step()` loops, wrap each step:
# step_result = await plugin.wrap_step(agent, agent.step)
```

## What you’ll get
- `artifacts/<timestamp>/trace.jsonl`
- `artifacts/<timestamp>/screenshots/*.png` (+ optional `*_annotated.png`)
- `artifacts/<timestamp>/video/demo.mp4` (stitched from screenshots)
- (optional) `artifacts/<timestamp>/video/playwright.mp4` if Playwright recording is enabled

## How it works (architecture)

- **browser-use owns the browser session** (`BrowserSession` + CDP).
- `PredicateBrowserUsePlugin.bind(...)` attaches via `BrowserUseAdapter(session)` to create a Predicate **CDP backend**.
- That backend is wrapped in `AgentRuntime`, and the sidecar is `PredicateDebugger(runtime=...)`.
- The demo takes snapshots, runs assertions, and emits trace + visual artifacts.

## Install

From repo root (recommended: use your existing playground venv):

```bash
pip install "predicatelabs[browser-use]" python-dotenv moviepy pillow
playwright install chromium
```

## Configure environment

This demo loads env vars from:

- `sentience-sdk-playground/.env`
- `./.env` (current working directory)

Minimum required:

- `PREDICATE_API_KEY`
- `BROWSER_USE_API_KEY`

## Run

Set your Sentience API key (Pro tier) so traces upload and can be opened in Predicate Studio:

```bash
export PREDICATE_API_KEY="sk_pro_..."
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

## How to set up a browser-use agent with PredicateDebugger + AgentRuntime

The core wiring is small. This is the underlying pattern used by the plugin (and the demo). If you prefer to wire things manually (without the plugin), this is what it looks like:

```python
import os

from browser_use import BrowserProfile, BrowserSession

from predicate import PredicateDebugger, get_extension_dir
from predicate.agent_runtime import AgentRuntime
from predicate.backends import BrowserUseAdapter
from predicate.models import SnapshotOptions
from predicate.verification import any_of, exists, url_contains

# 1) Start browser-use with the Predicate extension loaded
profile = BrowserProfile(args=[f"--load-extension={get_extension_dir()}"], headless=False)
session = BrowserSession(browser_profile=profile)
await session.start()

# 2) Create a Sentience backend from the browser-use session (CDP)
adapter = BrowserUseAdapter(session)
backend = await adapter.create_backend()

# 3) Wrap in AgentRuntime + PredicateDebugger (verification sidecar)
runtime = AgentRuntime(
    backend=backend,
    tracer=None,  # optional (use create_tracer(...) in the demo)
    predicate_api_key=os.getenv("PREDICATE_API_KEY"),
    snapshot_options=SnapshotOptions(use_api=True, limit=100, screenshot=True, show_overlay=True),
)
dbg = PredicateDebugger(runtime=runtime)

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

## Open the run in Predicate Studio

After the script prints `run_id=...` (UUID) and exits, open Predicate Studio and find the run by that run_id.

In the Studio walkthrough, focus on:
- the **step timeline**
- the **recorded action strings** from `dbg.record_action(...)`
- the **failed required assertion** (in `DEMO_MODE=fail`)
- the **snapshot evidence** for why the assertion failed

## Notes
- This demo requires the Predicate extension (loaded via `--load-extension=...`) for snapshots.
- Playwright video recording must be enabled at **context creation time**. browser-use may or may not expose this; we still persist `page.video.path()` if available.

