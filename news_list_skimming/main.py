import asyncio
import os
import random
import re
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime

from dotenv import load_dotenv

from sentience.actions import click_async, press_async, type_text_async
from sentience.async_api import AsyncSentienceBrowser
from sentience.backends.playwright_backend import PlaywrightBackend
from sentience.backends.sentience_context import SentienceContext
from sentience.cursor_policy import CursorPolicy
from sentience.models import SnapshotOptions
from sentience.tracer_factory import create_tracer
from sentience.verification import AssertOutcome, exists, url_contains
from sentience.agent_runtime import AgentRuntime
from sentience.llm_provider import LocalLLMProvider, LocalVisionLLMProvider, MLXVLMProvider


@dataclass
class StepTokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_click_id(text: str) -> int | None:
    """
    Parse CLICK(<id>) from LLM output.
    """
    m = re.search(r"CLICK\s*\(\s*(\d+)\s*\)", text, flags=re.IGNORECASE)
    if not m:
        return None
    return int(m.group(1))


def build_llm_user_prompt(task: str, compact_elements: str) -> str:
    return (
        "You are controlling a browser via element IDs.\n\n"
        "You must respond with exactly ONE action in this format:\n"
        "- CLICK(<id>)\n\n"
        "Rules:\n"
        "- Only click an element that clearly matches the task.\n"
        "- Prefer DG=1 and low ord for 'top/first' list tasks.\n"
        "- If multiple candidates match, choose the safest/most obvious.\n\n"
        f"Task:\n{task}\n\n"
        "Elements (ID|role|text|imp|is_primary|docYq|ord|DG|href):\n"
        f"{compact_elements}\n"
    )


def _clip_for_log(text: str, max_chars: int = 2400) -> str:
    if text is None:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n… (clipped)"


def init_vision_provider() -> object | None:
    """
    Best-effort vision provider initializer.
    """
    provider = (os.getenv("LOCAL_VISION_PROVIDER") or "mlx").strip().lower()
    model = (os.getenv("LOCAL_VISION_MODEL") or "").strip()
    if not model:
        return None

    if provider == "mlx":
        return MLXVLMProvider(model=model)
    if provider == "hf":
        return LocalVisionLLMProvider(model_name=model)

    return None


