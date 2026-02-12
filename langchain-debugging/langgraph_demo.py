#!/usr/bin/env python3
"""
LangGraph + Playwright + PredicateDebugger demo (verification sidecar).

READ task (WebBench 425, from webbench/docs/tasks.md line 134):
- On encyclopedia.com, search for "Artificial Intelligence"
- On the entry page, list any related news/magazine/media items referenced

This demo showcases:
- Less drift: step invariants + postconditions gate progress
- Better measured accuracy: report verified_success, not "agent returned"
- Debuggable failures: labeled checks + snapshot evidence + trace artifacts in Studio
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import uuid
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional, TypedDict

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:
    # Optional dependency: the demo can still run if env vars are set another way.
    def load_dotenv(*_args, **_kwargs):  # type: ignore
        return False


# Allow running from the monorepo without pip-installing the SDK.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SDK_PYTHON = _REPO_ROOT / "sdk-python"
if _SDK_PYTHON.exists():
    sys.path.insert(0, str(_SDK_PYTHON))

# Reuse shared demo utilities from browser-use-debugging/shared/
_SHARED = Path(__file__).resolve().parents[1] / "browser-use-debugging" / "shared"
if _SHARED.exists():
    sys.path.insert(0, str(_SHARED))

from predicate import AsyncPredicateBrowser, PredicateDebugger
from predicate.models import ScreenshotConfig, SnapshotOptions
from predicate.tracer_factory import create_tracer
from predicate.verification import custom, exists, url_contains

from token_tracker import TokenTracker  # type: ignore
from playwright_video import try_persist_page_video  # type: ignore
from video_generator_simple import create_demo_video  # type: ignore

from observe import make_compact_observation
from tools import (
    pick_click_target_from_snapshot,
    tool_click_at,
    tool_press,
    tool_scroll_by,
    tool_type_text,
)


START_URL = "https://www.encyclopedia.com"
TASK_ID = 425
QUERY = "Artificial Intelligence"
TASK = (
    'Search for "Artificial Intelligence" and list any related news or magazine articles '
    "or media referenced on the entry."
)

# We keep the same fail/fix semantics as other playground demos.
# NOTE: these are rebound inside main() after env loading.
DEMO_MODE = (os.getenv("DEMO_MODE") or "fix").strip().lower()  # "fail" | "fix"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
HEADLESS = (os.getenv("HEADLESS") or "false").strip().lower() in {"1", "true", "yes"}
RECORD_VIDEO = (os.getenv("PLAYWRIGHT_RECORD_VIDEO") or "false").strip().lower() in {"1", "true", "yes"}
SCREENSHOT_FORMAT = "jpeg"
SCREENSHOT_QUALITY = int(os.getenv("SCREENSHOT_QUALITY", "60"))


def _load_env_file(path: Path, *, override: bool = False) -> None:
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
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", (s or "").strip())
    return s[:80].strip("_") or "step"


async def _screenshot(page, path: Path) -> None:
    try:
        await page.screenshot(path=str(path), full_page=False)
    except Exception as e:
        print(f"[warn] screenshot failed: {e}", flush=True)


async def _wait_for_predicate(page, timeout_ms: int = 30000) -> None:
    try:
        await page.wait_for_function("() => window.sentience && window.sentience.snapshot", timeout=timeout_ms)
    except Exception as e:
        print(f"[warn] predicate injection check failed: {e}", flush=True)


async def _dismiss_modals_best_effort(page) -> None:
    """
    Best-effort dismissal for common cookie banners/modals.
    We keep it generic and low-risk.
    """
    try:
        await page.evaluate(
            """() => {
  const texts = ['Reject', 'Reject all', 'Accept', 'Accept all', 'Agree', 'I Agree', 'Continue'];
  const clickable = Array.from(document.querySelectorAll('button,[role="button"],input[type="button"],input[type="submit"],a'));
  const lower = (s) => (s || '').trim().toLowerCase();
  for (const el of clickable) {
    const t = lower(el.innerText || el.value || el.textContent || '');
    if (!t) continue;
    if (texts.some(x => lower(x) === t)) {
      el.click();
      return true;
    }
  }
  return false;
}"""
        )
    except Exception:
        return


class DemoState(dict):
    pass


class GraphState(TypedDict, total=False):
    # Core loop counters
    step_index: int
    replans: int
    iters: int
    started_at: float
    stagnation: int
    consecutive_snapshots: int

    # Task progress
    entry_opened: bool
    related_items: list[dict[str, Any]]
    ai_title_visible: bool
    top_result_url: Optional[str]

    # Observability / artifacts
    last_snapshot: Any
    observation: dict[str, Any]
    next_action: dict[str, Any]
    last_action: str
    last_action_meta: dict[str, Any]
    prev_url: str
    post_url: str
    last_step_failed: bool
    required_checks_failed: list[str]
    required_checks_passed: list[str]
    last_verify_outcomes: list[dict[str, Any]]


@dataclass
class StepResult:
    ok: bool
    label: str
    detail: str | None = None


async def main() -> None:
    # Load env vars from the playground .env (so PREDICATE_API_KEY is picked up).
    _load_env_file(_REPO_ROOT / "sentience-sdk-playground" / ".env", override=False)
    load_dotenv(dotenv_path=str(_REPO_ROOT / "sentience-sdk-playground" / ".env"), override=False)
    _load_env_file(Path.cwd() / ".env", override=False)
    load_dotenv(override=False)

    # Re-bind env-driven config after loading .env (avoid import-time stale values).
    global DEMO_MODE, OPENAI_MODEL, HEADLESS, RECORD_VIDEO
    DEMO_MODE = (os.getenv("DEMO_MODE") or "fix").strip().lower()  # "fail" | "fix"
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
    HEADLESS = (os.getenv("HEADLESS") or "false").strip().lower() in {"1", "true", "yes"}
    RECORD_VIDEO = (os.getenv("PLAYWRIGHT_RECORD_VIDEO") or "false").strip().lower() in {"1", "true", "yes"}

    predicate_api_key = os.getenv("PREDICATE_API_KEY")
    if not predicate_api_key:
        raise SystemExit("Missing PREDICATE_API_KEY in environment.")
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Missing OPENAI_API_KEY in environment.")

    # LangGraph + LangChain imports are optional until runtime.
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage
        from langchain_core.output_parsers import PydanticOutputParser
        from pydantic import BaseModel, Field

        from langgraph.graph import StateGraph, END
    except ImportError as e:
        raise SystemExit(
            "langgraph + langchain-openai are required.\n"
            "Install: pip install langgraph langchain langchain-openai\n"
            f"ImportError: {e}"
        ) from e

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_dir = Path(__file__).resolve().parent / "artifacts" / timestamp
    screenshots_dir = base_dir / "screenshots"
    video_dir = base_dir / "video"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)

    run_label = f"langgraph-encyclopedia-{timestamp}"
    run_id = str(uuid.uuid4())

    class _TraceLogger:
        def info(self, message: str) -> None:
            print(f"[trace] {message}", flush=True)

        def warning(self, message: str) -> None:
            print(f"[trace][warn] {message}", flush=True)

        def error(self, message: str) -> None:
            print(f"[trace][error] {message}", flush=True)

    tracer = create_tracer(
        api_key=predicate_api_key,
        run_id=run_id,
        upload_trace=True,
        goal=TASK,
        logger=_TraceLogger(),
        agent_type="sdk-playground/langchain-debugging/langgraph-demo",
        llm_model=OPENAI_MODEL,
        start_url=START_URL,
    )

    print(f"[demo] run_label={run_label}")
    print(f"[demo] run_id={run_id} (UUID; used by Predicate Studio)")
    print(f"[demo] DEMO_MODE={DEMO_MODE!r} (fail to force a failing trace)")
    print(f"[demo] OPENAI_MODEL={OPENAI_MODEL!r}")

    token_tracker = TokenTracker("langgraph-demo")

    browser = AsyncPredicateBrowser(
        api_key=predicate_api_key,
        headless=HEADLESS,
        user_data_dir=str(base_dir / "profile"),
        record_video_dir=str(video_dir) if RECORD_VIDEO else None,
        allowed_domains=["encyclopedia.com"],
    )
    await browser.start()
    # Bootstrap: start on homepage (task constraint) and let the graph use the search bar.
    await browser.goto(START_URL)
    page = browser.page
    if page is None:
        raise RuntimeError("PredicateBrowser did not create a page.")
    await _dismiss_modals_best_effort(page)
    await _wait_for_predicate(page, timeout_ms=30000)

    dbg = PredicateDebugger.attach(
        page=page,
        tracer=tracer,
        snapshot_options=SnapshotOptions(
            use_api=True,
            show_overlay=True,
            limit=120,
            screenshot=ScreenshotConfig(format=SCREENSHOT_FORMAT, quality=SCREENSHOT_QUALITY),
        ),
        predicate_api_key=predicate_api_key,
    )

    # ---- LangGraph model + schema ----
    class NextAction(BaseModel):
        action: Literal["snapshot", "click_match", "type_text", "press_enter", "scroll", "goto", "done"]
        query: Optional[str] = Field(
            default=None,
            description="For click_match: target text like 'Search', 'Artificial Intelligence', or a related item title fragment",
        )
        text: Optional[str] = Field(default=None, description="For type_text: text to type into focused field")
        scroll_dy: Optional[int] = Field(default=None, description="For scroll: positive=down, negative=up")
        url: Optional[str] = Field(default=None, description="For goto: URL (must be on encyclopedia.com)")
        note: Optional[str] = None

    parser = PydanticOutputParser(pydantic_object=NextAction)

    sys_msg = SystemMessage(
        content=(
            "You are a careful browser automation planner.\n"
            f"Your goal: use {START_URL} to search for '{QUERY}', open the encyclopedia entry page, and extract any related news/magazine/media items referenced on the entry.\n"
            "You may only propose one action at a time from the allowed actions.\n"
            "If you are unsure, take a snapshot.\n"
            "Prefer using the site's search bar.\n"
            "Typical sequence: click_match('Search') → type_text('Artificial Intelligence') → press_enter → click_match('Artificial Intelligence') (open entry).\n"
            "If you get lost, use goto('https://www.encyclopedia.com').\n"
            "If a cookie consent/modal blocks, take a snapshot then try clicking obvious dismiss/accept buttons.\n"
            "Return ONLY JSON that matches the schema.\n\n"
            f"{parser.get_format_instructions()}"
        )
    )

    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)

    # ---- Verification helpers ----
    async def verify_invariants(*, required: bool = True) -> list[StepResult]:
        results: list[StepResult] = []
        try:
            ok = await dbg.check(
                url_contains("encyclopedia.com"),
                label="on_encyclopedia_domain",
                required=required,
            ).eventually(timeout_s=10)
            results.append(StepResult(ok=bool(ok), label="on_encyclopedia_domain"))
        except Exception as e:
            # Only unexpected runtime errors should land here.
            results.append(StepResult(ok=False, label="on_encyclopedia_domain", detail=str(e)))
        return results

    # ---- Graph nodes ----
    MAX_REPLANS = int(os.getenv("MAX_REPLANS", "6"))
    MAX_ITERS = int(os.getenv("MAX_ITERS", "30"))  # total verify cycles
    MAX_WALL_TIME_S = float(os.getenv("MAX_WALL_TIME_S", "240"))  # hard stop

    async def await_with_timeout(label: str, coro, *, timeout_s: float):
        print(f"[demo] -> {label} (timeout={timeout_s}s)", flush=True)
        try:
            out = await asyncio.wait_for(coro, timeout=timeout_s)
            print(f"[demo] <- {label} (ok)", flush=True)
            return out
        except asyncio.TimeoutError:
            print(f"[demo] !! {label} timed out after {timeout_s}s", flush=True)
            raise

    async def node_observe(state: DemoState) -> DemoState:
        step_index = int(state.get("step_index", 0))
        async with dbg.step("observe: snapshot", step_index=step_index):
            await dbg.record_action("langgraph: snapshot()", url=page.url)
            snap = await await_with_timeout(
                "dbg.snapshot(observe)",
                dbg.snapshot(goal="observe:encyclopedia_state", use_api=True, limit=120, show_overlay=True),
                timeout_s=75,
            )
            try:
                n = len(getattr(snap, "elements", []) or [])
            except Exception:
                n = -1
            print(f"[demo] observe: url={getattr(snap, 'url', None)!r} elements={n}", flush=True)
            obs = make_compact_observation(snap, max_elements=35)
            top_n = len(obs.get("top_elements", []) or [])
            print(f"[demo] observe: top_elements={top_n}", flush=True)
            p = screenshots_dir / f"step_{step_index:02d}_{_safe_filename('observe')}.png"
            await _screenshot(page, p)
        return {
            "last_snapshot": snap,
            "observation": obs,
            "step_index": step_index + 1,
        }

    async def node_plan(state: GraphState) -> dict[str, Any]:
        obs = state.get("observation") or {}
        have_items = bool(state.get("related_items") or [])
        ai_title_visible = bool(state.get("ai_title_visible", False))
        replan_count = int(state.get("replans", 0))
        consecutive_snaps = int(state.get("consecutive_snapshots", 0))
        top_elems = obs.get("top_elements", []) or []
        url = str(obs.get("url") or "")
        top_result_url = str(state.get("top_result_url") or "").strip()
        if top_result_url in {START_URL, f"{START_URL}/"}:
            top_result_url = ""
        try:
            print(
                f"[demo] plan: obs_keys={list(obs.keys())} top_elems_len={len(top_elems)} consecutive_snaps={consecutive_snaps}",
                flush=True,
            )
        except Exception:
            pass

        prompt = (
            f"Task: {TASK}\n"
            f"Search query: {QUERY}\n"
            f"Current URL: {obs.get('url')}\n"
            f"AI title visible? {ai_title_visible}\n"
            f"Have extracted related items? {have_items}\n"
            f"Replans so far: {replan_count}/{MAX_REPLANS}\n"
            f"Iterations so far: {int(state.get('iters', 0))}/{MAX_ITERS}\n"
            f"Modal detected: {obs.get('modal_detected')}\n\n"
            "Top elements (ranked):\n"
            + json.dumps(obs.get("top_elements", [])[:25], ensure_ascii=False)
            + "\n\n"
            "Choose the next single action."
        )

        # Guardrail: avoid getting stuck in repeated snapshots (no state change).
        if consecutive_snaps >= 2:
            forced = {"action": "scroll", "query": None, "scroll_dy": 900, "note": "Guardrail: avoid repeated snapshot()"}
            print(f"[demo] plan (forced) -> {forced}", flush=True)
            return {"next_action": forced}

        # Guardrail (root-cause fix): ensure we actually submit the search query before trying to click results.
        # We observed runs getting stuck at /gsearch?q= (empty query) and then repeatedly clicking a non-existent result.
        if "/gsearch" in url and "q=" in url:
            try:
                parsed = urllib.parse.urlparse(url)
                qval = (urllib.parse.parse_qs(parsed.query).get("q", [""])[0] or "").strip()
            except Exception:
                qval = ""

            if not qval:
                # Deterministic: don't depend on focus/keyboard; go straight to the correct search URL.
                u = f"{START_URL}/gsearch?q={urllib.parse.quote(QUERY)}"
                forced_goto0 = {"action": "goto", "url": u, "note": "Guardrail: empty query on gsearch; navigate to populated query URL"}
                print(f"[demo] plan (forced) -> {forced_goto0}", flush=True)
                return {"next_action": forced_goto0}

            # If we ended up with an unexpected query, jump directly to the correct one deterministically.
            if qval.lower() != QUERY.lower():
                u = f"{START_URL}/gsearch?q={urllib.parse.quote(QUERY)}"
                forced_goto = {"action": "goto", "url": u, "note": "Guardrail: normalize search query via direct URL"}
                print(f"[demo] plan (forced) -> {forced_goto}", flush=True)
                return {"next_action": forced_goto}

            # If we have the correct query and we already discovered a top result URL, open it deterministically.
            # This avoids flaky coordinate clicks on result cards.
            if top_result_url and not bool(state.get("entry_opened", False)):
                forced_open = {"action": "goto", "url": top_result_url, "note": "Guardrail: open top search result via URL (avoid click flake)"}
                print(f"[demo] plan (forced) -> {forced_open}", flush=True)
                return {"next_action": forced_open}

        # If the observation is empty, try scrolling to surface content.
        if not top_elems:
            forced2 = {"action": "scroll", "query": None, "scroll_dy": 900, "note": "No elements observed; scroll to reveal content"}
            print(f"[demo] plan (forced) -> {forced2}", flush=True)
            return {"next_action": forced2}

        resp = await await_with_timeout("llm.plan()", llm.ainvoke([sys_msg, ("human", prompt)]), timeout_s=45)
        action = parser.parse(resp.content)
        next_action = action.model_dump()
        print(f"[demo] plan -> {next_action}", flush=True)
        return {"next_action": next_action}

    async def node_act(state: GraphState) -> dict[str, Any]:
        step_index = int(state.get("step_index", 0))
        action = state.get("next_action") or {}
        snap = state.get("last_snapshot")

        async with dbg.step(f"act: {action.get('action')}", step_index=step_index):
            await dbg.record_action(f"langgraph: act {action}", url=page.url)
            print(f"[demo] act: next_action={action}", flush=True)
            prev_url = page.url
            updates: dict[str, Any] = {"prev_url": prev_url}

            if action.get("action") == "snapshot":
                # no-op; observe node will snapshot next
                updates["last_action"] = "snapshot"
                updates["consecutive_snapshots"] = int(state.get("consecutive_snapshots", 0)) + 1
            elif action.get("action") == "scroll":
                dy = int(action.get("scroll_dy") or 900)
                last_action = await tool_scroll_by(page, dy)
                updates["last_action"] = last_action
                print(f"[demo] act: {last_action}", flush=True)
                updates["consecutive_snapshots"] = 0
            elif action.get("action") == "click_match":
                q = str(action.get("query") or "").strip()
                if not q:
                    updates["last_action"] = "click_match(no_query)"
                else:
                    target = pick_click_target_from_snapshot(snap, q) if snap is not None else None
                    if target is None:
                        # fallback: try a generic click on text in DOM via playwright locator
                        try:
                            await page.get_by_text(q, exact=False).first.click(timeout=4000)
                            updates["last_action"] = f"click_text({q})"
                        except Exception:
                            updates["last_action"] = f"click_match_not_found({q})"
                    else:
                        updates["last_action"] = await tool_click_at(page, target.x, target.y)
                        updates["last_action_meta"] = target.meta
                updates["consecutive_snapshots"] = 0
            elif action.get("action") == "type_text":
                t = str(action.get("text") or "")
                updates["last_action"] = await tool_type_text(page, t)
                updates["consecutive_snapshots"] = 0
            elif action.get("action") == "press_enter":
                updates["last_action"] = await tool_press(page, "Enter")
                updates["consecutive_snapshots"] = 0
            elif action.get("action") == "goto":
                u = str(action.get("url") or "").strip()
                if not u:
                    updates["last_action"] = "goto(no_url)"
                else:
                    try:
                        await page.goto(u, wait_until="domcontentloaded")
                        updates["last_action"] = f"goto({u})"
                    except Exception:
                        updates["last_action"] = f"goto_failed({u})"
                updates["consecutive_snapshots"] = 0
            elif action.get("action") == "done":
                updates["last_action"] = "done"
                updates["consecutive_snapshots"] = 0
            else:
                updates["last_action"] = f"unknown_action({action})"
                updates["consecutive_snapshots"] = 0

            await asyncio.sleep(1.0)
            await _dismiss_modals_best_effort(page)
            await await_with_timeout("_wait_for_predicate", _wait_for_predicate(page, timeout_ms=30000), timeout_s=35)
            updates["post_url"] = page.url
            try:
                print(f"[demo] act: last_action={updates.get('last_action')} url={updates.get('prev_url')} -> {updates.get('post_url')}", flush=True)
            except Exception:
                pass

            p = screenshots_dir / f"step_{step_index:02d}_{_safe_filename('act')}.png"
            await _screenshot(page, p)

        updates["step_index"] = step_index + 1
        return updates

    async def node_verify(state: GraphState) -> dict[str, Any]:
        step_index = int(state.get("step_index", 0))
        required_checks_failed: list[str] = list(state.get("required_checks_failed") or [])
        required_checks_passed: list[str] = list(state.get("required_checks_passed") or [])
        replans = int(state.get("replans", 0))

        async with dbg.step("verify", step_index=step_index):
            await dbg.record_action("langgraph: verify()", url=page.url)
            # Always snapshot before verifying (evidence).
            snap = await await_with_timeout(
                "dbg.snapshot(verify)",
                dbg.snapshot(goal="verify:post_action", use_api=True, limit=120, show_overlay=True),
                timeout_s=75,
            )
            state["last_snapshot"] = snap
            state["observation"] = make_compact_observation(snap, max_elements=35)
            obs = state.get("observation") or {}
            url = str(obs.get("url") or "")
            url_l = url.lower()
            is_search = "/gsearch" in url_l
            # "Entry page" is intentionally loose: we'll require an AI title signal + related refs.
            is_entryish = (not is_search) and ("encyclopedia.com" in url_l)

            outcomes: list[StepResult] = []
            last_action = str(state.get("last_action") or "")
            prev_url = str(state.get("prev_url") or "")
            post_url = str(state.get("post_url") or "")

            outcomes += await verify_invariants(required=True)

            # ---- Task-specific verification: entry title + related refs extraction ----
            ai_title_visible = False
            entry_required = bool(is_entryish)
            try:
                ok = await dbg.check(
                    exists("text~'Artificial Intelligence'"),
                    label="ai_title_visible",
                    required=entry_required,
                ).eventually(timeout_s=10)
                ai_title_visible = bool(ok)
                outcomes.append(StepResult(ok=bool(ok), label="ai_title_visible"))
            except Exception as e:
                outcomes.append(StepResult(ok=False, label="ai_title_visible", detail=str(e)))

            related_items: list[dict[str, Any]] = []
            if is_entryish:
                try:
                    related_items = await page.evaluate(
                        """() => {
  const q = (s) => (s || '').trim();
  const lower = (s) => q(s).toLowerCase();
  const isOk = (href, text) => {
    const h = lower(href);
    const t = lower(text);
    if (!href) return false;
    // Keep within site to satisfy task constraint.
    if (!(h.startsWith('/') || h.includes('encyclopedia.com'))) return false;
    // Related items signals.
    const kw = ['news', 'magazine', 'media', 'video', 'podcast'];
    return kw.some(k => h.includes(k) || t.includes(k));
  };

  const anchors = Array.from(document.querySelectorAll('a')).slice(0, 500);
  const out = [];
  const seen = new Set();
  for (const a of anchors) {
    const href = a.getAttribute('href') || '';
    const text = q(a.innerText || a.textContent || '');
    if (!isOk(href, text)) continue;
    let abs = href;
    try { abs = new URL(href, location.href).toString(); } catch (e) {}
    if (seen.has(abs)) continue;
    seen.add(abs);
    out.push({ title: text || abs, href: abs });
    if (out.length >= 12) break;
  }
  return out;
}"""
                    )
                    if not isinstance(related_items, list):
                        related_items = []
                except Exception:
                    related_items = []

            # DEMO_MODE=fail: intentionally break extraction even if present (for Studio walkthrough).
            if DEMO_MODE == "fail":
                related_items = []

            state["related_items"] = related_items
            state["ai_title_visible"] = ai_title_visible
            state["entry_opened"] = bool(is_entryish)

            # If we're on the search results page, deterministically discover the top result URL.
            top_result_url: str | None = None
            if is_search:
                try:
                    top_result_url = await page.evaluate(
                        """() => {
  const abs = (href) => {
    try { return new URL(href, location.href).toString(); } catch (e) { return href; }
  };
  const q = (s) => (s || '').trim();
  const lower = (s) => q(s).toLowerCase();
  const isBad = (u) => {
    const ul = lower(u);
    if (!ul) return true;
    if (ul.includes('/gsearch')) return true;
    if (ul === lower(location.origin) || ul === lower(location.origin + '/')) return true;
    return false;
  };

  const anchors = Array.from(document.querySelectorAll('a')).slice(0, 1200);
  const scored = [];
  for (const a of anchors) {
    const hrefRaw = a.getAttribute('href') || '';
    const text = q(a.innerText || a.textContent || '');
    const u = abs(hrefRaw);
    if (isBad(u)) continue;
    // Must stay on encyclopedia.com or be relative.
    try {
      const U = new URL(u, location.href);
      if (!U.hostname.endsWith('encyclopedia.com')) continue;
      if (!U.pathname || U.pathname === '/' || U.pathname.length < 2) continue;
    } catch (e) {
      continue;
    }

    const ul = lower(u);
    const tl = lower(text);
    let score = 1000;
    // Prefer an entry-like URL.
    if (ul.includes('artificial-intelligence')) score -= 500;
    if (tl.includes('artificial intelligence')) score -= 300;
    // Prefer result-title links (often longer text).
    if (text.length >= 10) score -= Math.min(100, text.length);
    scored.push({u, text, score});
  }
  scored.sort((a,b) => a.score - b.score);
  return scored.length ? scored[0].u : null;
}"""
                    )
                    if isinstance(top_result_url, str):
                        top_result_url = top_result_url.strip() or None
                except Exception:
                    top_result_url = None

            # Sanity: don't treat homepage as a "top result".
            if top_result_url in {START_URL, f"{START_URL}/"}:
                top_result_url = None

            state["top_result_url"] = top_result_url
            if is_search:
                try:
                    print(f"[demo] verify: top_result_url={top_result_url!r}", flush=True)
                except Exception:
                    pass

            def _items_ok(_ctx) -> bool:
                return bool(related_items)

            try:
                # NOTE: .once() is synchronous and returns bool (does not raise on assertion failure).
                ok = dbg.check(
                    custom(_items_ok, "related_items_present"),
                    label="related_items_present",
                    required=entry_required,
                ).once()
                outcomes.append(StepResult(ok=bool(ok), label="related_items_present"))
            except Exception as e:
                outcomes.append(StepResult(ok=False, label="related_items_present", detail=str(e)))

            # Bookkeeping for "measured accuracy"
            # Important: we want the FINAL summary to reflect the *latest* required-check state,
            # not "it failed at some earlier step". So we overwrite with the current verify outcomes.
            passed_now: list[str] = []
            failed_now: list[str] = []
            for o in outcomes:
                if not o.label:
                    continue
                if o.ok:
                    passed_now.append(o.label)
                else:
                    failed_now.append(o.label)

            # De-dupe while preserving order.
            def _dedupe(xs: list[str]) -> list[str]:
                seen: set[str] = set()
                out: list[str] = []
                for x in xs:
                    if x in seen:
                        continue
                    seen.add(x)
                    out.append(x)
                return out

            required_checks_passed = _dedupe(passed_now)
            required_checks_failed = _dedupe(failed_now)
            state["required_checks_failed"] = required_checks_failed
            state["required_checks_passed"] = required_checks_passed
            state["last_verify_outcomes"] = [o.__dict__ for o in outcomes]
            last_step_failed = any((o.ok is False) and o.label for o in outcomes)

            # Stagnation detection: if we are not making progress, force a replan.
            stagnation = int(state.get("stagnation", 0))
            url_unchanged = bool(prev_url) and bool(post_url) and (prev_url == post_url)
            if last_action.startswith("click_match_not_found") or (last_action == "done" and not (ai_title_visible and related_items)):
                stagnation += 1
            elif url_unchanged and not is_search and not is_entryish:
                stagnation += 1
            else:
                stagnation = 0
            state["stagnation"] = stagnation
            if stagnation >= 3:
                last_step_failed = True

            p = screenshots_dir / f"step_{step_index:02d}_{_safe_filename('verify')}.png"
            await _screenshot(page, p)

        if last_step_failed:
            replans += 1
        return {
            "last_snapshot": snap,
            "observation": make_compact_observation(snap, max_elements=35),
            "related_items": state.get("related_items", []),
            "ai_title_visible": bool(state.get("ai_title_visible", False)),
            "entry_opened": bool(state.get("entry_opened", False)),
            "top_result_url": state.get("top_result_url"),
            "required_checks_failed": required_checks_failed,
            "required_checks_passed": required_checks_passed,
            "last_verify_outcomes": [o.__dict__ for o in outcomes],
            "last_step_failed": last_step_failed,
            "stagnation": stagnation,
            "replans": replans,
            "step_index": step_index + 1,
            "iters": int(state.get("iters", 0)) + 1,
        }

    def route(state: GraphState) -> str:
        # Hard stop: wall time / max iterations
        started_at = float(state.get("started_at") or 0.0)
        if started_at and (time.monotonic() - started_at) > MAX_WALL_TIME_S:
            return "done"
        if int(state.get("iters", 0)) >= MAX_ITERS:
            return "done"

        # If task is verified, we're done.
        ai_title_visible = bool(state.get("ai_title_visible", False))
        related_items = state.get("related_items") or []
        if ai_title_visible and bool(related_items):
            return "done"

        replans = int(state.get("replans", 0))
        if replans >= MAX_REPLANS:
            return "done"

        # If the last verify step failed, replan.
        if bool(state.get("last_step_failed")):
            return "replan"
        return "continue"

    # ---- Build graph ----
    g = StateGraph(GraphState)
    g.add_node("observe", node_observe)
    g.add_node("plan", node_plan)
    g.add_node("act", node_act)
    g.add_node("verify", node_verify)

    g.set_entry_point("observe")
    g.add_edge("observe", "plan")
    g.add_edge("plan", "act")
    g.add_edge("act", "verify")
    g.add_conditional_edges("verify", route, {"continue": "observe", "replan": "observe", "done": END})
    app = g.compile()

    state: GraphState = {
        "step_index": 0,
        "replans": 0,
        "iters": 0,
        "started_at": time.monotonic(),
        "stagnation": 0,
        "consecutive_snapshots": 0,
        "entry_opened": False,
        "ai_title_visible": False,
        "related_items": [],
        "top_result_url": None,
        "required_checks_failed": [],
        "required_checks_passed": [],
    }

    try:
        final_state = await app.ainvoke(state)
        verified_success = bool(final_state.get("ai_title_visible", False)) and bool(final_state.get("related_items") or [])
        result = {
            "task_id": TASK_ID,
            "task": TASK,
            "openai_model": OPENAI_MODEL,
            "demo_mode": DEMO_MODE,
            "run_id": run_id,
            "verified_success": verified_success,
            "ai_title_visible": bool(final_state.get("ai_title_visible", False)),
            "entry_opened": bool(final_state.get("entry_opened", False)),
            "related_items": final_state.get("related_items") or [],
            "replans": int(final_state.get("replans", 0)),
            "required_checks_passed": final_state.get("required_checks_passed", []),
            "required_checks_failed": final_state.get("required_checks_failed", []),
        }
        (base_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"[demo] result: {json.dumps(result, indent=2)}", flush=True)
    finally:
        try:
            persisted = await try_persist_page_video(page, out_dir=video_dir, filename="playwright.mp4")
            if persisted:
                print(f"[video] persisted Playwright recording to: {persisted}")
        except Exception:
            pass

        try:
            out_mp4 = video_dir / "demo.mp4"
            create_demo_video(str(screenshots_dir), token_tracker.get_summary(), str(out_mp4))
        except Exception as e:
            print(f"[warn] video stitching failed: {e}", flush=True)

        try:
            tracer.close()
        except Exception:
            pass

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

