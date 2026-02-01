#!/usr/bin/env python3
"""
LangChain + Playwright + SentienceDebugger demo (verification sidecar).

This demo shows how to:
- Use a LangChain agent to drive a Playwright browser
- Attach SentienceDebugger to the Playwright page
- Produce consistent screenshots + optional video artifacts
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

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

from sentience import SentienceDebugger
from sentience.browser import AsyncSentienceBrowser
from sentience.models import SnapshotOptions
from sentience.tracer_factory import create_tracer
from sentience.verification import any_of, custom, exists, url_contains

from bbox_visualizer import visualize_api_elements
from playwright_video import try_persist_page_video
from token_tracker import TokenTracker

try:
    from video_generator_simple import create_demo_video
except ImportError:
    create_demo_video = None


START_URL = "https://www.dw.com"
TASK_QUESTION = "Visit DW.com and list the headline and publication time of the top news article."
DEMO_MODE = (os.getenv("DEMO_MODE") or "fix").strip().lower()  # "fail" | "fix"
DEMO_FAILURE = (os.getenv("DEMO_FAILURE") or "").strip().lower()  # "headline" | "time" | ""
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
HEADLESS = (os.getenv("HEADLESS") or "false").strip().lower() in {"1", "true", "yes"}
RECORD_VIDEO = (os.getenv("PLAYWRIGHT_RECORD_VIDEO") or "false").strip().lower() in {
    "1",
    "true",
    "yes",
}
SENTIENCE_BROWSER_EXECUTABLE_PATH = os.getenv("SENTIENCE_BROWSER_EXECUTABLE_PATH")


def _load_env_file(path: Path, *, override: bool = False) -> None:
    """
    Minimal .env loader (so we don't hard-depend on python-dotenv).
    """
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


def _parse_extraction(text: str) -> tuple[str, str]:
    headline = ""
    time_text = ""
    for raw in (text or "").splitlines():
        line = raw.strip()
        if line.lower().startswith("headline:"):
            headline = line.split(":", 1)[1].strip()
        elif line.lower().startswith("time:"):
            time_text = line.split(":", 1)[1].strip()
    return headline, time_text


def _stealth_init_script() -> str:
    return """
(() => {
  try {
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
  } catch (e) {}
  try {
    window.chrome = window.chrome || {};
    window.chrome.runtime = window.chrome.runtime || {};
  } catch (e) {}
  try {
    const originalQuery = navigator.permissions && navigator.permissions.query;
    if (originalQuery) {
      navigator.permissions.query = (parameters) => (
        parameters && parameters.name === 'notifications'
          ? Promise.resolve({ state: Notification.permission })
          : originalQuery(parameters)
      );
    }
  } catch (e) {}
})();
""".strip()


async def _screenshot(page, path: Path) -> None:
    try:
        await page.screenshot(path=str(path), full_page=False)
    except Exception as e:
        print(f"[warn] screenshot failed: {e}")


async def _wait_for_sentience(page, timeout_ms: int = 30000) -> None:
    try:
        await page.wait_for_function(
            "() => window.sentience && window.sentience.snapshot", timeout=timeout_ms
        )
    except Exception as e:
        print(f"[warn] sentience injection check failed: {e}")


async def _dismiss_dw_modal(page) -> None:
    """
    Best-effort dismissal for DW consent modal (Agree/Reject).
    """
    try:
        await page.evaluate(
            """() => {
  const texts = ['Reject', 'Reject all', 'Agree', 'Accept', 'Accept all', 'I Agree'];
  const buttons = Array.from(document.querySelectorAll('button, [role="button"], input[type="button"], input[type="submit"]'));
  const match = (el) => {
    const t = (el.innerText || el.value || '').trim();
    return texts.some((x) => t.toLowerCase() === x.toLowerCase());
  };
  const target = buttons.find(match);
  if (target) {
    target.click();
    return true;
  }
  return false;
}"""
        )
    except Exception:
        return


async def main() -> None:
    # Load env vars from the playground .env (so SENTIENCE_API_KEY is picked up).
    _load_env_file(_REPO_ROOT / "sentience-sdk-playground" / ".env", override=False)
    load_dotenv(dotenv_path=str(_REPO_ROOT / "sentience-sdk-playground" / ".env"), override=False)
    _load_env_file(Path.cwd() / ".env", override=False)
    load_dotenv(override=False)

    sentience_api_key = os.getenv("SENTIENCE_API_KEY")
    if not sentience_api_key:
        raise SystemExit("Missing SENTIENCE_API_KEY in environment.")
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Missing OPENAI_API_KEY in environment.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_dir = Path(__file__).resolve().parent / "artifacts" / timestamp
    screenshots_dir = base_dir / "screenshots"
    video_dir = base_dir / "video"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)

    run_label = f"langchain-debug-{timestamp}"
    run_id = str(uuid.uuid4())
    tracer = create_tracer(
        api_key=sentience_api_key,
        run_id=run_id,
        upload_trace=False,
        goal=f"[demo] {run_label} | DW.com: top news headline + time",
        agent_type="sdk-playground/langchain-debugging",
        llm_model=OPENAI_MODEL,
        start_url=START_URL,
    )

    print(f"[demo] run_label={run_label}")
    print(f"[demo] run_id={run_id} (UUID; used by Sentience Studio)")
    print(f"[demo] DEMO_MODE={DEMO_MODE!r} (set DEMO_MODE=fail to force a failing trace)")

    token_tracker = TokenTracker("langchain-debugging")

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
        from langchain_core.tools import tool

        extracted = ""
        try:
            from langchain.callbacks import get_openai_callback
        except ImportError:
            try:
                from langchain_community.callbacks import get_openai_callback  # type: ignore
            except ImportError:
                from contextlib import contextmanager

                @contextmanager
                def get_openai_callback():  # type: ignore
                    class _Noop:
                        prompt_tokens = 0
                        completion_tokens = 0

                    yield _Noop()

        _agent_builder = None
        try:
            from langchain.agents import AgentExecutor, create_openai_functions_agent

            def _build_executor(llm, tools, prompt):
                agent = create_openai_functions_agent(llm, tools, prompt)
                return AgentExecutor(agent=agent, tools=tools, verbose=True)

            _agent_builder = _build_executor
        except Exception:
            _agent_builder = None

        if _agent_builder is None:
            try:
                from langchain.agents import initialize_agent, AgentType  # type: ignore

                def _build_executor(llm, tools, _prompt):
                    return initialize_agent(
                        tools, llm, agent=AgentType.OPENAI_FUNCTIONS, verbose=True
                    )

                _agent_builder = _build_executor
            except Exception:
                _agent_builder = None
    except ImportError as e:
        raise SystemExit(
            "langchain and langchain-openai are required.\n"
            "Install: pip install langchain langchain-openai\n"
            f"ImportError: {e}"
        ) from e

    browser = AsyncSentienceBrowser(
        api_key=sentience_api_key,
        headless=HEADLESS,
        user_data_dir=str(base_dir / "profile"),
        record_video_dir=str(video_dir) if RECORD_VIDEO else None,
        allowed_domains=["dw.com"],
        executable_path=SENTIENCE_BROWSER_EXECUTABLE_PATH,
    )
    await browser.start()
    if browser.context is not None:
        await browser.context.add_init_script(_stealth_init_script())
    await browser.goto(START_URL)
    page = browser.page
    if page is None:
        raise RuntimeError("SentienceBrowser did not create a page.")
    await _dismiss_dw_modal(page)
    await _wait_for_sentience(page, timeout_ms=30000)

    dbg = SentienceDebugger.attach(
        page=page,
        tracer=tracer,
        snapshot_options=SnapshotOptions(use_api=True, show_overlay=True, limit=50),
        sentience_api_key=sentience_api_key,
    )

    if True:
        try:
            # -------------------------
            # Scene 1: Verify landing
            # -------------------------
            async with dbg.step("Verify landing", step_index=0):
                await _dismiss_dw_modal(page)
                await dbg.snapshot(goal="verify:landing", use_api=True, limit=60, show_overlay=True)
                await dbg.check(url_contains("dw.com"), label="on_dw", required=True).eventually(
                    timeout_s=10
                )
            p0 = screenshots_dir / f"scene1_{_safe_filename('landing')}.png"
            await _screenshot(page, p0)

            # -------------------------
            # Scene 2: LangChain agent opens DW homepage
            # -------------------------
            @tool("open_dw_homepage")
            async def open_dw_homepage() -> str:
                """
                Navigate to the DW homepage.
                """
                await dbg.record_action("langchain: open DW homepage", url=page.url)
                await page.goto(START_URL, wait_until="domcontentloaded")
                await asyncio.sleep(1.0)
                await _dismiss_dw_modal(page)
                await _wait_for_sentience(page, timeout_ms=30000)
                return "Opened DW homepage"

            tools = [open_dw_homepage]

            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "You are a precise web agent. Use the open_dw_homepage tool exactly once.",
                    ),
                    ("human", "{input}"),
                    MessagesPlaceholder("agent_scratchpad"),
                ]
            )

            llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)

            task = "Open the DW homepage."
            async with dbg.step("LangChain agent: open homepage", step_index=1):
                with get_openai_callback() as cb:
                    if _agent_builder is not None:
                        executor = _agent_builder(llm, tools, prompt)
                        await executor.ainvoke({"input": task})
                    else:
                        # Fallback: no agent helpers in this langchain build.
                        _ = await llm.ainvoke(task)
                        try:
                            await open_dw_homepage.ainvoke({})
                        except Exception:
                            coro = getattr(open_dw_homepage, "coroutine", None)
                            if callable(coro):
                                await coro()
                            else:
                                raise
                token_tracker.log_interaction(
                    "scene 2: langchain open homepage", cb.prompt_tokens, cb.completion_tokens
                )

            # Verify homepage
            snap = await dbg.snapshot(
                goal="verify:dw_homepage", use_api=True, limit=80, show_overlay=True
            )
            await dbg.check(
                any_of(
                    exists("role=heading"),
                    exists("text~'DW'"),
                ),
                label="on_dw_homepage",
                required=True,
            ).eventually(timeout_s=12)

            p1 = screenshots_dir / f"scene2_{_safe_filename('homepage')}.png"
            await _screenshot(page, p1)
            try:
                visualize_api_elements(str(p1), snap.model_dump())
            except Exception:
                pass

            # -------------------------
            # Scene 3: Extract top headline + time
            # -------------------------
            extracted = ""
            expected_headline = ""
            expected_time = ""
            async with dbg.step("Extract answer", step_index=2):
                if DEMO_MODE == "fail":
                    # Force an explicit failure for demo/Studio walkthrough.
                    await dbg.check(
                        exists("text~'__INTENTIONAL_FAILURE__'"),
                        label="intentional_failure",
                        required=True,
                    ).eventually(timeout_s=4)
                else:
                    await dbg.check(
                        any_of(
                            exists("role=heading"),
                            exists("role=link"),
                            exists("text~'DW'"),
                        ),
                        label="headline_signal_present",
                        required=True,
                    ).eventually(timeout_s=8)

                extracted = await page.evaluate(
                    """() => {
  const root = document.querySelector('main') || document.body;
  if (!root) return '';

  const pickFromArticle = (article) => {
    if (!article) return null;
    const headlineEl =
      article.querySelector('h1') ||
      article.querySelector('h2') ||
      article.querySelector('h3') ||
      article.querySelector('[data-title]') ||
      article.querySelector('[class*=\"headline\" i]');
    const timeEl =
      article.querySelector('time') ||
      article.querySelector('[class*=\"date\" i] time') ||
      article.querySelector('[class*=\"date\" i]');
    const headline = headlineEl ? (headlineEl.textContent || '').trim() : '';
    let timeText = '';
    if (timeEl) {
      timeText = timeEl.getAttribute('datetime') || (timeEl.textContent || '').trim();
    }
    if (!headline) return null;
    return { headline, timeText };
  };

  const candidates = [
    root.querySelector('article'),
    root.querySelector('[class*=\"top\" i] article'),
    root.querySelector('[class*=\"top\" i]'),
    root.querySelector('[class*=\"teaser\" i]'),
  ].filter(Boolean);

  let picked = null;
  for (const c of candidates) {
    picked = pickFromArticle(c);
    if (picked) break;
  }

  if (!picked) {
    const h = root.querySelector('h1') || root.querySelector('h2') || root.querySelector('h3');
    const t = root.querySelector('time');
    picked = {
      headline: h ? (h.textContent || '').trim() : '',
      timeText: t ? (t.getAttribute('datetime') || (t.textContent || '').trim()) : '',
    };
  }

  const out = [];
  if (picked.headline) out.push('Headline: ' + picked.headline);
  if (picked.timeText) out.push('Time: ' + picked.timeText);
  return out.join('\\n');
}"""
                )
                expected = await page.evaluate(
                    """() => {
  const root = document.querySelector('main') || document.body;
  if (!root) return { headline: '', timeText: '' };
  const article = root.querySelector('article') || root.querySelector('[class*="top" i] article') || root.querySelector('[class*="top" i]');
  const headlineEl = article ? (article.querySelector('h1, h2, h3') || article.querySelector('[class*="headline" i]')) : null;
  const timeEl = article ? (article.querySelector('time') || article.querySelector('[class*="date" i] time') || article.querySelector('[class*="date" i]')) : null;
  const headline = headlineEl ? (headlineEl.textContent || '').trim() : '';
  let timeText = '';
  if (timeEl) {
    timeText = timeEl.getAttribute('datetime') || (timeEl.textContent || '').trim();
  }
  return { headline, timeText };
}"""
                )
                if isinstance(expected, dict):
                    expected_headline = (expected.get("headline") or "").strip()
                    expected_time = (expected.get("timeText") or "").strip()

                extracted_headline, extracted_time = _parse_extraction(extracted)
                if DEMO_FAILURE == "headline":
                    extracted_headline = "Homepage"
                if DEMO_FAILURE == "time":
                    extracted_time = ""

                await dbg.check(
                    custom(
                        lambda _ctx: bool(extracted_headline)
                        and bool(expected_headline)
                        and extracted_headline.lower() == expected_headline.lower(),
                        label="headline_matches_top_story",
                    ),
                    label="verify_headline_matches",
                    required=DEMO_FAILURE in {"headline", "time"},
                ).eventually(timeout_s=4)
                await dbg.check(
                    custom(
                        lambda _ctx: bool(extracted_time)
                        and bool(expected_time)
                        and (extracted_time in expected_time or expected_time in extracted_time),
                        label="time_matches_top_story",
                    ),
                    label="verify_time_matches",
                    required=DEMO_FAILURE in {"headline", "time"},
                ).eventually(timeout_s=4)

            p2 = screenshots_dir / f"scene3_{_safe_filename('answer')}.png"
            await _screenshot(page, p2)

        finally:
            # Persist Playwright video if available
            try:
                persisted = await try_persist_page_video(page, out_dir=video_dir, filename="playwright.mp4")
                if persisted:
                    print(f"[video] persisted Playwright recording to: {persisted}")
            except Exception:
                pass

            # Save token usage summary
            try:
                token_tracker.save_to_file(str(base_dir / "token_usage.json"))
            except Exception as e:
                print(f"[warn] token usage save failed: {e}")
            trace_dst = base_dir / "trace.jsonl"
            try:
                import shutil

                sink = getattr(tracer, "sink", None)
                trace_src = None
                if sink is not None:
                    trace_src = getattr(sink, "path", None) or getattr(sink, "_path", None)
                if trace_src and Path(trace_src).exists():
                    shutil.copyfile(trace_src, trace_dst)
            except Exception as e:
                print(f"[warn] trace copy failed: {e}")
            try:
                tracer.close()
            except Exception as e:
                print(f"[warn] tracer close failed: {e}")
            try:
                index_dst = trace_dst.with_suffix(".index.json")
                if trace_dst.exists() and not index_dst.exists():
                    try:
                        from sentience.trace_indexing import write_trace_index

                        write_trace_index(str(trace_dst), str(index_dst), frontend_format=True)
                    except Exception:
                        pass
            except Exception as e:
                print(f"[warn] trace index failed: {e}")
            try:
                import json

                out = {
                    "question": TASK_QUESTION,
                    "answer_paragraph": extracted,
                    "url": page.url,
                }
                (base_dir / "extraction.json").write_text(
                    json.dumps(out, indent=2), encoding="utf-8"
                )
            except Exception as e:
                print(f"[warn] extraction save failed: {e}")

            # Stitch screenshots into a simple video (optional)
            out_mp4 = video_dir / "demo.mp4"
            if create_demo_video is not None:
                try:
                    create_demo_video(str(screenshots_dir), token_tracker.get_summary(), str(out_mp4))
                except Exception as e:
                    print(f"[warn] video stitching failed: {e}")
            else:
                print("[video] moviepy not installed; skipping screenshot stitching")

            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
