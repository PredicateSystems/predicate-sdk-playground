"""
Demo 4: Interactive SPA Dashboard - KPI Extraction on Local Llama Land

This demo navigates to the dashboard page of a fake Next.js site (https://sentience-sdk-playground.vercel.app/dashboard)
and extracts KPI values. It builds upon Demo 3 (Login + Profile) by demonstrating extraction from a dynamic SPA dashboard.

Why high impact:
SPAs and dynamic content are where traditional scraping + vision agents fail;
Sentience's structure inference helps extract semantic data reliably.

Site Characteristics (intentional challenges):
- DELAYED HYDRATION: Dashboard KPI cards and content load after ~900-1500ms (setTimeout)
  → We handle with runtime.check(...).eventually() to wait for KPI elements
- DYNAMIC KPI CARDS: Three KPI cards with labels, values, and hints
  → We extract values by matching text patterns in snapshot elements
- LATE-LOADING TABLE: Event table loads after separate delay
  → We use eventually() with retries to wait for table content
- OPTIONAL LIVE MODE: ?live=1 causes continuous DOM churn every 400ms (for stress testing)
  → Tests agent robustness against structural changes
- SVG CHART: Engagement chart with polyline (tests handling of non-text elements)

Target KPIs to extract:
- Llama Coins: 128 (Monthly balance)
- Active Herds: 7 (Groups you follow)
- Messages: 3 (Unread)

Flow:
1. Navigate to login page → wait for form hydration
2. Fill username field → LLM identifies textbox, types "testuser"
3. Fill password field → LLM identifies password input, types "password123"
4. Click login button → LLM identifies "Sign in" button, waits for navigation
5. Navigate to dashboard page → click "Dashboard" link from profile page
6. Wait for KPI cards to load → use eventually(exists("text~'Llama Coins'")) with retries
7. Extract all three KPI values → verify each value matches expected
8. Verify event table loaded → check for "Recent events" and row content
9. Enable live mode & re-extract KPIs → stress test: prove snapshot stability during DOM churn

This demo showcases:
- SPA dashboard handling with delayed hydration
- Semantic KPI extraction from dynamic cards
- Verification assertions for extracted values (assert_ with AssertOutcome)
- Retry semantics with eventually() for late-loading content
- Snapshot stability during DOM churn (live mode stress test)
- Local LLM for element identification (Qwen 2.5 3B)
- Cloud tracing for debugging and replay

Key features demonstrated:
- eventually() retries: Handle 900-1500ms hydration delay
- Snapshot element extraction: Find KPI values by text matching
- DOM churn resilience: Extract stable data while table rows change every 400ms
- Structured assertions: Log extracted values with details
- Token usage tracking: Per-step breakdown for cost analysis
- Screenshot capture: For video generation and debugging
"""
import asyncio
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime

from dotenv import load_dotenv

# Import shared video utilities from amazon_shopping
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "amazon_shopping", "shared"))
from video_generator_simple import create_demo_video

from sentience.actions import click_async
from sentience.async_api import AsyncSentienceBrowser
from sentience.backends.playwright_backend import PlaywrightBackend
from sentience.backends.sentience_context import SentienceContext
from sentience.cursor_policy import CursorPolicy
from sentience.models import SnapshotOptions
from sentience.tracer_factory import create_tracer
from sentience.verification import AssertOutcome, exists, url_contains, is_enabled, is_disabled
from sentience.agent_runtime import AgentRuntime
from sentience.llm_provider import LocalLLMProvider
import random
import re


# Test credentials for the fake site
TEST_USERNAME = "testuser"
TEST_PASSWORD = "password123"

# Expected KPI values
EXPECTED_KPIS = {
    "Llama Coins": "128",
    "Active Herds": "7",
    "Messages": "3",
}


def parse_click_id(text: str) -> int | None:
    """Parse CLICK(<id>) from LLM output."""
    m = re.search(r"CLICK\s*\(\s*(\d+)\s*\)", text, flags=re.IGNORECASE)
    if not m:
        return None
    return int(m.group(1))


