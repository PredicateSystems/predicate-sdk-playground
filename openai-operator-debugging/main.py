#!/usr/bin/env python3
"""
OpenAI computer-use + PredicateDebugger demo (deterministic verification sidecar).

Modeled after: sentience-sdk-playground/browser-use-debugging

High-level:
- OpenAI "computer use" proposes UI actions (click/type/scroll/wait/...).
- We execute actions in a local Playwright browser session.
- Predicate attaches to the same Playwright Page and enforces:
  - per-step required checks (stay on-domain)
  - task proof-of-done (top 3 featured Esquire headlines)
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import sys
import traceback
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:

    def load_dotenv(*_args, **_kwargs):  # type: ignore
        return False


# Allow running from the monorepo without pip-installing the SDK.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SDK_PYTHON = _REPO_ROOT / "sdk-python"
if _SDK_PYTHON.exists():
    sys.path.insert(0, str(_SDK_PYTHON))

# Reuse shared helpers (artifacts/video) from browser-use-debugging if present.
_BROWSER_USE_DEMO = _REPO_ROOT / "sentience-sdk-playground" / "browser-use-debugging"
if _BROWSER_USE_DEMO.exists():
    sys.path.insert(0, str(_BROWSER_USE_DEMO))

from openai import OpenAI  # type: ignore

from predicate import AsyncPredicateBrowser, PredicateDebugger
from predicate.agent_runtime import AgentRuntime
from predicate.models import ScreenshotConfig, SnapshotOptions
from predicate.tracer_factory import create_tracer
from predicate.verification import custom, url_matches


TASK_ID = 449
START_URL = "https://www.esquire.com"
TASK_TEXT = (
    "Navigate to the Esquire homepage and list the headlines of the top 3 featured articles.\n"
    "Only use http://esquire.com to achieve the task. Don't go to any other site."
)


def _load_env_file(path: Path, *, override: bool = False) -> None:
    """Minimal .env loader (no hard dependency on python-dotenv)."""
    try:
        if not path.exists() or not path.is_file():
            return
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            key = k.strip()
            if not key:
                continue
            val = v.strip().strip("'").strip('"')
            if not override and os.environ.get(key) is not None:
                continue
            os.environ[key] = val
    except Exception:
        return


def _safe_filename(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", s.strip())
    return s[:80].strip("_") or "step"


def _host(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).hostname or ""
    except Exception:
        return ""


def _is_esquire(url: str) -> bool:
    h = _host(url).lower()
    return h == "esquire.com" or h.endswith(".esquire.com")


def _data_url_from_snapshot(snap) -> str:
    """
    Convert Predicate Snapshot.screenshot (base64) to data URL.
    """
    screenshot = getattr(snap, "screenshot", None)
    fmt = getattr(snap, "screenshot_format", None)
    if not screenshot:
        raise RuntimeError("snapshot did not include screenshot (set screenshot=True)")

    # Predicate snapshots commonly store screenshots as a data URL already.
    s = str(screenshot)
    if s.startswith("data:image/"):
        return s

    # Otherwise assume raw base64 payload and build a data URL.
    b64 = s
    # Some snapshot providers omit screenshot_format. OpenAI validates that the
    # base64 payload matches the declared mime type, so we must be correct.
    if not fmt:
        try:
            head = base64.b64decode(b64[:256] + "===")[:16]
        except Exception:
            head = b""
        if head.startswith(b"\x89PNG\r\n\x1a\n"):
            fmt = "png"
        elif head.startswith(b"\xff\xd8\xff"):
            fmt = "jpeg"
        elif head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
            fmt = "gif"
        elif head.startswith(b"RIFF") and b"WEBP" in head:
            fmt = "webp"
        else:
            # Fall back to jpeg (most common for our snapshots) to avoid sending an
            # incorrect image/png label with jpeg bytes.
            fmt = "jpeg"

    return f"data:image/{fmt};base64,{b64}"

def _write_snapshot_image(snap: Any, path: Path) -> None:
    """
    Persist Snapshot.screenshot (base64) to disk.
    """
    screenshot = getattr(snap, "screenshot", None)
    if not screenshot:
        return
    try:
        s = str(screenshot)
        if s.startswith("data:image/"):
            # data:image/<fmt>;base64,<payload>
            if "base64," in s:
                s = s.split("base64,", 1)[1]
            else:
                return
        raw = base64.b64decode(s)
        path.write_bytes(raw)
    except Exception:
        return


def _to_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()  # type: ignore[no-any-return]
    if hasattr(obj, "dict"):
        return obj.dict()  # type: ignore[no-any-return]
    raise TypeError(f"unsupported response object: {type(obj)}")


def _extract_top_featured_headlines(snapshot: Any, k: int = 3) -> list[str]:
    """
    Deterministic best-effort extraction using Predicate structured snapshot.

    Heuristic:
    - Prefer main/dominant group elements.
    - Prefer role=heading/link with non-trivial text.
    - Sort by document Y (or bbox y) then by importance (desc).
    - De-dupe case-insensitively.
    """
    els = list(getattr(snapshot, "elements", []) or [])
    scored: list[tuple[float, int, str]] = []
    for e in els:
        role = str(getattr(e, "role", "") or "").lower()
        if role not in ("heading", "link"):
            continue
        text = (getattr(e, "text", None) or getattr(e, "name", None) or "").strip()
        if len(text) < 15:
            continue
        # Prefer dominant group / main region when available.
        in_dom = getattr(e, "in_dominant_group", None)
        if in_dom is False:
            continue
        layout = getattr(e, "layout", None)
        region = getattr(layout, "region", None) if layout is not None else None
        if region is not None and str(region) not in ("main",):
            continue

        doc_y = getattr(e, "doc_y", None)
        if doc_y is None:
            bbox = getattr(e, "bbox", None)
            doc_y = float(getattr(bbox, "y", 999999.0) or 999999.0) if bbox is not None else 999999.0
        imp = int(getattr(e, "importance", 0) or 0)
        scored.append((float(doc_y), -imp, text))

    scored.sort(key=lambda t: (t[0], t[1]))
    out: list[str] = []
    seen: set[str] = set()
    for _y, _imp, t in scored:
        key = re.sub(r"\s+", " ", t).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(t.strip())
        if len(out) >= k:
            break
    return out


@dataclass
class CUAConfig:
    openai_model: str
    computer_tool_type: str
    max_steps: int
    demo_mode: str


def _load_config() -> CUAConfig:
    # OpenAI: dedicated model for computer use (GPT-4.1 does NOT support computer use).
    openai_model = (os.getenv("OPENAI_MODEL") or "computer-use-preview").strip()
    # Tool type varies by SDK/docs; OpenAI's official sample app uses "computer-preview".
    computer_tool_type = (os.getenv("OPENAI_COMPUTER_TOOL_TYPE") or "computer-preview").strip()
    max_steps = int((os.getenv("MAX_STEPS") or "30").strip())
    demo_mode = (os.getenv("DEMO_MODE") or "fix").strip().lower()
    return CUAConfig(
        openai_model=openai_model,
        computer_tool_type=computer_tool_type,
        max_steps=max_steps,
        demo_mode=demo_mode,
    )


async def _execute_action(page: Any, action: dict[str, Any]) -> None:
    """
    Execute a computer-use action on a Playwright Page.

    Supports a minimal subset needed for most web tasks.
    """
    t = str(action.get("type") or "")
    if t == "click":
        x = float(action.get("x"))
        y = float(action.get("y"))
        button = str(action.get("button") or "left")
        if button == "wheel":
            button = "middle"
        await page.mouse.click(x, y, button=button)
        return

    if t == "double_click":
        x = float(action.get("x"))
        y = float(action.get("y"))
        await page.mouse.dblclick(x, y)
        return

    if t == "type":
        text = str(action.get("text") or "")
        # Optional typing delay for stability (ms per char)
        await page.keyboard.type(text, delay=10)
        return

    if t == "keypress":
        keys = action.get("keys")
        if isinstance(keys, list):
            for k in keys:
                await page.keyboard.press(str(k))
        else:
            await page.keyboard.press(str(keys))
        return

    if t == "scroll":
        # Docs vary; best-effort support both "scroll_y" and "delta_y".
        dy = action.get("scroll_y", None)
        if dy is None:
            dy = action.get("delta_y", None)
        if dy is None:
            dy = action.get("y", 0)
        await page.mouse.wheel(0, float(dy))
        return

    if t == "wait":
        ms = float(action.get("ms") or 1000)
        await page.wait_for_timeout(ms)
        return

    if t == "hover":
        x = float(action.get("x"))
        y = float(action.get("y"))
        await page.mouse.move(x, y)
        return

    if t == "drag":
        path = action.get("path") or []
        if not isinstance(path, list) or len(path) < 2:
            raise ValueError("drag requires path with >=2 points")
        x0 = float(path[0]["x"])
        y0 = float(path[0]["y"])
        await page.mouse.move(x0, y0)
        await page.mouse.down()
        for pt in path[1:]:
            await page.mouse.move(float(pt["x"]), float(pt["y"]))
        await page.mouse.up()
        return

    raise NotImplementedError(f"unsupported action type: {t!r} (action={action})")


async def main() -> None:
    # Load env vars from the playground .env (so OPENAI_API_KEY is picked up even
    # when running from the monorepo root).
    _load_env_file(_REPO_ROOT / "sentience-sdk-playground" / ".env", override=True)
    load_dotenv(dotenv_path=str(_REPO_ROOT / "sentience-sdk-playground" / ".env"), override=True)
    _load_env_file(Path.cwd() / ".env", override=True)
    load_dotenv(override=True)

    cfg = _load_config()

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise SystemExit("Missing OPENAI_API_KEY in environment.")

    predicate_api_key = os.getenv("PREDICATE_API_KEY")

    # Fail fast on incompatible models (common when OPENAI_MODEL is set globally in .env).
    if not cfg.openai_model.startswith("computer-use-preview"):
        raise SystemExit(
            "OPENAI_MODEL must be 'computer-use-preview' (computer use tool is not supported on this model).\n"
            f"Current OPENAI_MODEL={cfg.openai_model!r}\n"
            "Fix: set `OPENAI_MODEL=computer-use-preview` (or unset OPENAI_MODEL).\n"
            "Note: GPT-4.1 and gpt-4o do not support the computer use tool."
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_dir = Path(__file__).resolve().parent / "artifacts" / timestamp
    screenshots_dir = base_dir / "screenshots"
    base_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    run_label = f"openai-operator-debug-{timestamp}"
    run_id = str(uuid.uuid4())
    tracer = create_tracer(
        api_key=predicate_api_key,
        run_id=run_id,
        upload_trace=bool(predicate_api_key),
        goal=f"[demo] {run_label} | WebBench {TASK_ID} (Esquire featured headlines)",
        agent_type="sdk-playground/openai-operator-debugging",
        llm_model=cfg.openai_model,
        start_url=START_URL,
    )

    print(f"[demo] run_label={run_label}")
    print(f"[demo] run_id={run_id} (UUID; used by Predicate Studio)")
    print(f"[demo] OPENAI_MODEL={cfg.openai_model!r}")
    print(f"[demo] OPENAI_COMPUTER_TOOL_TYPE={cfg.computer_tool_type!r}")
    print(f"[demo] DEMO_MODE={cfg.demo_mode!r}")

    client = OpenAI(api_key=openai_key)

    try:
        # ---------------------------------------------------------------------
        # Start Predicate-managed browser (extension loaded)
        # ---------------------------------------------------------------------
        async with AsyncPredicateBrowser(
            headless=False,
            allowed_domains=["esquire.com", "www.esquire.com"],
        ) as browser:
            page = browser.page
            assert page is not None

            runtime = AgentRuntime.from_playwright_page(
                page=page,
                tracer=tracer,
                snapshot_options=SnapshotOptions(
                    limit=80,
                    screenshot=ScreenshotConfig(format="jpeg", quality=60),
                    use_api=True if predicate_api_key else None,
                ),
                predicate_api_key=predicate_api_key,
            )
            dbg = PredicateDebugger(runtime=runtime)

            # Deterministic navigation (so we start on-domain before handing to CUA).
            async with dbg.step("goto:esquire_homepage"):
                await browser.goto(START_URL)
                snap0 = await dbg.snapshot(goal="landing")
                _write_snapshot_image(snap0, screenshots_dir / "step_000_landing.jpeg")
                await dbg.check(
                    url_matches(r"^https?://([a-z0-9-]+\.)*esquire\.com/"),
                    label="on_esquire_domain",
                    required=True,
                ).eventually(timeout_s=15)

            # Build CUA tool spec (OpenAI sample app naming).
            tools = [
                {
                    "type": cfg.computer_tool_type,
                    "display_width": 1024,
                    "display_height": 768,
                    "environment": "browser",
                }
            ]

            # Conversation items (OpenAI sample app pattern).
            items: list[dict[str, Any]] = [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": TASK_TEXT},
                        {"type": "input_image", "image_url": _data_url_from_snapshot(snap0)},
                    ],
                }
            ]

            for i in range(cfg.max_steps):
                resp = client.responses.create(
                    model=cfg.openai_model,
                    input=items,
                    tools=tools,
                    truncation="auto",
                )
                rd = _to_dict(resp)
                out_items = list(rd.get("output") or [])
                if not out_items:
                    raise RuntimeError(f"OpenAI response missing output: {rd}")

                items += out_items

                had_computer_call = False
                # Process each output item; executing computer calls adds computer_call_output items.
                for it in out_items:
                    it = dict(it)
                    if it.get("type") == "message":
                        try:
                            content = it.get("content") or []
                            if content and content[0].get("type") == "output_text":
                                print(content[0].get("text") or "")
                        except Exception:
                            pass
                        continue

                    if it.get("type") == "computer_call":
                        had_computer_call = True
                        action = it.get("action") or {}
                        action_type = str(action.get("type") or "")
                        action_args = {k: v for k, v in action.items() if k != "type"}
                        call_id = it.get("call_id")
                        pending_checks = it.get("pending_safety_checks", []) or []

                        async with dbg.step(f"cua:{action_type}"):
                            await dbg.record_action(
                                f"{action_type}({action_args})", url=page.url
                            )
                            await _execute_action(page, action)
                            snap = await dbg.snapshot(goal=f"after_step_{i}")
                            _write_snapshot_image(
                                snap,
                                screenshots_dir
                                / f"step_{i+1:03d}_{_safe_filename(action_type)}.jpeg",
                            )
                            await dbg.check(
                                url_matches(r"^https?://([a-z0-9-]+\.)*esquire\.com/"),
                                label="still_on_esquire_domain",
                                required=True,
                            ).eventually(timeout_s=15)
                            # Hard stop if we drifted (defense-in-depth)
                            if not _is_esquire(page.url):
                                raise RuntimeError(f"domain drift: {page.url}")

                        # Feed screenshot back to OpenAI as tool output
                        items.append(
                            {
                                "type": "computer_call_output",
                                "call_id": call_id,
                                "acknowledged_safety_checks": pending_checks,
                                "output": {
                                    "type": "input_image",
                                    "image_url": _data_url_from_snapshot(snap),
                                    "current_url": page.url,
                                },
                            }
                        )

                # Stop if the model produced no computer action requests this turn.
                if not had_computer_call:
                    break

            # Final deterministic extraction + proof-of-done
            async with dbg.step("verify:task_complete"):
                final_snap = await dbg.snapshot(goal="final", screenshot=False)
                headlines = _extract_top_featured_headlines(final_snap, k=3)
                print("\n[demo] extracted_headlines:")
                for h in headlines:
                    print(f"- {h}")

                def _has_3(ctx) -> bool:
                    snap = ctx.snapshot
                    if snap is None:
                        return False
                    return len(_extract_top_featured_headlines(snap, k=3)) >= 3

                pred = custom(_has_3, label="extracted_3_headlines")
                if cfg.demo_mode == "fail":
                    pred = custom(lambda _ctx: False, label="demo_intentional_failure")

                ok = runtime.assert_done(pred, label="task_complete")
                if not ok:
                    raise RuntimeError("task_complete verification failed")

            # Persist artifacts
            result = {
                "task_id": TASK_ID,
                "start_url": START_URL,
                "openai_model": cfg.openai_model,
                "computer_tool_type": cfg.computer_tool_type,
                "run_id": run_id,
                "demo_mode": cfg.demo_mode,
                "final_url": page.url,
                "headlines": headlines,
            }
            (base_dir / "result.json").write_text(
                json.dumps(result, indent=2), encoding="utf-8"
            )
            print(f"\n[demo] wrote: {base_dir/'result.json'}")
    finally:
        try:
            tracer.close()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print("\n[demo] ERROR:", e)
        traceback.print_exc()
        raise

