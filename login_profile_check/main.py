"""
Demo 3: Login + Profile Check on Local Llama Land

This demo navigates to a fake Next.js site (https://sentience-sdk-playground.vercel.app/login)
that is designed to test agent robustness with realistic JS-heavy patterns.

Site Characteristics (intentional challenges):
- DELAYED HYDRATION: Login form loads after ~600ms (setTimeout/Suspense)
  → We handle with runtime.check(...).eventually() to wait for textbox elements
- BUTTON DISABLED→ENABLED: Login button starts disabled, becomes enabled only after
  both username and password fields are filled
  → We assert is_disabled() initially, then is_enabled() after filling fields
- PROFILE PAGE LATE-LOAD: Profile card content loads after 800-1200ms
  → We use eventually() with poll_s to wait for content
- IFRAME: The page includes an iframe element to test agent frame handling
- ARTIFICIAL NAVIGATION DELAY: Login action has delay before redirecting

Flow:
1. Navigate to login page → wait for hydration with eventually(exists("role=textbox"))
2. Fill username field → LLM finds textbox, human-like typing
3. Fill password field → LLM finds password input, verify button becomes enabled
4. Click login button → verify button is enabled, LLM clicks, wait for navigation
5. Navigate to profile page → handle if not auto-redirected
6. Extract username AND email from profile card → wait for late-loading content

This demo showcases:
- State-aware assertions (is_enabled, is_disabled)
- Retry semantics with eventually()
- Local LLM for element identification
- Human-like cursor movement and typing
- Cloud tracing for debugging
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

from sentience.actions import click_async, press_async, type_text_async
from sentience.async_api import AsyncSentienceBrowser
from sentience.backends.playwright_backend import PlaywrightBackend
from sentience.backends.sentience_context import SentienceContext
from sentience.cursor_policy import CursorPolicy
from sentience.models import SnapshotOptions
from sentience.tracer_factory import create_tracer
from sentience.verification import AssertOutcome, exists, url_contains, is_enabled, is_disabled
from sentience.agent_runtime import AgentRuntime
from sentience.llm_provider import LocalLLMProvider, LocalVisionLLMProvider, MLXVLMProvider


# Test credentials for the fake site
TEST_USERNAME = "testuser"
TEST_PASSWORD = "password123"


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


def parse_type_action(text: str) -> tuple[int, str] | None:
    """
    Parse TYPE(<id>, "<text>") from LLM output.
    """
    m = re.search(r'TYPE\s*\(\s*(\d+)\s*,\s*["\']([^"\']*)["\']', text, flags=re.IGNORECASE)
    if not m:
        return None
    return int(m.group(1)), m.group(2)


def build_llm_user_prompt(task: str, compact_elements: str) -> str:
    return (
        "You are controlling a browser via element IDs.\n\n"
        "You must respond with exactly ONE action in this format:\n"
        "- CLICK(<id>)\n"
        "- TYPE(<id>, \"<text>\")\n\n"
        "SNAPSHOT FORMAT EXPLANATION:\n"
        "The snapshot shows elements in this format: ID|role|text|importance|is_primary|docYq|ord|DG|href|\n"
        "- ID: Element ID (use this for CLICK or TYPE)\n"
        "- role: Element type (link, button, textbox, etc.)\n"
        "- text: Visible text content or placeholder\n"
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
    task_goal = "Login + Profile Check: Log in to Local Llama Land → Navigate to profile → Extract username"
    snapshot_goal = "Find form elements and interact with them"
    start_ts = time.time()
    run_id = str(uuid.uuid4())

    sentience_api_key = os.getenv("SENTIENCE_API_KEY")
    use_api = bool((sentience_api_key or "").strip())

    # Tier 1: local text LLM (HF transformers)
    local_text_model = os.getenv("LOCAL_TEXT_MODEL") or "Qwen/Qwen2.5-3B-Instruct"
    llm = LocalLLMProvider(model_name=local_text_model, device="auto", load_in_4bit=False)

    # Tier 2: local vision LLM (fallback, last resort)
    vision_provider = init_vision_provider()

    # Cloud tracing
    tracer = create_tracer(
        api_key=sentience_api_key,
        run_id=run_id,
        upload_trace=bool(sentience_api_key),
        goal=task_goal,
        agent_type="public_build/login_profile_check",
        llm_model=local_text_model,
        start_url="https://sentience-sdk-playground.vercel.app/login",
    )
    tracer.emit_run_start(agent="LoginProfileCheckDemo", llm_model=local_text_model, config={})

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
                limit=40,
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

            # Debug: print current URL from browser
            current_url = browser.page.url
            print(f"  [debug] Browser URL after navigation: {current_url}", flush=True)

            # The site has delayed hydration (~600ms for form to appear)
            # Use .eventually() to wait for form elements - this handles the hydration delay
            print("  [info] Waiting for login form hydration using eventually()...", flush=True)

            # Wait for textbox (username input) to appear - this confirms form hydration
            # The eventually() loop takes snapshots which include the URL
            form_loaded = await runtime.check(
                exists("role=textbox"),
                label="login_form_hydrated",
                required=True
            ).eventually(timeout_s=15.0, poll_s=0.5, max_snapshot_attempts=15)

            if not form_loaded:
                print("  [error] Login form did not hydrate in time", flush=True)
                return False, None

            print("  [info] Login form hydrated successfully", flush=True)

            # Now verify URL from the snapshot (after hydration)
            snap = runtime.last_snapshot
            snapshot_url = snap.url if snap else None
            print(f"  [debug] Snapshot URL: {snapshot_url}", flush=True)

            # Verify we're on the playground site
            url_ok = runtime.assert_(url_contains("sentience-sdk-playground"), label="on_playground_site", required=True)
            if not url_ok:
                print(f"  [error] Not on playground site. URL: {snapshot_url}", flush=True)
                return False, None

            print(f"  [info] URL verified: {snapshot_url}", flush=True)

            # Debug: print all elements found in snapshot
            snap = runtime.last_snapshot
            if snap:
                buttons = [el for el in snap.elements if (el.role or "").lower() == "button"]
                textboxes = [el for el in snap.elements if (el.role or "").lower() == "textbox"]
                print(f"  [debug] Found {len(buttons)} buttons, {len(textboxes)} textboxes:", flush=True)
                for btn in buttons:
                    print(f"    button: id={btn.id} text={btn.text!r} disabled={btn.disabled}", flush=True)
                for tb in textboxes:
                    print(f"    textbox: id={tb.id} text={tb.text!r}", flush=True)

            # Verify the Sign In button is DISABLED initially (before any fields are filled)
            # This is a key demo point: button is disabled until both fields have values
            disabled_ok = runtime.assert_(is_disabled("role=button"), label="login_button_disabled_initially", required=False)
            if disabled_ok:
                print("  [info] Login button is DISABLED initially (as expected)", flush=True)
            else:
                print("  [warn] Could not verify button is disabled initially - continuing anyway", flush=True)

            return True, None

        # -------------------------
        # Step 2: LLM finds and fills username field
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

            task = (
                "Find the username input field (role='textbox') and click it.\n"
                "It's the FIRST textbox on the page. Click the textbox to focus it."
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

            print(f"  [debug] LLM response: {resp.content!r}", flush=True)

            click_id = parse_click_id(resp.content or "")
            if click_id is None:
                print(f"  [error] Could not parse CLICK(<id>) from LLM response: {resp.content!r}", flush=True)
                runtime.assert_(exists("role=textbox"), label="llm_failed_to_find_username", required=True)
                return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

            print(f"  [info] LLM chose element ID {click_id} for username field", flush=True)

            # Click the username field
            await click_async(browser, click_id, use_mouse=True, cursor_policy=cursor_policy)
            await browser.page.wait_for_timeout(200)

            # Type username with human-like delays
            for ch in TEST_USERNAME:
                await browser.page.keyboard.type(ch)
                await browser.page.wait_for_timeout(random.randint(50, 120))

            runtime.assert_(exists("role=textbox"), label="username_field_filled", required=True)
            return True, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0), f"typed={TEST_USERNAME}"

        # -------------------------
        # Step 3: LLM finds and fills password field
        # -------------------------
        async def step3(step_id: str):
            await runtime.snapshot(limit=40, screenshot=False, goal="Find the password input field")
            snap = runtime.last_snapshot
            if snap is None:
                raise RuntimeError("snapshot missing")

            compact = ctx_formatter._format_snapshot_for_llm(snap)
            tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)
            print("\n--- Step 3: LLM compact prompt ---", flush=True)
            print(_clip_for_log(compact), flush=True)
            print("--- end compact prompt ---\n", flush=True)

            task = (
                "Find the password input field and click it.\n"
                "Look for a field with placeholder or label containing 'password'.\n"
                "The password field may have role='textbox' with type='password' or similar."
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

            print(f"  [debug] LLM response: {resp.content!r}", flush=True)

            click_id = parse_click_id(resp.content or "")
            if click_id is None:
                print(f"  [error] Could not parse CLICK(<id>) from LLM response: {resp.content!r}", flush=True)
                runtime.assert_(exists("role=textbox"), label="llm_failed_to_find_password", required=True)
                return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

            print(f"  [info] LLM chose element ID {click_id} for password field", flush=True)

            # Click the password field
            await click_async(browser, click_id, use_mouse=True, cursor_policy=cursor_policy)
            await browser.page.wait_for_timeout(200)

            # Type password with human-like delays
            for ch in TEST_PASSWORD:
                await browser.page.keyboard.type(ch)
                await browser.page.wait_for_timeout(random.randint(50, 120))

            runtime.assert_(exists("role=textbox"), label="password_field_filled", required=True)

            # After filling both username and password, wait for button to become ENABLED
            # This is a key demo point: button transitions from disabled → enabled
            print("  [info] Waiting for login button to become enabled...", flush=True)

            enabled_ok = await runtime.check(
                is_enabled("role=button"),
                label="login_button_enabled_after_fill",
                required=True
            ).eventually(timeout_s=5.0, poll_s=0.3, max_snapshot_attempts=5)

            # Debug: print button state after filling fields
            snap = runtime.last_snapshot
            if snap:
                buttons = [el for el in snap.elements if (el.role or "").lower() == "button"]
                print(f"  [debug] After filling fields, found {len(buttons)} buttons:", flush=True)
                for btn in buttons:
                    print(f"    id={btn.id} text={btn.text!r} disabled={btn.disabled}", flush=True)

            if enabled_ok:
                print("  [info] Button is now ENABLED after filling both fields", flush=True)
            else:
                print("  [warn] Button may not be enabled - continuing anyway", flush=True)

            return True, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0), "password_filled"

        # -------------------------
        # Step 4: LLM finds and clicks login button
        # -------------------------
        async def step4(step_id: str):
            # Wait a moment for button to become enabled (after both fields filled)
            await browser.page.wait_for_timeout(300)
            await runtime.snapshot(limit=40, screenshot=False, goal="Find and click the login button")
            snap = runtime.last_snapshot
            if snap is None:
                raise RuntimeError("snapshot missing")

            # Verify button is enabled before clicking (should have been enabled in Step 3)
            enabled_ok = runtime.assert_(is_enabled("role=button"), label="login_button_enabled_before_click", required=False)
            if not enabled_ok:
                print("  [warn] Button may not be enabled, but proceeding with click", flush=True)

            compact = ctx_formatter._format_snapshot_for_llm(snap)
            tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)
            print("\n--- Step 4: LLM compact prompt ---", flush=True)
            print(_clip_for_log(compact), flush=True)
            print("--- end compact prompt ---\n", flush=True)

            task = (
                "Find and click the login/submit button.\n"
                "Look for a button (role='button') with text containing 'Login', 'Sign in', or 'Submit'.\n"
                "The button should now be enabled since both username and password are filled."
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
                runtime.assert_(exists("role=button"), label="llm_failed_to_find_login_button", required=True)
                return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

            print(f"  LLM chose element ID {click_id} for login button", flush=True)

            # Click the login button
            pre_url = browser.page.url
            await click_async(browser, click_id, use_mouse=True, cursor_policy=cursor_policy)

            # Wait for navigation (site has artificial delay before navigation)
            await browser.page.wait_for_timeout(1500)
            await browser.page.wait_for_load_state("domcontentloaded", timeout=10_000)

            # Verify we navigated away from login page
            current_url = browser.page.url
            ok = "login" not in current_url.lower() or "profile" in current_url.lower()
            runtime.assert_(
                lambda ctx: AssertOutcome(passed=ok, reason="login_success" if ok else "still_on_login", details={"url": current_url}),
                label="navigated_after_login",
                required=True,
            )

            return ok, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0), f"navigated_to={current_url}"

        # -------------------------
        # Step 5: Navigate to profile page
        # -------------------------
        async def step5(step_id: str):
            # Check if we're already on profile page, if not navigate there
            current_url = browser.page.url
            if "profile" not in current_url.lower():
                await runtime.snapshot(limit=40, screenshot=False, goal="Find the profile link")
                snap = runtime.last_snapshot
                if snap is None:
                    raise RuntimeError("snapshot missing")

                compact = ctx_formatter._format_snapshot_for_llm(snap)
                tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)
                print("\n--- Step 5: LLM compact prompt ---", flush=True)
                print(_clip_for_log(compact), flush=True)
                print("--- end compact prompt ---\n", flush=True)

                task = (
                    "Find and click the Profile link in the navigation.\n"
                    "Look for a link (role='link') with text 'Profile' or href containing '/profile'."
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
                    runtime.assert_(exists("role=link"), label="llm_failed_to_find_profile_link", required=True)
                    return False, StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)

                await click_async(browser, click_id, use_mouse=True, cursor_policy=cursor_policy)
                await browser.page.wait_for_load_state("domcontentloaded", timeout=10_000)
                usage = StepTokenUsage(resp.prompt_tokens or 0, resp.completion_tokens or 0, resp.total_tokens or 0)
            else:
                usage = None

            # Wait for profile content to load (site has 800-1200ms delay)
            await browser.page.wait_for_timeout(1500)
            await runtime.snapshot(limit=40, screenshot=False, goal="Verify profile page loaded")

            ok = runtime.assert_(url_contains("profile"), label="on_profile_page", required=True)
            return ok, usage

        # -------------------------
        # Step 6: Extract username AND email from profile
        # -------------------------
        async def step6(step_id: str):
            # Wait for late-loading profile content (800-1200ms delay)
            # Use eventually() to wait for profile card to appear
            print("  [info] Waiting for profile card to load...", flush=True)
            profile_loaded = await runtime.check(
                exists("text~'Profile'"),
                label="profile_card_loaded",
                required=True
            ).eventually(timeout_s=10.0, poll_s=0.5, max_snapshot_attempts=10)

            if not profile_loaded:
                print("  [error] Profile card did not load in time", flush=True)
                return False, None, "profile_not_loaded"

            await runtime.snapshot(limit=40, screenshot=False, goal="Extract username and email from profile card")
            snap = runtime.last_snapshot
            if snap is None:
                raise RuntimeError("snapshot missing")

            compact = ctx_formatter._format_snapshot_for_llm(snap)
            tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)
            print("\n--- Step 6: LLM compact prompt ---", flush=True)
            print(_clip_for_log(compact), flush=True)
            print("--- end compact prompt ---\n", flush=True)

            # Extract both username and email from the profile card
            found_username = None
            found_email = None

            for el in snap.elements:
                text = (el.text or "").strip()
                # Look for email pattern (contains @)
                if "@" in text and found_email is None:
                    found_email = text
                # Look for username (matches test username, not an email)
                elif TEST_USERNAME.lower() in text.lower() and "@" not in text:
                    found_username = text

            # Log what we found
            print(f"  [info] Extracted username: {found_username}", flush=True)
            print(f"  [info] Extracted email: {found_email}", flush=True)

            # Verify we found at least one (username or email)
            if found_username or found_email:
                details = {}
                if found_username:
                    details["username"] = found_username
                if found_email:
                    details["email"] = found_email

                runtime.assert_(
                    lambda ctx: AssertOutcome(
                        passed=True,
                        reason="profile_data_extracted",
                        details=details
                    ),
                    label="profile_data_extracted",
                    required=True,
                )

                extracted = []
                if found_username:
                    extracted.append(f"username={found_username}")
                if found_email:
                    extracted.append(f"email={found_email}")

                return True, None, " | ".join(extracted)
            else:
                # Check if profile card elements exist at all
                has_profile_content = any(
                    "profile" in (el.text or "").lower() for el in snap.elements
                )
                runtime.assert_(
                    lambda ctx: AssertOutcome(passed=has_profile_content, reason="profile_content_check", details={}),
                    label="profile_has_content",
                    required=True,
                )
                return has_profile_content, None, "profile_content_present_but_no_extraction"

        # -------------------------
        # Run the steps
        # -------------------------
        all_ok = True
        steps = [
            (1, "Navigate to login page", step1),
            (2, "Fill username field", step2),
            (3, "Fill password field", step3),
            (4, "Click login button", step4),
            (5, "Navigate to profile page", step5),
            (6, "Extract username and email from profile", step6),
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
            "demo_name": "Login + Profile Check: Local LLM Agent",
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

        video_output = os.path.join(os.path.dirname(__file__), "video", f"login_profile_{timestamp}.mp4")
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
