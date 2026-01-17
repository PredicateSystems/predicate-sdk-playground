"""
Demo 5: Form Validation + Submission on Local Llama Land

This demo navigates to the onboarding form page of a fake Next.js site
(https://sentience-sdk-playground.vercel.app/forms/onboarding) and completes
a multi-step form with validation gating at each step.

Why high impact:
Multi-step forms with validation are common in real-world applications.
This demo showcases state-aware assertions (enabled/disabled, value validation)
and proves the agent can handle complex form flows deterministically.

Site Characteristics (intentional challenges):
- MULTI-STEP FORM: 4 steps with validation gating each step
  → We assert button state (disabled → enabled) at each step
- STEP 1: Email validation (must be valid email format)
  → Next button disabled until email contains @ and valid format
- STEP 2: Display name validation (must be >= 2 characters)
  → Next button disabled until name length >= 2
- STEP 3: Plan selection (radio) + Terms checkbox
  → Next button disabled until both plan selected AND terms checked
- STEP 4: Review + Submit with CAPTCHA placeholder
  → Submit button disabled until form is ready
- ARTIFICIAL DELAYS: Each step transition has 450-1100ms delay
  → We use eventually() to wait for state transitions
- SUCCESS MESSAGE: Appears after submit with 900-1800ms delay
  → We wait for success message with eventually()

Flow:
1. Navigate to onboarding form page → wait for form hydration
2. Fill email field (Step 1) → verify Next button becomes enabled
3. Click Next → wait for step transition, verify on Step 2
4. Fill display name (Step 2) → verify Next button becomes enabled
5. Click Next → wait for step transition, verify on Step 3
6. Select plan (radio) → verify selection
7. Check Terms checkbox → verify Next button becomes enabled
8. Click Next → wait for step transition, verify on Step 4 (Review)
9. Click Submit → wait for success message
10. Verify success message appears → "Success! Your profile is ready."

This demo showcases:
- State-aware assertions (is_enabled, is_disabled, value_equals, is_checked)
- Multi-step form navigation with validation gating
- Retry semantics with eventually() for state transitions
- Local LLM for element identification (Qwen 2.5 3B)
- Human-like cursor movement and typing
- Cloud tracing for debugging and replay

Key features demonstrated:
- Validation gating: Assert button state at each step
- Value verification: Check field values match expected
- Radio/checkbox selection: Verify selection state
- Success verification: Wait for and verify success message
- Token usage tracking: Per-step breakdown for cost analysis
"""
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

# Import shared video utilities from amazon_shopping
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "amazon_shopping", "shared"))
from video_generator_simple import create_demo_video

from sentience.actions import click_async, type_text_async
from sentience.async_api import AsyncSentienceBrowser
from sentience.backends.playwright_backend import PlaywrightBackend
from sentience.backends.sentience_context import SentienceContext
from sentience.cursor_policy import CursorPolicy
from sentience.models import SnapshotOptions
from sentience.tracer_factory import create_tracer
from sentience.verification import (
    AssertOutcome,
    exists,
    url_contains,
    is_enabled,
    is_disabled,
    value_contains,
    is_checked,
)
from sentience.agent_runtime import AgentRuntime
from sentience.llm_provider import LocalLLMProvider


# Test form data
TEST_EMAIL = "testuser@localllama.land"
TEST_NAME = "Llama Rider"
TEST_PLAN = "pro"  # or "free"