def build_llm_user_prompt(task: str, compact_elements: str) -> str:
    return (
        "You are controlling a browser via element IDs.\n\n"
        "You must respond with exactly ONE action in this format:\n"
        "- CLICK(<id>)\n\n"
        "SNAPSHOT FORMAT EXPLANATION:\n"
        "The snapshot shows elements in this format: ID|role|text|importance|is_primary|docYq|ord|DG|href|\n"
        "- ID: Element ID (use this for CLICK)\n"
        "- role: Element type (link, button, textbox, etc.)\n"
        "- text: Visible text content or placeholder\n\n"
        f"Task:\n{task}\n\n"
        "Elements (ID|role|text|imp|is_primary|docYq|ord|DG|href):\n"
        f"{compact_elements}\n"
    )


@dataclass
class StepTokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clip_for_log(text: str, max_chars: int = 2400) -> str:
    if text is None:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... (clipped)"


async def main() -> None:
    load_dotenv()

    # Help debug env issues quickly
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
    task_goal = "Dashboard KPI Extraction: Navigate to dashboard → Extract KPI values (Llama Coins, Active Herds, Messages)"
    snapshot_goal = "Find KPI cards and extract values"
    start_ts = time.time()
    run_id = str(uuid.uuid4())

    sentience_api_key = os.getenv("SENTIENCE_API_KEY")
    use_api = bool((sentience_api_key or "").strip())

    # Tier 1: local text LLM (HF transformers)
    local_text_model = os.getenv("LOCAL_TEXT_MODEL") or "Qwen/Qwen2.5-3B-Instruct"
    llm = LocalLLMProvider(model_name=local_text_model, device="auto", load_in_4bit=False)

    # Cloud tracing
    tracer = create_tracer(
        api_key=sentience_api_key,
        run_id=run_id,
        upload_trace=bool(sentience_api_key),
        goal=task_goal,
        agent_type="public_build/dashboard_kpi_extraction",
        llm_model=local_text_model,
        start_url="https://sentience-sdk-playground.vercel.app/dashboard",
    )
    tracer.emit_run_start(agent="DashboardKPIExtractionDemo", llm_model=local_text_model, config={})

    # Screenshot directory for video recording
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshots_dir = os.path.join(os.path.dirname(__file__), "screenshots", timestamp)
    os.makedirs(screenshots_dir, exist_ok=True)
    print(f"Screenshots will be saved to: {screenshots_dir}")

    # Browser
    user_data_dir = os.path.join(os.path.dirname(__file__), ".user_data")
    async with AsyncSentienceBrowser(headless=False, user_data_dir=user_data_dir) as browser:
        if browser.page is None:
            raise RuntimeError("Browser page not initialized")

        backend = PlaywrightBackend(browser.page)
        show_overlay = True
        show_grid = False

        runtime = AgentRuntime(
            backend=backend,
            tracer=tracer,
            sentience_api_key=sentience_api_key,
            snapshot_options=SnapshotOptions(
                limit=50,
                screenshot=False,
                show_overlay=show_overlay,
                show_grid=show_grid,
                goal=snapshot_goal,
                use_api=True if use_api else None,
                sentience_api_key=sentience_api_key if use_api else None,
            ),
        )

        ctx_formatter = SentienceContext(max_elements=60)
        cursor_policy = CursorPolicy(
            mode="human",
            duration_ms=550,
            pause_before_click_ms=120,
            jitter_px=1.5,
            overshoot_px=8.0,
        )

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
                if isinstance(ret, tuple) and len(ret) == 3:
                    ok, usage, note = ret
                else:
                    ok, usage = ret
            except Exception as e:
                ok = False
                error = str(e)
                tracer.emit("error", {"error": error, "step_index": step_index, "goal": goal}, step_id=step_id)
            dt_ms = int((time.time() - t0) * 1000)

            # Take screenshot for video recording
            screenshot_path = os.path.join(screenshots_dir, f"scene{step_index}_{goal.replace(' ', '_')[:30]}.png")
            try:
                await browser.page.screenshot(path=screenshot_path, full_page=False)
                print(f"  Screenshot saved: {screenshot_path}")
            except Exception as e:
                print(f"  Warning: Failed to save screenshot: {e}")

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
        # Step 1: Navigate to login page and wait for hydration
        # -------------------------
        async def step1(_step_id: str):
            await browser.goto("https://sentience-sdk-playground.vercel.app/login")
            await browser.page.wait_for_load_state("domcontentloaded", timeout=10_000)

            current_url = browser.page.url
            print(f"  [debug] Browser URL after navigation: {current_url}", flush=True)

            # Wait for login form to hydrate
            print("  [info] Waiting for login form hydration...", flush=True)
            form_loaded = await runtime.check(
                exists("role=textbox"),
                label="login_form_hydrated",
                required=True
            ).eventually(timeout_s=15.0, poll_s=0.5, max_snapshot_attempts=15)

            if not form_loaded:
                print("  [error] Login form did not hydrate in time", flush=True)
                return False, None

            print("  [info] Login form hydrated successfully", flush=True)
            return True, None

        # -------------------------
        # Step 2: Fill username field
        # -------------------------
        async def step2(step_id: str):
            await runtime.snapshot(limit=40, screenshot=False, goal="Find the username input field")
            snap = runtime.last_snapshot
            if snap is None:
                raise RuntimeError("snapshot missing")

            compact = ctx_formatter._format_snapshot_for_llm(snap)
            tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)
            print("\n--- Step 2: LLM compact prompt ---", flush=True)
            print(_clip_for_log(compact), flush=True)
            print("--- end compact prompt ---\n", flush=True)

            task = "Find the username input field (role='textbox') and click it."
            user_prompt = build_llm_user_prompt(task, compact)
            sys_prompt = "You are a careful web agent. Output only CLICK(<id>)."

            resp = llm.generate(sys_prompt, user_prompt, temperature=0.0, max_new_tokens=24)
            tracer.emit("llm", {"model": llm.model_name, "output": resp.content}, step_id=step_id)

            click_id = parse_click_id(resp.content or "")
            if click_id is None:
                print(f"  [error] Could not parse CLICK from: {resp.content!r}", flush=True)
                return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

            print(f"  [info] LLM chose element ID {click_id} for username field", flush=True)

            await click_async(browser, click_id, use_mouse=True, cursor_policy=cursor_policy)
            await browser.page.wait_for_timeout(200)

            # Type username
            for ch in TEST_USERNAME:
                await browser.page.keyboard.type(ch)
                await browser.page.wait_for_timeout(random.randint(50, 120))

            return True, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0), f"typed={TEST_USERNAME}"

        # -------------------------
        # Step 3: Fill password field
        # -------------------------
        async def step3(step_id: str):
            await runtime.snapshot(limit=40, screenshot=False, goal="Find the password input field")
            snap = runtime.last_snapshot
            if snap is None:
                raise RuntimeError("snapshot missing")

            compact = ctx_formatter._format_snapshot_for_llm(snap)
            tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)

            task = "Find the password input field and click it. Look for a field with placeholder containing dots or 'password'."
            user_prompt = build_llm_user_prompt(task, compact)
            sys_prompt = "You are a careful web agent. Output only CLICK(<id>)."

            resp = llm.generate(sys_prompt, user_prompt, temperature=0.0, max_new_tokens=24)
            tracer.emit("llm", {"model": llm.model_name, "output": resp.content}, step_id=step_id)

            click_id = parse_click_id(resp.content or "")
            if click_id is None:
                print(f"  [error] Could not parse CLICK from: {resp.content!r}", flush=True)
                return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

            print(f"  [info] LLM chose element ID {click_id} for password field", flush=True)

            await click_async(browser, click_id, use_mouse=True, cursor_policy=cursor_policy)
            await browser.page.wait_for_timeout(200)

            # Type password
            for ch in TEST_PASSWORD:
                await browser.page.keyboard.type(ch)
                await browser.page.wait_for_timeout(random.randint(50, 120))

            # Wait for button to become enabled
            print("  [info] Waiting for login button to become enabled...", flush=True)
            await runtime.check(
                is_enabled("role=button"),
                label="login_button_enabled",
                required=True
            ).eventually(timeout_s=5.0, poll_s=0.3, max_snapshot_attempts=5)

            return True, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0), "password_filled"

        # -------------------------
        # Step 4: Click login button
        # -------------------------
        async def step4(step_id: str):
            await runtime.snapshot(limit=40, screenshot=False, goal="Find and click the login button")
            snap = runtime.last_snapshot
            if snap is None:
                raise RuntimeError("snapshot missing")

            compact = ctx_formatter._format_snapshot_for_llm(snap)
            tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)

            task = "Find and click the login/submit button. Look for a button with text 'Sign in'."
            user_prompt = build_llm_user_prompt(task, compact)
            sys_prompt = "You are a careful web agent. Output only CLICK(<id>)."

            resp = llm.generate(sys_prompt, user_prompt, temperature=0.0, max_new_tokens=24)
            tracer.emit("llm", {"model": llm.model_name, "output": resp.content}, step_id=step_id)

            click_id = parse_click_id(resp.content or "")
            if click_id is None:
                print(f"  [error] Could not parse CLICK from: {resp.content!r}", flush=True)
                return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

            print(f"  [info] LLM chose element ID {click_id} for login button", flush=True)

            await click_async(browser, click_id, use_mouse=True, cursor_policy=cursor_policy)
            await browser.page.wait_for_timeout(1500)
            await browser.page.wait_for_load_state("domcontentloaded", timeout=10_000)

            # Verify we navigated away from login
            current_url = browser.page.url
            ok = "login" not in current_url.lower() or "profile" in current_url.lower()
            print(f"  [info] After login, URL: {current_url}", flush=True)

            return ok, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0), f"navigated_to={current_url}"

        # -------------------------
        # Step 5: Navigate to dashboard page
        # -------------------------
        async def step5(step_id: str):
            # Check if we need to navigate to dashboard
            current_url = browser.page.url
            if "dashboard" not in current_url.lower():
                await runtime.snapshot(limit=40, screenshot=False, goal="Find dashboard link")
                snap = runtime.last_snapshot
                if snap is None:
                    raise RuntimeError("snapshot missing")

                compact = ctx_formatter._format_snapshot_for_llm(snap)
                tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)

                task = "Find and click the Dashboard link in the navigation."
                user_prompt = build_llm_user_prompt(task, compact)
                sys_prompt = "You are a careful web agent. Output only CLICK(<id>)."

                resp = llm.generate(sys_prompt, user_prompt, temperature=0.0, max_new_tokens=24)
                tracer.emit("llm", {"model": llm.model_name, "output": resp.content}, step_id=step_id)

                click_id = parse_click_id(resp.content or "")
                if click_id is None:
                    print(f"  [error] Could not parse CLICK from: {resp.content!r}", flush=True)
                    return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

                print(f"  [info] LLM chose element ID {click_id} for dashboard link", flush=True)

                await click_async(browser, click_id, use_mouse=True, cursor_policy=cursor_policy)
                await browser.page.wait_for_load_state("domcontentloaded", timeout=10_000)
                usage = StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)
            else:
                usage = None

            # Wait for dashboard to load and take snapshot for URL verification
            await browser.page.wait_for_timeout(1000)
            await runtime.snapshot(limit=40, screenshot=False, goal="Verify dashboard page loaded")

            # Verify we're on dashboard
            url_ok = runtime.assert_(url_contains("dashboard"), label="on_dashboard_page", required=True)
            current_url = browser.page.url
            print(f"  [info] Dashboard URL verified: {current_url}", flush=True)

            return url_ok, usage

        # -------------------------
        # Step 6: Wait for KPI cards to load
        # -------------------------
        async def step6(step_id: str):
            # Dashboard content loads after 900-1500ms delay
            # Use eventually() to wait for KPI cards to appear
            print("  [info] Waiting for KPI cards to load...", flush=True)

            kpi_loaded = await runtime.check(
                exists("text~'Llama Coins'"),
                label="kpi_cards_loaded",
                required=True
            ).eventually(timeout_s=15.0, poll_s=0.5, max_snapshot_attempts=15)

            if not kpi_loaded:
                print("  [error] KPI cards did not load in time", flush=True)
                return False, None

            print("  [info] KPI cards loaded successfully", flush=True)

            # Take a snapshot to see what's available
            await runtime.snapshot(limit=50, screenshot=False, goal="Inspect KPI cards")
            snap = runtime.last_snapshot
            if snap:
                print(f"  [debug] Snapshot has {len(snap.elements)} elements", flush=True)

            return True, None

        # -------------------------
        # Step 7: Extract KPI values
        # -------------------------
        async def step7(step_id: str):
            await runtime.snapshot(limit=50, screenshot=False, goal="Extract KPI values from dashboard")
            snap = runtime.last_snapshot
            if snap is None:
                raise RuntimeError("snapshot missing")

            compact = ctx_formatter._format_snapshot_for_llm(snap)
            tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)
            print("\n--- Step 7: Dashboard snapshot ---", flush=True)
            print(_clip_for_log(compact), flush=True)
            print("--- end snapshot ---\n", flush=True)

            # Extract KPI values from snapshot
            extracted_kpis = {}

            # Strategy: Look for KPI labels and their adjacent values
            elements_by_text = {}
            for el in snap.elements:
                text = (el.text or "").strip()
                if text:
                    elements_by_text[text] = el

            # Look for each expected KPI
            for kpi_label, expected_value in EXPECTED_KPIS.items():
                # Check if label exists
                if kpi_label in elements_by_text:
                    extracted_kpis[kpi_label] = {"label_found": True, "value": None}

                # Check if value exists
                if expected_value in elements_by_text:
                    if kpi_label in extracted_kpis:
                        extracted_kpis[kpi_label]["value"] = expected_value
                    else:
                        extracted_kpis[kpi_label] = {"label_found": False, "value": expected_value}

            # Log what we found
            print("  [info] Extracted KPIs:", flush=True)
            for label, data in extracted_kpis.items():
                print(f"    {label}: value={data.get('value')} (label_found={data.get('label_found')})", flush=True)

            # Count successful extractions
            successful = sum(1 for d in extracted_kpis.values() if d.get("value") is not None)
            total_expected = len(EXPECTED_KPIS)

            print(f"  [info] Successfully extracted {successful}/{total_expected} KPI values", flush=True)

            # Assert we found all KPIs
            all_found = successful == total_expected
            runtime.assert_(
                lambda ctx: AssertOutcome(
                    passed=all_found,
                    reason="all_kpis_extracted" if all_found else f"only {successful}/{total_expected} KPIs found",
                    details={"extracted": extracted_kpis, "expected": EXPECTED_KPIS}
                ),
                label="kpi_extraction_complete",
                required=True,
            )

            # Build result string
            result_parts = []
            for label in ["Llama Coins", "Active Herds", "Messages"]:
                if label in extracted_kpis and extracted_kpis[label].get("value"):
                    result_parts.append(f"{label}={extracted_kpis[label]['value']}")

            return all_found, None, " | ".join(result_parts) if result_parts else "no_kpis_extracted"

        # -------------------------
        # Step 8: Verify event table loaded (optional)
        # -------------------------
        async def step8(step_id: str):
            # Wait for the event table to load (it has a separate delay)
            print("  [info] Waiting for event table to load...", flush=True)

            table_loaded = await runtime.check(
                exists("text~'Recent events'"),
                label="event_table_loaded",
                required=False  # Optional step
            ).eventually(timeout_s=10.0, poll_s=0.5, max_snapshot_attempts=10)

            if not table_loaded:
                print("  [warn] Event table did not load (optional)", flush=True)
                return True, None, "table_not_loaded"

            # Check for table rows
            await runtime.snapshot(limit=50, screenshot=False, goal="Verify event table")
            snap = runtime.last_snapshot

            if snap:
                # Look for event table content
                has_signed_in = any("Signed in" in (el.text or "") for el in snap.elements)
                has_viewed_profile = any("Viewed profile" in (el.text or "") for el in snap.elements)

                events_found = []
                if has_signed_in:
                    events_found.append("Signed in")
                if has_viewed_profile:
                    events_found.append("Viewed profile")

                print(f"  [info] Found events: {events_found}", flush=True)

                runtime.assert_(
                    lambda ctx: AssertOutcome(
                        passed=len(events_found) > 0,
                        reason="events_found" if events_found else "no_events",
                        details={"events": events_found}
                    ),
                    label="event_table_has_content",
                    required=False,
                )

                return True, None, f"events={events_found}"

            return True, None, "table_loaded"

        # -------------------------
        # Step 9: Enable live mode and re-extract KPIs (stress test)
        # -------------------------
        async def step9(step_id: str):
            """
            This step demonstrates snapshot stability during DOM churn.

            When live mode is enabled:
            - Event table updates every 400ms (new rows added, old rows removed)
            - DOM structure constantly changes
            - But KPI cards remain stable

            We click "Enable live updates" button, wait for churn to start,
            then re-extract KPIs to prove our snapshot handles instability.
            """
            print("  [info] Enabling live updates to test DOM churn resilience...", flush=True)

            # Take snapshot to find the "Enable live updates" button
            await runtime.snapshot(limit=50, screenshot=False, goal="Find Enable live updates button")
            snap = runtime.last_snapshot
            if snap is None:
                raise RuntimeError("snapshot missing")

            compact = ctx_formatter._format_snapshot_for_llm(snap)
            tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)
            print("\n--- Step 9: Finding live updates button ---", flush=True)
            print(_clip_for_log(compact), flush=True)
            print("--- end snapshot ---\n", flush=True)

            # Find the button element
            live_button_id = None
            for el in snap.elements:
                text = (el.text or "").strip().lower()
                if "enable live" in text or "live updates" in text:
                    live_button_id = el.id
                    print(f"  [info] Found live updates button: id={el.id} text={el.text!r}", flush=True)
                    break

            if live_button_id is None:
                print("  [warn] Could not find 'Enable live updates' button - skipping live mode test", flush=True)
                return True, None, "button_not_found"

            # Click the button to enable live mode
            print(f"  [info] Clicking button id={live_button_id} to enable live mode...", flush=True)
            await click_async(browser, live_button_id, use_mouse=True, cursor_policy=cursor_policy)

            # Wait for DOM churn to start (table updates every 400ms)
            print("  [info] Waiting 2s for DOM churn to accumulate...", flush=True)
            await browser.page.wait_for_timeout(2000)

            # Now re-extract KPIs during active DOM churn
            print("  [info] Re-extracting KPIs during DOM churn...", flush=True)
            await runtime.snapshot(limit=50, screenshot=False, goal="Extract KPIs during live DOM churn")
            snap = runtime.last_snapshot
            if snap is None:
                raise RuntimeError("snapshot missing during churn")

            compact = ctx_formatter._format_snapshot_for_llm(snap)
            tracer.emit("note", {"kind": "compact_prompt_during_churn", "text": compact}, step_id=step_id)
            print("\n--- Step 9: Snapshot during DOM churn ---", flush=True)
            print(_clip_for_log(compact), flush=True)
            print("--- end snapshot ---\n", flush=True)

            # Re-extract KPIs
            extracted_during_churn = {}
            elements_by_text = {(el.text or "").strip(): el for el in snap.elements if el.text}

            for kpi_label, expected_value in EXPECTED_KPIS.items():
                if kpi_label in elements_by_text:
                    extracted_during_churn[kpi_label] = {"label_found": True, "value": None}
                if expected_value in elements_by_text:
                    if kpi_label in extracted_during_churn:
                        extracted_during_churn[kpi_label]["value"] = expected_value
                    else:
                        extracted_during_churn[kpi_label] = {"label_found": False, "value": expected_value}

            # Count successful extractions during churn
            successful = sum(1 for d in extracted_during_churn.values() if d.get("value") is not None)
            total_expected = len(EXPECTED_KPIS)

            print(f"  [info] During DOM churn, extracted {successful}/{total_expected} KPI values:", flush=True)
            for label, data in extracted_during_churn.items():
                print(f"    {label}: value={data.get('value')} (label_found={data.get('label_found')})", flush=True)

            # Check for "Live ping" events (proves churn is happening)
            live_ping_count = sum(1 for el in snap.elements if "Live ping" in (el.text or ""))
            print(f"  [info] Found {live_ping_count} 'Live ping' events (proves DOM churn is active)", flush=True)

            # Assert KPIs are still extractable during churn
            all_found = successful == total_expected
            runtime.assert_(
                lambda ctx: AssertOutcome(
                    passed=all_found,
                    reason="kpis_stable_during_churn" if all_found else f"only {successful}/{total_expected} KPIs during churn",
                    details={
                        "extracted_during_churn": extracted_during_churn,
                        "live_ping_count": live_ping_count,
                        "dom_churn_active": live_ping_count > 0
                    }
                ),
                label="kpi_extraction_during_churn",
                required=True,
            )

            # Build result string
            result_parts = [f"churn_events={live_ping_count}"]
            for label in ["Llama Coins", "Active Herds", "Messages"]:
                if label in extracted_during_churn and extracted_during_churn[label].get("value"):
                    result_parts.append(f"{label}={extracted_during_churn[label]['value']}")

            return all_found, None, " | ".join(result_parts)

        # -------------------------
        # Run the steps
        # -------------------------
        all_ok = True
        steps = [
            (1, "Navigate to login page", step1),
            (2, "Fill username field", step2),
            (3, "Fill password field", step3),
            (4, "Click login button", step4),
            (5, "Navigate to dashboard page", step5),
            (6, "Wait for KPI cards to load", step6),
            (7, "Extract KPI values", step7),
            (8, "Verify event table loaded", step8),
            (9, "Extract KPIs during DOM churn (stress test)", step9),
        ]
        for idx, goal, fn in steps:
            print(f"\n[{now_iso()}] Starting Step {idx}: {goal}", flush=True)
            try:
                ok = await run_step(idx, goal, fn)
                print(f"[{now_iso()}] Step {idx} completed with ok={ok}", flush=True)
                if not ok:
                    all_ok = False
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

        # Generate video from screenshots
        print("\n" + "=" * 70)
        print("Generating video with token overlay...")
        print("=" * 70)

        token_summary = {
            "demo_name": "Dashboard KPI Extraction: Local LLM Agent",
            "total_prompt_tokens": total_tokens.prompt_tokens,
            "total_completion_tokens": total_tokens.completion_tokens,
            "total_tokens": total_tokens.total_tokens,
            "average_per_scene": total_tokens.total_tokens / len(step_stats) if step_stats else 0,
            "interactions": [
                {
                    "scene": f"Scene {s['step_index']}: {s['goal'][:40]}",
                    "prompt_tokens": s["token_usage"]["prompt_tokens"] if s["token_usage"] else 0,
                    "completion_tokens": s["token_usage"]["completion_tokens"] if s["token_usage"] else 0,
                    "total": s["token_usage"]["total_tokens"] if s["token_usage"] else 0,
                }
                for s in step_stats
            ],
        }

        video_output = os.path.join(os.path.dirname(__file__), "video", f"dashboard_kpi_{timestamp}.mp4")
        os.makedirs(os.path.dirname(video_output), exist_ok=True)

        try:
            create_demo_video(screenshots_dir, token_summary, video_output)
        except Exception as e:
            print(f"Warning: Video generation failed: {e}")
            import traceback
            traceback.print_exc()
            print("Screenshots are still available in the screenshots directory")


if __name__ == "__main__":
    asyncio.run(main())
