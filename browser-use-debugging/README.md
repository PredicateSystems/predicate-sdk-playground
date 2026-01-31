# browser-use + SentienceDebugger (Playground Demo)

This demo shows how to attach **SentienceDebugger** as a *verification + trace sidecar* to a browser-use-driven browser session, with:
- **Per-step verification** (fail-fast on drift)
- **Task completion verification** (explicit “done” condition)
- **Consistent visuals**: per-step screenshots + optional element bbox annotation + token overlay video
- **Best-effort Playwright video artifact** (when recording is enabled in the underlying context)

## What you’ll get
- `artifacts/<timestamp>/trace.jsonl`
- `artifacts/<timestamp>/screenshots/*.png` (+ optional `*_annotated.png`)
- `artifacts/<timestamp>/video/demo.mp4` (stitched from screenshots)
- (optional) `artifacts/<timestamp>/video/playwright.mp4` if Playwright recording is enabled

## Install

From repo root (recommended: use your existing playground venv):

```bash
pip install "sentienceapi[browser-use]" python-dotenv moviepy pillow
playwright install chromium
```

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

## Recommended “vision vs verification” story to record

This demo is designed to show a common real-world failure mode:

- The **vision-based agent** finishes and “thinks” it succeeded (it returns without error, sometimes with an answer).
- Sentience then runs **deterministic verification** over snapshots and can prove the task is not actually complete.

In `DEMO_MODE=fail`, the demo first tries a **strict** completion assertion (often catches drift or hallucinated extraction).
If it unexpectedly passes, it will fall back to a forced failure so you can still record the Studio walkthrough.

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

