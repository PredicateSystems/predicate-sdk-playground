import asyncio
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime

from dotenv import load_dotenv

from sentience.actions import click_async
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
    task_goal = "News list skimming: find and open the top 'Show HN' post"
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
    # Allow overriding device_map behavior via env for reliability on some setups.
    # Examples:
    #   export LOCAL_TEXT_DEVICE=cpu   (most compatible)
    #   export LOCAL_TEXT_DEVICE=auto  (default; may use accelerate device_map)
    local_text_device = (os.getenv("LOCAL_TEXT_DEVICE") or "auto").strip().lower()
    llm = LocalLLMProvider(model_name=local_text_model, device=local_text_device, load_in_4bit=False)

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
    async with AsyncSentienceBrowser(headless=False) as browser:
        await browser.start()

        if browser.page is None:
            raise RuntimeError("Browser page not initialized")

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
        cursor_policy = CursorPolicy(mode="human")

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
        # Step 1: Navigate to HN Show
        # -------------------------
        async def step1(_step_id: str):
            await browser.goto("https://news.ycombinator.com/show")
            await browser.page.wait_for_load_state("domcontentloaded", timeout=10_000)
            await runtime.snapshot(goal=snapshot_goal)

            ok1 = runtime.assert_(url_contains("news.ycombinator.com/show"), label="on_hn_show", required=True)
            ok2 = await runtime.check(exists("role=link text~'Show HN'"), label="show_hn_visible", required=True).eventually(
                timeout_s=8.0,
                poll_s=0.25,
                min_confidence=0.6,
                max_snapshot_attempts=3,
                snapshot_kwargs={
                    "limit": 60,
                    "screenshot": False,
                    "goal": snapshot_goal,
                    "use_api": True if use_api else None,
                    "sentience_api_key": sentience_api_key if use_api else None,
                },
                vision_provider=vision_provider,
            )

            return (ok1 and ok2), None

        # ---------------------------------------
        # Step 2: LLM picks the top "Show HN" post
        # ---------------------------------------
        selected_id: int | None = None

        async def step2(step_id: str):
            nonlocal selected_id
            await runtime.snapshot(limit=60, screenshot=False, goal=snapshot_goal)
            snap = runtime.last_snapshot
            if snap is None:
                raise RuntimeError("snapshot missing")

            compact = ctx_formatter._format_snapshot_for_llm(snap)
            tracer.emit("note", {"kind": "compact_prompt", "text": compact}, step_id=step_id)
            print("\n--- LLM compact prompt (elements context) ---", flush=True)
            print(_clip_for_log(compact), flush=True)
            print("--- end compact prompt ---\n", flush=True)

            task = "Find the FIRST post in the list that is a 'Show HN' item, then click that post."
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

            # Verify the chosen element looks like a Show HN post (best-effort)
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
            runtime.assert_(
                exists(f"id={click_id}"),
                label="chosen_id_exists",
                required=True,
            )
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
        # Step 3: Click with human cursor + verify navigation
        # -------------------------
        async def step3(_step_id: str):
            if selected_id is None:
                raise RuntimeError("No selected_id from step2")

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

            # For HN, the title link often navigates to an external domain (e.g. github.com),
            # so "/item?id=" is NOT a reliable success signal. Instead, wait for any URL change.
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
        # Run the 3 steps
        # -------------------------
        all_ok = True
        all_ok &= await run_step(1, "Navigate to HN Show page + verify list visible", step1)
        all_ok &= await run_step(2, "LLM identifies top 'Show HN' post", step2)
        all_ok &= await run_step(3, "Click selected post with human cursor + verify navigation", step3)

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