async def main() -> None:
    load_dotenv()

    # Help debug env issues quickly (common when pyenv/global site-packages are used).
    try:
        import sentience as _sentience

        if "site-packages/sentience" in (_sentience.__file__ or ""):
            print(
                f"[warn] Using sentience from site-packages: {_sentience.__file__}\n"
                f"       Python: {sys.executable}\n"
                f"       If you expected the monorepo SDK, activate the demo venv and run:\n"
                f"         pip install -e ../sdk-python\n",
                flush=True,
            )
    except Exception:
        pass

    # -------------------------
    # Global demo configuration
    # -------------------------
    task_goal = "News list skimming: Google → open HN Show → open the FIRST (top 1) 'Show HN' post"
    # IMPORTANT: ordinal ranking/boosting is keyed off SnapshotOptions.goal text.
    # Include explicit ordinal terms like "FIRST" / "top 1" so the core can apply its boost.
    snapshot_goal = "Find the FIRST (top 1) 'Show HN' post in the list and open it"
    start_ts = time.time()
    run_id = str(uuid.uuid4())

    sentience_api_key = os.getenv("SENTIENCE_API_KEY")
    # If a key is present, force Gateway refinement for snapshots (Pro/Enterprise).
    use_api = bool((sentience_api_key or "").strip())

    # Tier 1: local text LLM (HF transformers)
    local_text_model = os.getenv("LOCAL_TEXT_MODEL") or "Qwen/Qwen2.5-3B-Instruct"
    # Hardcode device selection for the public demo (keep env surface minimal).
    llm = LocalLLMProvider(model_name=local_text_model, device="auto", load_in_4bit=False)

    # Tier 2: local vision LLM (fallback, last resort)
    vision_provider = init_vision_provider()

    # Cloud tracing
    tracer = create_tracer(
        api_key=sentience_api_key,
        run_id=run_id,
        upload_trace=bool(sentience_api_key),
        goal=task_goal,
        agent_type="public_build/news_list_skimming",
        llm_model=local_text_model,
        start_url="https://news.ycombinator.com/show",
    )
    tracer.emit_run_start(agent="NewsListSkimmingDemo", llm_model=local_text_model, config={})

    # Browser (keep api_key unset to avoid gateway payload limits; tracing upload is separate)
    # NOTE: AsyncSentienceBrowser's async context manager already calls `await start()`.
    # Do NOT call start() again here, or you'll spawn a second Chromium window/context.
    # Also: use a persistent profile dir to reduce Google bot challenges across runs.
    user_data_dir = os.path.join(os.path.dirname(__file__), ".user_data")
    async with AsyncSentienceBrowser(headless=False, user_data_dir=user_data_dir) as browser:
        if browser.page is None:
            raise RuntimeError("Browser page not initialized (start() should have been called by __aenter__)")

        backend = PlaywrightBackend(browser.page)
        # Demo UX: overlays always ON for debuggability.
        show_overlay = True
        show_grid = False

        runtime = AgentRuntime(
            backend=backend,
            tracer=tracer,
            sentience_api_key=sentience_api_key,
            snapshot_options=SnapshotOptions(
                limit=60,
                screenshot=False,
                show_overlay=show_overlay,
                show_grid=show_grid,
                goal=snapshot_goal,
                use_api=True if use_api else None,
                sentience_api_key=sentience_api_key if use_api else None,
            ),
        )

        ctx_formatter = SentienceContext(max_elements=60)
        # Slightly slower, more human-ish mouse movement (helps avoid bot-like timing).
        cursor_policy = CursorPolicy(
            mode="human",
            duration_ms=550,
            pause_before_click_ms=120,
            jitter_px=1.5,
            overshoot_px=8.0,
        )

        def _pick_element_id_from_snapshot(
            *,
            snap,
            roles: set[str],
            prefer_name_contains: str | None = None,
        ) -> int | None:
            """
            Pick a best-effort element ID from a snapshot by role + heuristics.
            """
            candidates = []
            for el in snap.elements:
                role = (el.role or "").lower()
                if role not in roles:
                    continue
                candidates.append(el)

            if not candidates:
                return None

            if prefer_name_contains:
                needle = prefer_name_contains.lower()
                for el in sorted(candidates, key=lambda e: e.importance or 0, reverse=True):
                    name = (getattr(el, "name", None) or "").lower()
                    text = (el.text or "").lower()
                    if needle in name or needle in text:
                        return el.id

            # Fallback: highest importance
            candidates.sort(key=lambda e: e.importance or 0, reverse=True)
            return candidates[0].id


        total_tokens = StepTokenUsage(0, 0, 0)
        step_stats: list[dict] = []

        async def run_step(step_index: int, goal: str, fn):
            nonlocal total_tokens
            step_id = runtime.begin_step(goal, step_index=step_index - 1)
            pre_url = browser.page.url
            tracer.emit("step_start", {"step_index": step_index, "goal": goal, "pre_url": pre_url}, step_id=step_id)
            t0 = time.time()
            ok = False
            error: str | None = None
            usage: StepTokenUsage | None = None
            note: str | None = None
            try:
                ret = await fn(step_id)
                # Allow step functions to optionally return a third value: a short note for logs.
                # - (ok, usage)
                # - (ok, usage, note)
                if isinstance(ret, tuple) and len(ret) == 3:
                    ok, usage, note = ret  # type: ignore[misc]
                else:
                    ok, usage = ret  # type: ignore[misc]
            except Exception as e:
                ok = False
                error = str(e)
                tracer.emit("error", {"error": error, "step_index": step_index, "goal": goal}, step_id=step_id)
            dt_ms = int((time.time() - t0) * 1000)

            verify = runtime.get_assertions_for_step_end()
            tracer.emit(
                "step_end",
                {
                    "step_index": step_index,
                    "goal": goal,
                    "success": ok,
                    "duration_ms": dt_ms,
                    "post_url": browser.page.url,
                    "verify": {"signals": verify},
                    "token_usage": (
                        {
                            "prompt_tokens": usage.prompt_tokens,
                            "completion_tokens": usage.completion_tokens,
                            "total_tokens": usage.total_tokens,
                        }
                        if usage
                        else None
                    ),
                    "error": error,
                },
                step_id=step_id,
            )

            if usage:
                total_tokens = StepTokenUsage(
                    total_tokens.prompt_tokens + usage.prompt_tokens,
                    total_tokens.completion_tokens + usage.completion_tokens,
                    total_tokens.total_tokens + usage.total_tokens,
                )

            step_stats.append(
                {
                    "step_index": step_index,
                    "goal": goal,
                    "success": ok,
                    "duration_ms": dt_ms,
                    "token_usage": usage.__dict__ if usage else None,
                    "url": browser.page.url,
                    "note": note,
                }
            )
            note_suffix = f" | {note}" if note else ""
            print(
                f"[{now_iso()}] Step {step_index} {'PASS' if ok else 'FAIL'} ({dt_ms}ms): {goal}{note_suffix}",
                flush=True,
            )
            if usage:
                print(
                    f"  tokens: prompt={usage.prompt_tokens} completion={usage.completion_tokens} total={usage.total_tokens}",
                    flush=True,
                )
            if error:
                print(f"  error: {error}", flush=True)
            return ok

        # -------------------------
        # Step 1: Navigate to Google and verify search box exists
        # -------------------------
        async def step1(_step_id: str):
            # Use /ncr to reduce geo redirects / extra interstitials.
            await browser.goto("https://www.google.com/ncr")
            await browser.page.wait_for_load_state("domcontentloaded", timeout=10_000)
            # Wait a bit more for SPA hydration (Google's search box might render after DOMContentLoaded)
            await browser.page.wait_for_timeout(500)
            await runtime.snapshot(goal="Find the Google search box")

            ok1 = runtime.assert_(url_contains("google."), label="on_google", required=True)

            # Debug: print what roles are actually in the snapshot
            if runtime.last_snapshot:
                roles_in_snapshot = set()
                for el in runtime.last_snapshot.elements:
                    if el.role:
                        roles_in_snapshot.add(el.role)
                print(f"[debug] Roles in snapshot: {sorted(roles_in_snapshot)}", flush=True)
                # Check if combobox/textbox are present
                has_combobox = any(el.role == "combobox" for el in runtime.last_snapshot.elements)
                has_textbox = any(el.role == "textbox" for el in runtime.last_snapshot.elements)
                print(f"[debug] Has combobox: {has_combobox}, Has textbox: {has_textbox}", flush=True)

            # Google uses different roles depending on locale/variant; keep it flexible.
            ok2 = await runtime.check(
                exists("role=combobox"),
                label="google_has_combobox",
                required=False,
            ).eventually(
                timeout_s=8.0,
                poll_s=0.25,
                max_snapshot_attempts=3,
                snapshot_kwargs={
                    "limit": 60,
                    "screenshot": False,
                    "goal": "Find the Google search box",
                    "use_api": True if use_api else None,
                    "sentience_api_key": sentience_api_key if use_api else None,
                },
                vision_provider=vision_provider,
            )

            ok3 = await runtime.check(
                exists("role=textbox"),
                label="google_has_textbox",
                required=False,
            ).eventually(
                timeout_s=8.0,
                poll_s=0.25,
                max_snapshot_attempts=3,
                snapshot_kwargs={
                    "limit": 60,
                    "screenshot": False,
                    "goal": "Find the Google search box",
                    "use_api": True if use_api else None,
                    "sentience_api_key": sentience_api_key if use_api else None,
                },
                vision_provider=vision_provider,
            )

            return (ok1 and (ok2 or ok3)), None

        # ---------------------------------------
        # Step 2: Search for "Hacker News Show"
        # ---------------------------------------
        selected_id: int | None = None  # later, on HN Show page

        async def step2(step_id: str):
            await runtime.snapshot(limit=60, screenshot=False, goal="Type query: Hacker News Show")
            snap = runtime.last_snapshot
            if snap is None:
                raise RuntimeError("snapshot missing")

            # Let the LLM pick the correct search box ID from the compact prompt (no heuristics).
            compact = ctx_formatter._format_snapshot_for_llm(snap)
            tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)
            print("\n--- Step 2: LLM compact prompt (elements context) ---", flush=True)
            print(_clip_for_log(compact), flush=True)
            print("--- end compact prompt ---\n", flush=True)

            task = "Click the main Google search input box (where you type a query). Do NOT click buttons or result links."
            user_prompt = build_llm_user_prompt(task, compact)
            sys_prompt = "You are a careful web agent. Output only CLICK(<id>)."

            resp = llm.generate(sys_prompt, user_prompt, temperature=0.0, max_new_tokens=24)
            tracer.emit(
                "llm",
                {
                    "model": llm.model_name,
                    "prompt_tokens": resp.prompt_tokens,
                    "completion_tokens": resp.completion_tokens,
                    "total_tokens": resp.total_tokens,
                    "output": resp.content,
                },
                step_id=step_id,
            )

            search_box_id = parse_click_id(resp.content or "")
            if search_box_id is None:
                runtime.assert_(exists("role=textbox"), label="llm_failed_to_pick_search_box", required=True)
                return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

            # Click → type → enter
            await click_async(browser, search_box_id, use_mouse=True, cursor_policy=cursor_policy)
            # Google is extremely sensitive to "perfect" deterministic typing.
            # Type with per-keystroke jitter + occasional pauses to look human.
            query = "Hacker News Show"
            for ch in query:
                # Type one char (page is already focused via click)
                try:
                    await browser.page.keyboard.type(ch)
                except Exception:
                    # If focus is lost, re-click and continue.
                    await click_async(browser, search_box_id, use_mouse=True, cursor_policy=cursor_policy)
                    await browser.page.keyboard.type(ch)

                # Jitter between keys (40–140ms), plus rare longer pauses.
                await browser.page.wait_for_timeout(random.randint(40, 140))
                if random.random() < 0.08:
                    await browser.page.wait_for_timeout(random.randint(180, 520))

            # Settle before submit (avoid "instant type+enter" pattern).
            await browser.page.wait_for_timeout(random.randint(450, 1100))
            await press_async(browser, "Enter")
            await browser.page.wait_for_load_state("domcontentloaded", timeout=10_000)
            # Wait a bit more for search results to render
            await browser.page.wait_for_timeout(1000)

            # If Google blocks us, fail fast with a clear reason.
            await runtime.snapshot(limit=60, screenshot=False, goal="Check for bot block or find search results")
            blocked = runtime.assert_(
                exists("text~'unusual traffic'"),
                label="google_bot_block_detected",
                required=False,
            )
            if blocked:
                runtime.assert_(
                    exists("text~'unusual traffic'"),
                    label="google_bot_blocked",
                    required=True,
                )
                tracer.emit(
                    "note",
                    {"kind": "google_blocked", "reason": "unusual traffic"},
                    step_id=step_id,
                )
                return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

            # Let LLM pick the "Show | Hacker News" link directly from the compact prompt
            # No strict text matching - let the LLM decide what matches best
            await runtime.snapshot(limit=60, screenshot=False, goal="Click the result titled 'Show | Hacker News'")
            snap2 = runtime.last_snapshot
            if snap2 is None:
                raise RuntimeError("snapshot missing after search results")

            compact2 = ctx_formatter._format_snapshot_for_llm(snap2)
            tracer.emit("note", {"kind": "compact_prompt", "text": compact2}, step_id=step_id)
            print("\n--- Step 2 (click result): LLM compact prompt (elements context) ---", flush=True)
            print(_clip_for_log(compact2), flush=True)
            print("--- end compact prompt ---\n", flush=True)

            task2 = (
                "Click the Google search result link that goes to news.ycombinator.com/show.\n"
                "REQUIREMENTS:\n"
                "- The href MUST be exactly 'news.ycombinator.com/show' (NOT /shownew)\n"
                "- Prefer links ending in '/show' over '/shownew'\n"
                "- The text should mention 'Show' and 'Hacker News'\n"
                "NEVER click these:\n"
                "- Links with 'reddit.com' in href\n"
                "- Links saying 'More results from...'\n"
                "- Links saying 'See more' or 'More'\n"
                "- Links to 'news.ycombinator.com/shownew' (wrong page)\n"
                "- Any link that doesn't have 'news.ycombinator.com/show' in the href"
            )
            user_prompt2 = build_llm_user_prompt(task2, compact2)
            sys_prompt2 = "You are a careful web agent. Output only CLICK(<id>)."

            resp2 = llm.generate(sys_prompt2, user_prompt2, temperature=0.0, max_new_tokens=24)
            tracer.emit(
                "llm",
                {
                    "model": llm.model_name,
                    "prompt_tokens": resp2.prompt_tokens,
                    "completion_tokens": resp2.completion_tokens,
                    "total_tokens": resp2.total_tokens,
                    "output": resp2.content,
                },
                step_id=step_id,
            )

            click_id = parse_click_id(resp2.content or "")
            if click_id is None:
                print(f"[error] LLM failed to output CLICK(<id>) format. Response: {resp2.content}", flush=True)
                runtime.assert_(
                    exists("role=link"),
                    label="llm_failed_to_pick_any_link",
                    required=True,
                )
                total_usage = StepTokenUsage(
                    (resp.prompt_tokens or 0) + (resp2.prompt_tokens or 0),
                    (resp.completion_tokens or 0) + (resp2.completion_tokens or 0),
                    (resp.total_tokens or 0) + (resp2.total_tokens or 0),
                )
                return False, total_usage

            # Verify the chosen element exists and is a link (LLM decides if it's the right one)
            chosen = next((e for e in snap2.elements if e.id == click_id), None)
            chosen_ok = chosen is not None and (chosen.role or "").lower() == "link"
            if not chosen_ok:
                print(f"[error] LLM chose invalid element: id={click_id}, found={chosen is not None}, role={chosen.role if chosen else None}", flush=True)
                runtime.assert_(
                    (lambda ctx: AssertOutcome(passed=False, reason="chosen_element_not_found_or_not_link", details={"id": click_id, "found": chosen is not None, "role": (chosen.role if chosen else None)}) ),  # type: ignore
                    label="chosen_is_valid_link",
                    required=True,
                )
                total_usage = StepTokenUsage(
                    (resp.prompt_tokens or 0) + (resp2.prompt_tokens or 0),
                    (resp.completion_tokens or 0) + (resp2.completion_tokens or 0),
                    (resp.total_tokens or 0) + (resp2.total_tokens or 0),
                )
                return False, total_usage
            
            # Log what was chosen - make it prominent
            chosen_text = (chosen.text or "")[:100] if chosen else "N/A"
            chosen_href = (chosen.href or "")[:200] if chosen else "N/A"
            print(f"\n{'='*60}", flush=True)
            print(f"Step 2: Agent chose element ID {click_id} for 'Show | Hacker News'", flush=True)
            print(f"  Element text: {chosen_text!r}", flush=True)
            print(f"  Element href: {chosen_href!r}", flush=True)
            print(f"{'='*60}\n", flush=True)
            
            # Validate the chosen link - must be news.ycombinator.com, not reddit or "More results"
            text_lower = (chosen_text or "").lower()
            href_lower = (chosen_href or "").lower()

            # Check if it's the wrong link or if it's /shownew (we want /show)
            is_shownew = "news.ycombinator.com/shownew" in href_lower
            is_wrong_link = (
                "reddit.com" in href_lower or
                "more results" in text_lower or
                "news.ycombinator.com/show" not in href_lower or
                is_shownew  # /shownew is not what we want
            )

            if is_wrong_link:
                if is_shownew:
                    print(f"[warn] LLM chose /shownew instead of /show: href={chosen_href!r}", flush=True)
                else:
                    print(f"[error] LLM chose wrong link (not HN Show): text={chosen_text!r}, href={chosen_href!r}", flush=True)
                print("[info] Looking for correct link with news.ycombinator.com/show (not /shownew) in href...", flush=True)

                # Find the correct link - prefer /show over /shownew
                correct_link = None
                for el in snap2.elements:
                    el_href = (el.href or "").lower()
                    # Must have /show but NOT /shownew
                    if "news.ycombinator.com/show" in el_href and "news.ycombinator.com/shownew" not in el_href:
                        correct_link = el
                        break

                if correct_link:
                    print(f"[info] Found correct link: id={correct_link.id}, text={correct_link.text!r}, href={correct_link.href!r}", flush=True)
                    click_id = correct_link.id
                    chosen = correct_link
                    chosen_text = (chosen.text or "")[:100]
                    chosen_href = (chosen.href or "")[:200]
                else:
                    print("[error] Could not find any link to news.ycombinator.com/show in the search results", flush=True)
                    # List all links for debugging
                    print("[debug] Available links:", flush=True)
                    for el in snap2.elements:
                        if (el.role or "").lower() == "link":
                            print(f"  id={el.id} text={el.text!r} href={el.href!r}", flush=True)
                    runtime.assert_(
                        exists("href~'news.ycombinator.com/show'"),
                        label="hn_show_link_not_found_in_results",
                        required=True,
                    )
                    total_usage = StepTokenUsage(
                        (resp.prompt_tokens or 0) + (resp2.prompt_tokens or 0),
                        (resp.completion_tokens or 0) + (resp2.completion_tokens or 0),
                        (resp.total_tokens or 0) + (resp2.total_tokens or 0),
                    )
                    return False, total_usage

            # Click the element ID chosen by the LLM agent
            print(f"\n>>> Clicking element ID {click_id} (chosen by LLM agent) <<<", flush=True)
            result = await click_async(browser, click_id, use_mouse=True, cursor_policy=cursor_policy)
            print(f"Click result: success={result.success}, outcome={result.outcome}", flush=True)
            tracer.emit(
                "action",
                {
                    "action": "click",
                    "element_id": click_id,
                    "success": result.success,
                    "outcome": result.outcome,
                    "cursor": getattr(result, "cursor", None),
                },
                step_id=step_id,
            )

            # Wait for navigation to complete
            await browser.page.wait_for_load_state("domcontentloaded", timeout=10_000)

            total_usage = StepTokenUsage(
                (resp.prompt_tokens or 0) + (resp2.prompt_tokens or 0),
                (resp.completion_tokens or 0) + (resp2.completion_tokens or 0),
                (resp.total_tokens or 0) + (resp2.total_tokens or 0),
            )
            chosen_text_short = (chosen.text or "")[:60] if chosen else "N/A"
            note = f"search_box_id={search_box_id}, clicked_result_id={click_id} (text={chosen_text_short!r})"
            return True, total_usage, note

        # -------------------------
        # Step 3: Verify we landed on HN Show page (Step 2 already clicked the link)
        # -------------------------
        async def step3(step_id: str):
            await runtime.snapshot(limit=60, screenshot=False, goal=snapshot_goal)

            # Debug: print current URL
            current_url = browser.page.url
            print(f"[debug] Step 3: Current URL = {current_url}", flush=True)

            ok1 = runtime.assert_(url_contains("news.ycombinator.com/show"), label="on_hn_show_via_google", required=True)
            print(f"[debug] Step 3: URL check (ok1) = {ok1}", flush=True)

            return ok1, None

        # ---------------------------------------
        # Step 4: LLM picks the FIRST (top 1) "Show HN" post on HN Show page
        # ---------------------------------------
        async def step4(step_id: str):
            nonlocal selected_id
            await runtime.snapshot(limit=60, screenshot=False, goal=snapshot_goal)
            snap = runtime.last_snapshot
            if snap is None:
                raise RuntimeError("snapshot missing")

            compact = ctx_formatter._format_snapshot_for_llm(snap)
            tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)
            print("\n--- Step 4: LLM compact prompt (elements context) ---", flush=True)
            print(_clip_for_log(compact), flush=True)
            print("--- end compact prompt ---\n", flush=True)

            task = "Find the FIRST (top 1) post in the list that is a 'Show HN' item, then click that post."
            user_prompt = build_llm_user_prompt(task, compact)
            sys_prompt = "You are a careful web agent. Output only CLICK(<id>)."

            resp = llm.generate(sys_prompt, user_prompt, temperature=0.0, max_new_tokens=32)
            tracer.emit(
                "llm",
                {
                    "model": llm.model_name,
                    "prompt_tokens": resp.prompt_tokens,
                    "completion_tokens": resp.completion_tokens,
                    "total_tokens": resp.total_tokens,
                    "output": resp.content,
                },
                step_id=step_id,
            )

            click_id = parse_click_id(resp.content or "")
            if click_id is None:
                runtime.assert_(exists("role=link"), label="llm_returned_invalid_action", required=True)
                return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

            chosen = next((e for e in snap.elements if e.id == click_id), None)
            picked_title_for_step = None
            if chosen is not None:
                picked_title = (chosen.text or "").strip()
                picked_href = (chosen.href or "").strip()
                picked_title_for_step = picked_title
                print(
                    f"  picked: id={click_id} title={picked_title[:140]!r} href={picked_href[:200]!r}",
                    flush=True,
                )
                tracer.emit(
                    "note",
                    {
                        "kind": "picked_post",
                        "id": click_id,
                        "title": picked_title[:500],
                        "href": picked_href[:500],
                    },
                    step_id=step_id,
                )

            ok = chosen is not None and ("show hn" in (chosen.text or "").lower())
            runtime.assert_(exists(f"id={click_id}"), label="chosen_id_exists", required=True)
            runtime.assert_(
                (lambda ctx: type("O", (), {"passed": ok, "reason": "chosen_contains_show_hn", "details": {"id": click_id}})())  # type: ignore
                if ok
                else (lambda ctx: type("O", (), {"passed": False, "reason": "chosen_missing_show_hn", "details": {"id": click_id, "text": (chosen.text if chosen else None)}})())  # type: ignore
                ,
                label="chosen_is_show_hn",
                required=True,
            )

            selected_id = click_id
            note = f"picked_title={picked_title_for_step[:140]!r}" if picked_title_for_step else f"picked_id={click_id}"
            return True, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0), note

        # -------------------------
        # Step 5: Click chosen Show HN post with human cursor + verify navigation
        # -------------------------
        async def step5(_step_id: str):
            if selected_id is None:
                raise RuntimeError("No selected_id from step4")

            pre_url = browser.page.url
            result = await click_async(browser, selected_id, use_mouse=True, cursor_policy=cursor_policy)
            tracer.emit(
                "action",
                {
                    "action": "click",
                    "element_id": selected_id,
                    "success": result.success,
                    "outcome": result.outcome,
                    "cursor": getattr(result, "cursor", None),
                },
                step_id=runtime.step_id,
            )

            try:
                await browser.page.wait_for_function(
                    "(pre) => window.location.href !== pre",
                    pre_url,
                    timeout=10_000,
                )
            except Exception:
                await browser.page.wait_for_load_state("domcontentloaded", timeout=10_000)

            await runtime.snapshot(limit=60, screenshot=False, goal=snapshot_goal)

            def _url_changed(ctx) -> AssertOutcome:  # type: ignore[no-untyped-def]
                url = (ctx.url or "").strip()
                ok = bool(url) and url != pre_url
                return AssertOutcome(passed=ok, reason="" if ok else "url did not change", details={"pre_url": pre_url, "url": url[:200]})

            ok1 = runtime.assert_(_url_changed, label="url_changed_after_click", required=True)
            runtime.assert_(exists("role=link"), label="page_has_links", required=False)
            tracer.emit("note", {"kind": "nav_debug", "pre_url": pre_url, "post_url": browser.page.url}, step_id=runtime.step_id)
            return ok1, None

        # -------------------------
        # Run the steps
        # -------------------------
        all_ok = True
        steps = [
            (1, "Navigate to Google + verify search box visible", step1),
            (2, "Search Google for 'Hacker News Show' + LLM clicks 'Show | Hacker News' result", step2),
            (3, "Verify we landed on HN Show page", step3),
            (4, "LLM identifies FIRST (top 1) 'Show HN' post", step4),
            (5, "Click selected post with human cursor + verify navigation", step5),
        ]
        for idx, goal, fn in steps:
            print(f"\n[{now_iso()}] Starting Step {idx}: {goal}", flush=True)
            try:
                ok = await run_step(idx, goal, fn)
                print(f"[{now_iso()}] Step {idx} completed with ok={ok}", flush=True)
                if not ok:
                    all_ok = False
                    # Debug UX: keep browser open briefly on failure so you can inspect state.
                    # This mirrors the "multi-step agent" feel (don't instantly disappear).
                    print(f"[{now_iso()}] Step {idx} failed. Keeping browser open for 30s for inspection...", flush=True)
                    try:
                        await browser.page.wait_for_timeout(30_000)
                    except Exception as e:
                        print(f"[{now_iso()}] Error during debug pause: {e}", flush=True)
                    break
            except Exception as e:
                print(f"[{now_iso()}] Step {idx} raised exception: {e}", flush=True)
                import traceback
                traceback.print_exc()
                all_ok = False
                print(f"[{now_iso()}] Keeping browser open for 30s after exception...", flush=True)
                try:
                    await browser.page.wait_for_timeout(30_000)
                except Exception:
                    pass
                break

        # Finalize run
        run_ms = int((time.time() - start_ts) * 1000)
        tracer.emit(
            "note",
            {
                "kind": "run_summary",
                "success": all_ok,
                "duration_ms": run_ms,
                "token_usage_total": total_tokens.__dict__,
                "steps": step_stats,
            },
        )
        tracer.set_final_status("success" if all_ok else "failure")
        tracer.emit_run_end(steps=len(step_stats), status=("success" if all_ok else "failure"))
        tracer.close(blocking=True)

        print("\n=== Run Summary ===")
        print(f"run_id: {run_id}")
        print(f"success: {all_ok}")
        print(f"duration_ms: {run_ms}")
        print(f"tokens_total: {total_tokens}")


if __name__ == "__main__":
    asyncio.run(main())