@dataclass
class StepTokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
        "- role: Element type (link, button, textbox, radio, checkbox, etc.)\n"
        "- text: Visible text content\n"
        "- importance: Importance score (higher = more important)\n"
        "- is_primary: 1 if primary action, 0 otherwise\n"
        "- docYq: Vertical position bucket\n"
        "- ord: Rank in dominant group (0 = first)\n"
        "- DG: 1 if in dominant group, 0 otherwise\n"
        "- href: URL if link element\n\n"
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
    task_goal = "Form Validation + Submission: Complete multi-step onboarding form with validation gating"
    snapshot_goal = "Find form elements and interact with them"
    start_ts = time.time()
    run_id = str(uuid.uuid4())

    sentience_api_key = os.getenv("SENTIENCE_API_KEY")
    use_api = bool((sentience_api_key or "").strip())

    # Tier 1: local text LLM (HF transformers)
    local_text_model = os.getenv("LOCAL_TEXT_MODEL") or "Qwen/Qwen2.5-3B-Instruct"
    llm = LocalLLMProvider(model_name=local_text_model, device="auto", load_in_4bit=False)
    print(f"  LLM initialized: {llm.model_name}")

    # Cloud tracing
    tracer = create_tracer(
        api_key=sentience_api_key,
        run_id=run_id,
        upload_trace=bool(sentience_api_key),
        goal=task_goal,
        agent_type="public_build/form_validation_submission",
        llm_model=local_text_model,
        start_url="https://sentience-sdk-playground.vercel.app/forms/onboarding",
    )
    tracer.emit_run_start(agent="FormValidationSubmissionDemo", llm_model=local_text_model, config={})

    # Screenshot directory for video recording
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshots_dir = os.path.join(os.path.dirname(__file__), "screenshots", timestamp)
    os.makedirs(screenshots_dir, exist_ok=True)
    print(f"Screenshots will be saved to: {screenshots_dir}")

    print(f"[{now_iso()}] Starting Demo 5: Form Validation + Submission")
    print(f"  Model: {local_text_model}")
    print(f"  Use API: {use_api}")
    print(f"  Test email: {TEST_EMAIL}")
    print(f"  Test name: {TEST_NAME}")
    print(f"  Test plan: {TEST_PLAN}")
    print(f"  Tracer run_id: {run_id}")

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
        # Step 1: Navigate to onboarding form page
        # -------------------------
        async def step1(_step_id: str):
            await browser.goto("https://sentience-sdk-playground.vercel.app/forms/onboarding")
            await browser.page.wait_for_load_state("domcontentloaded", timeout=10_000)

            current_url = browser.page.url
            print(f"  [debug] Browser URL after navigation: {current_url}", flush=True)

            # Wait for form to hydrate (may have delayed hydration)
            print("  [info] Waiting for onboarding form hydration...", flush=True)
            form_loaded = await runtime.check(
                exists("text~'Onboarding'"),
                label="onboarding_form_hydrated",
                required=True,
            ).eventually(timeout_s=15.0, poll_s=0.5, max_snapshot_attempts=15)

            if not form_loaded:
                print("  [error] Onboarding form did not hydrate in time", flush=True)
                return False, None

            print("  [info] Onboarding form hydrated successfully", flush=True)

            # Verify we're on the onboarding page
            url_ok = runtime.assert_(url_contains("onboarding"), label="on_onboarding_page", required=True)
            if not url_ok:
                print(f"  [error] Not on onboarding page. URL: {current_url}", flush=True)
                return False, None

            # Verify we're on Step 1 (should show "Step 1 / 4")
            step1_ok = runtime.assert_(exists("text~'Step 1 / 4'"), label="on_step_1", required=True)
            if not step1_ok:
                print("  [error] Not on Step 1", flush=True)
                return False, None

            # Verify Next button is initially DISABLED (email field is empty)
            disabled_ok = runtime.assert_(
                is_disabled("role=button text~'Next'"), label="next_button_disabled_initially", required=False
            )
            if disabled_ok:
                print("  [info] Next button is DISABLED initially (as expected)", flush=True)

            return True, None

        # -------------------------
        # Step 2: Fill email field (Step 1 of form)
        # -------------------------
        async def step2(step_id: str):
            await runtime.snapshot(limit=50, screenshot=False, goal="Find the email input field")
            snap = runtime.last_snapshot
            if snap is None:
                raise RuntimeError("snapshot missing")

            compact = ctx_formatter._format_snapshot_for_llm(snap)
            tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)
            print("\n--- Step 2: LLM compact prompt ---", flush=True)
            print(_clip_for_log(compact), flush=True)
            print("--- end compact prompt ---\n", flush=True)

            task = (
                "Find the email input field (role='textbox' or role='textbox') and click it.\n"
                "Look for a field with label 'Email' or placeholder containing 'email' or '@'."
            )
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

            click_id = parse_click_id(resp.content or "")
            if click_id is None:
                print(f"  [error] Could not parse CLICK from: {resp.content!r}", flush=True)
                return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

            print(f"  [info] LLM chose element ID {click_id} for email field", flush=True)

            # Click the email field
            await click_async(browser, click_id, use_mouse=True, cursor_policy=cursor_policy)
            await browser.page.wait_for_timeout(200)

            # Clear any existing text first
            await browser.page.keyboard.press("Control+A")
            await browser.page.wait_for_timeout(100)

            # Type email with human-like delays
            for ch in TEST_EMAIL:
                await browser.page.keyboard.type(ch)
                await browser.page.wait_for_timeout(random.randint(50, 120))

            # Wait a moment for validation to run
            await browser.page.wait_for_timeout(300)

            # Verify email value was entered
            await runtime.snapshot()
            value_ok = runtime.assert_(
                value_contains("name=email", "@"), label="email_contains_at_symbol", required=True
            )
            if not value_ok:
                print("  [warn] Could not verify email value", flush=True)

            # Verify Next button becomes ENABLED after valid email
            print("  [info] Waiting for Next button to become enabled...", flush=True)
            enabled_ok = await runtime.check(
                is_enabled("role=button text~'Next'"),
                label="next_button_enabled_after_email",
                required=True,
            ).eventually(timeout_s=5.0, poll_s=0.3, max_snapshot_attempts=5)

            if enabled_ok:
                print("  [info] Next button is now ENABLED after entering valid email", flush=True)
            else:
                print("  [warn] Next button may not be enabled", flush=True)

            return True, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0), f"email={TEST_EMAIL}"

        # -------------------------
        # Step 3: Click Next to go to Step 2
        # -------------------------
        async def step3(step_id: str):
            await runtime.snapshot(limit=50, screenshot=False, goal="Click Next button to proceed to Step 2")
            snap = runtime.last_snapshot
            if snap is None:
                raise RuntimeError("snapshot missing")

            # Verify Next button is enabled before clicking
            enabled_ok = runtime.assert_(
                is_enabled("role=button text~'Next'"), label="next_button_enabled_before_click", required=True
            )
            if not enabled_ok:
                print("  [error] Next button is not enabled", flush=True)
                return False, None

            compact = ctx_formatter._format_snapshot_for_llm(snap)
            tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)
            print("\n--- Step 3: LLM compact prompt ---", flush=True)
            print(_clip_for_log(compact), flush=True)
            print("--- end compact prompt ---\n", flush=True)

            task = "Find and click the 'Next' button to proceed to the next step of the form."
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

            click_id = parse_click_id(resp.content or "")
            if click_id is None:
                return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

            print(f"  [info] LLM chose element ID {click_id} for Next button", flush=True)

            # Click Next button
            await click_async(browser, click_id, use_mouse=True, cursor_policy=cursor_policy)

            # Wait for step transition (form has 450-1100ms delay)
            await browser.page.wait_for_timeout(1200)

            # Verify we're now on Step 2
            step2_ok = await runtime.check(
                exists("text~'Step 2 / 4'"), label="on_step_2", required=True
            ).eventually(timeout_s=5.0, poll_s=0.3, max_snapshot_attempts=5)

            if not step2_ok:
                print("  [error] Did not transition to Step 2", flush=True)
                return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

            print("  [info] Successfully transitioned to Step 2", flush=True)

            # Verify Next button is DISABLED initially (name field is empty)
            disabled_ok = runtime.assert_(
                is_disabled("role=button text~'Next'"), label="next_button_disabled_on_step2_initially", required=False
            )
            if disabled_ok:
                print("  [info] Next button is DISABLED on Step 2 initially (as expected)", flush=True)

            return True, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

        # -------------------------
        # Step 4: Fill display name field (Step 2 of form)
        # -------------------------
        async def step4(step_id: str):
            await runtime.snapshot(limit=50, screenshot=False, goal="Find the display name input field")
            snap = runtime.last_snapshot
            if snap is None:
                raise RuntimeError("snapshot missing")

            compact = ctx_formatter._format_snapshot_for_llm(snap)
            tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)
            print("\n--- Step 4: LLM compact prompt ---", flush=True)
            print(_clip_for_log(compact), flush=True)
            print("--- end compact prompt ---\n", flush=True)

            task = (
                "Find the display name input field (role='textbox') and click it.\n"
                "Look for a field with label 'Display name' or placeholder containing 'name'."
            )
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

            click_id = parse_click_id(resp.content or "")
            if click_id is None:
                return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

            print(f"  [info] LLM chose element ID {click_id} for display name field", flush=True)

            # Click the display name field
            await click_async(browser, click_id, use_mouse=True, cursor_policy=cursor_policy)
            await browser.page.wait_for_timeout(200)

            # Clear any existing text
            await browser.page.keyboard.press("Control+A")
            await browser.page.wait_for_timeout(100)

            # Type name with human-like delays
            for ch in TEST_NAME:
                await browser.page.keyboard.type(ch)
                await browser.page.wait_for_timeout(random.randint(50, 120))

            # Wait for validation
            await browser.page.wait_for_timeout(300)

            # Verify name value was entered (must be >= 2 chars)
            await runtime.snapshot()
            value_ok = runtime.assert_(
                value_contains("name=display_name", TEST_NAME[:2]), label="name_contains_expected_text", required=True
            )
            if not value_ok:
                print("  [warn] Could not verify name value", flush=True)

            # Verify Next button becomes ENABLED after valid name
            print("  [info] Waiting for Next button to become enabled...", flush=True)
            enabled_ok = await runtime.check(
                is_enabled("role=button text~'Next'"),
                label="next_button_enabled_after_name",
                required=True,
            ).eventually(timeout_s=5.0, poll_s=0.3, max_snapshot_attempts=5)

            if enabled_ok:
                print("  [info] Next button is now ENABLED after entering valid name", flush=True)

            return True, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0), f"name={TEST_NAME}"

        # -------------------------
        # Step 5: Click Next to go to Step 3
        # -------------------------
        async def step5(step_id: str):
            await runtime.snapshot(limit=50, screenshot=False, goal="Click Next button to proceed to Step 3")
            snap = runtime.last_snapshot
            if snap is None:
                raise RuntimeError("snapshot missing")

            enabled_ok = runtime.assert_(
                is_enabled("role=button text~'Next'"), label="next_button_enabled_before_click_step3", required=True
            )
            if not enabled_ok:
                return False, None

            compact = ctx_formatter._format_snapshot_for_llm(snap)
            tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)
            print("\n--- Step 5: LLM compact prompt ---", flush=True)
            print(_clip_for_log(compact), flush=True)
            print("--- end compact prompt ---\n", flush=True)

            task = "Find and click the 'Next' button to proceed to Step 3."
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

            click_id = parse_click_id(resp.content or "")
            if click_id is None:
                return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

            await click_async(browser, click_id, use_mouse=True, cursor_policy=cursor_policy)
            await browser.page.wait_for_timeout(1200)

            # Verify we're on Step 3
            step3_ok = await runtime.check(
                exists("text~'Step 3 / 4'"), label="on_step_3", required=True
            ).eventually(timeout_s=5.0, poll_s=0.3, max_snapshot_attempts=5)

            if not step3_ok:
                return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

            print("  [info] Successfully transitioned to Step 3", flush=True)

            # Verify Next button is DISABLED initially (plan not selected, terms not checked)
            disabled_ok = runtime.assert_(
                is_disabled("role=button text~'Next'"), label="next_button_disabled_on_step3_initially", required=False
            )
            if disabled_ok:
                print("  [info] Next button is DISABLED on Step 3 initially (as expected)", flush=True)

            return True, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

        # -------------------------
        # Step 6: Select plan (radio button)
        # -------------------------
        async def step6(step_id: str):
            await runtime.snapshot(limit=50, screenshot=False, goal="Find and select plan radio button")
            snap = runtime.last_snapshot
            if snap is None:
                raise RuntimeError("snapshot missing")

            compact = ctx_formatter._format_snapshot_for_llm(snap)
            tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)
            print("\n--- Step 6: LLM compact prompt ---", flush=True)
            print(_clip_for_log(compact), flush=True)
            print("--- end compact prompt ---\n", flush=True)

            task = (
                f"Find and click the '{TEST_PLAN}' plan radio button.\n"
                "Look for a radio button (role='radio') with value matching the plan name."
            )
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

            click_id = parse_click_id(resp.content or "")
            if click_id is None:
                return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

            print(f"  [info] LLM chose element ID {click_id} for {TEST_PLAN} plan", flush=True)

            # Click the radio button
            await click_async(browser, click_id, use_mouse=True, cursor_policy=cursor_policy)
            await browser.page.wait_for_timeout(300)

            # Verify plan is selected
            await runtime.snapshot()
            checked_ok = runtime.assert_(
                is_checked(f"name=plan value={TEST_PLAN}"), label=f"plan_{TEST_PLAN}_selected", required=True
            )
            if checked_ok:
                print(f"  [info] {TEST_PLAN.capitalize()} plan is selected", flush=True)

            # Next button should still be disabled (terms not checked yet)
            disabled_ok = runtime.assert_(
                is_disabled("role=button text~'Next'"), label="next_button_still_disabled_after_plan", required=False
            )
            if disabled_ok:
                print("  [info] Next button still DISABLED (terms not checked yet)", flush=True)

            return True, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0), f"plan={TEST_PLAN}"

        # -------------------------
        # Step 7: Check Terms checkbox
        # -------------------------
        async def step7(step_id: str):
            await runtime.snapshot(limit=50, screenshot=False, goal="Find and check Terms checkbox")
            snap = runtime.last_snapshot
            if snap is None:
                raise RuntimeError("snapshot missing")

            compact = ctx_formatter._format_snapshot_for_llm(snap)
            tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)
            print("\n--- Step 7: LLM compact prompt ---", flush=True)
            print(_clip_for_log(compact), flush=True)
            print("--- end compact prompt ---\n", flush=True)

            task = (
                "Find and click the Terms checkbox.\n"
                "Look for a checkbox (role='checkbox') with text containing 'Terms' or 'agree'."
            )
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

            click_id = parse_click_id(resp.content or "")
            if click_id is None:
                return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

            print(f"  [info] LLM chose element ID {click_id} for Terms checkbox", flush=True)

            # Click the checkbox
            await click_async(browser, click_id, use_mouse=True, cursor_policy=cursor_policy)
            await browser.page.wait_for_timeout(300)

            # Verify checkbox is checked
            await runtime.snapshot()
            checked_ok = runtime.assert_(
                is_checked("name=agree"), label="terms_checkbox_checked", required=True
            )
            if checked_ok:
                print("  [info] Terms checkbox is checked", flush=True)

            # Verify Next button becomes ENABLED after both plan and terms
            print("  [info] Waiting for Next button to become enabled...", flush=True)
            enabled_ok = await runtime.check(
                is_enabled("role=button text~'Next'"),
                label="next_button_enabled_after_plan_and_terms",
                required=True,
            ).eventually(timeout_s=5.0, poll_s=0.3, max_snapshot_attempts=5)

            if enabled_ok:
                print("  [info] Next button is now ENABLED after selecting plan and checking terms", flush=True)

            return True, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0), "terms_checked"

        # -------------------------
        # Step 8: Click Next to go to Step 4 (Review)
        # -------------------------
        async def step8(step_id: str):
            await runtime.snapshot(limit=50, screenshot=False, goal="Click Next button to proceed to Step 4 (Review)")
            snap = runtime.last_snapshot
            if snap is None:
                raise RuntimeError("snapshot missing")

            enabled_ok = runtime.assert_(
                is_enabled("role=button text~'Next'"), label="next_button_enabled_before_click_step4", required=True
            )
            if not enabled_ok:
                return False, None

            compact = ctx_formatter._format_snapshot_for_llm(snap)
            tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)
            print("\n--- Step 8: LLM compact prompt ---", flush=True)
            print(_clip_for_log(compact), flush=True)
            print("--- end compact prompt ---\n", flush=True)

            task = "Find and click the 'Next' button to proceed to Step 4 (Review)."
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

            click_id = parse_click_id(resp.content or "")
            if click_id is None:
                return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

            await click_async(browser, click_id, use_mouse=True, cursor_policy=cursor_policy)
            await browser.page.wait_for_timeout(1200)

            # Verify we're on Step 4 (Review)
            step4_ok = await runtime.check(
                exists("text~'Step 4 / 4'"), label="on_step_4_review", required=True
            ).eventually(timeout_s=5.0, poll_s=0.3, max_snapshot_attempts=5)

            if not step4_ok:
                return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

            print("  [info] Successfully transitioned to Step 4 (Review)", flush=True)

            # Verify review section shows our entered data
            review_ok = runtime.assert_(
                exists("text~'Review'"), label="review_section_visible", required=True
            )
            if review_ok:
                print("  [info] Review section is visible", flush=True)

            return True, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

        # -------------------------
        # Step 9: Click Submit button
        # -------------------------
        async def step9(step_id: str):
            await runtime.snapshot(limit=50, screenshot=False, goal="Click Submit button to complete form")
            snap = runtime.last_snapshot
            if snap is None:
                raise RuntimeError("snapshot missing")

            # Verify Submit button is enabled
            enabled_ok = runtime.assert_(
                is_enabled("role=button text~'Submit'"), label="submit_button_enabled", required=True
            )
            if not enabled_ok:
                print("  [error] Submit button is not enabled", flush=True)
                return False, None

            compact = ctx_formatter._format_snapshot_for_llm(snap)
            tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)
            print("\n--- Step 9: LLM compact prompt ---", flush=True)
            print(_clip_for_log(compact), flush=True)
            print("--- end compact prompt ---\n", flush=True)

            task = "Find and click the 'Submit' button to complete the form submission."
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

            click_id = parse_click_id(resp.content or "")
            if click_id is None:
                return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

            print(f"  [info] LLM chose element ID {click_id} for Submit button", flush=True)

            # Click Submit button
            await click_async(browser, click_id, use_mouse=True, cursor_policy=cursor_policy)

            # Wait for submission (form has 900-1800ms delay before success message)
            await browser.page.wait_for_timeout(2000)

            return True, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

        # -------------------------
        # Step 10: Verify success message
        # -------------------------
        async def step10(_step_id: str):
            # Wait for success message to appear (may take 900-1800ms)
            print("  [info] Waiting for success message...", flush=True)
            success_ok = await runtime.check(
                exists("text~'Success! Your profile is ready.'"),
                label="success_message_visible",
                required=True,
            ).eventually(timeout_s=5.0, poll_s=0.3, max_snapshot_attempts=10)

            if success_ok:
                print("  [info] Success message is visible!", flush=True)
                # Verify success message exists (the eventually() already verified it, but we assert it again for the step)
                runtime.assert_(
                    exists("text~'Success! Your profile is ready.'"),
                    label="form_submission_complete",
                    required=True,
                )
                # Mark task as done manually (since assert_done has a bug calling assertTrue instead of assert_)
                runtime._task_done = True
                runtime._task_done_label = "form_submission_complete"
                # Emit task_done verification event
                runtime.tracer.emit(
                    "verification",
                    data={
                        "kind": "task_done",
                        "passed": True,
                        "label": "form_submission_complete",
                    },
                    step_id=runtime.step_id,
                )
            else:
                print("  [error] Success message did not appear", flush=True)

            return success_ok, None

        # -------------------------
        # Run the steps
        # -------------------------
        all_ok = True
        steps = [
            (1, "Navigate to onboarding form page", step1),
            (2, "Fill email field", step2),
            (3, "Click Next to Step 2", step3),
            (4, "Fill display name field", step4),
            (5, "Click Next to Step 3", step5),
            (6, "Select plan (radio)", step6),
            (7, "Check Terms checkbox", step7),
            (8, "Click Next to Step 4 (Review)", step8),
            (9, "Click Submit button", step9),
            (10, "Verify success message", step10),
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
            "demo_name": "Form Validation + Submission: Local LLM Agent",
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

        video_output = os.path.join(os.path.dirname(__file__), "video", f"form_validation_{timestamp}.mp4")
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
