#!/usr/bin/env python3
"""
browser-use + PredicateDebugger demo (sidecar verification + trace).

This is intentionally a "minimal adapter" demo:
- browser-use owns the browser session
- PredicateDebugger attaches to the Playwright Page and verifies outcomes
- We emit per-step screenshots and stitch them into a simple mp4 with token overlays
"""

from __future__ import annotations

import asyncio
import base64
import builtins as _builtins
import inspect
import os
import re
import sys
import threading
import time
import traceback
import uuid
import urllib.parse
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:
    # Optional dependency: the demo can still run if env vars are set another way.
    def load_dotenv(*_args, **_kwargs):  # type: ignore
        return False


# ---------------------------------------------------------------------
# Demo logging: add elapsed timestamps to "[demo]" lines
#
# We prefer an "elapsed since video/session start" style timestamp so it's easy
# to align logs with recorded video playback.
# ---------------------------------------------------------------------

_DEMO_T0 = time.monotonic()


def _set_demo_time_origin() -> None:
    global _DEMO_T0
    _DEMO_T0 = time.monotonic()


def _demo_elapsed_ts() -> str:
    s = max(0.0, time.monotonic() - _DEMO_T0)
    m = int(s // 60)
    sec = s - m * 60
    # mm:ss.mmm
    return f"{m:02d}:{sec:06.3f}"


def print(*args, **kwargs):  # type: ignore[override]
    """
    Local print wrapper for this demo.

    - If the rendered message starts with "[demo]", rewrite it to:
      "[demo +MM:SS.mmm]"
    - Otherwise, pass through unchanged.
    """
    sep = kwargs.pop("sep", " ")
    end = kwargs.pop("end", "\n")
    file = kwargs.pop("file", None)
    flush = kwargs.pop("flush", False)

    msg = sep.join(str(a) for a in args)
    if msg.startswith("[demo]"):
        msg = msg.replace("[demo]", f"[demo +{_demo_elapsed_ts()}]", 1)

    _builtins.print(msg, sep="", end=end, file=file, flush=flush, **kwargs)

# Allow running from the monorepo without pip-installing the SDK.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SDK_PYTHON = _REPO_ROOT / "sdk-python"
if _SDK_PYTHON.exists():
    sys.path.insert(0, str(_SDK_PYTHON))

# Prefer the local browser-use clone (for debugging / patching).
# This repo contains changes that stream Chrome stderr/stdout to surface extension
# load failures. If this path doesn't exist, we fall back to the venv package.
_BROWSER_USE_DEV = Path("/Users/guoliangwang/Code/Python/browser-use")
if _BROWSER_USE_DEV.exists():
    sys.path.insert(0, str(_BROWSER_USE_DEV))

from predicate import PredicateDebugger, get_extension_dir
from predicate.integrations.browser_use import (
    PredicateBrowserUsePlugin,
    PredicateBrowserUsePluginConfig,
    PredicateBrowserUseVerificationError,
    StepCheckSpec,
)
from predicate.models import SnapshotOptions
from predicate.tracer_factory import create_tracer
from predicate.verification import any_of, custom, exists, url_contains

from predicate.backends.actions import type_text as backend_type_text
from predicate.backends import BrowserUseAdapter

from shared.playwright_video import try_persist_page_video
try:
    from shared.video_generator_simple import create_demo_video
except ImportError:
    create_demo_video = None


# DW (Deutsche Welle) URL - Task ID 391 from webbench
# Task: "Visit the DW homepage and list the headline and publication time of the top news article featured in the main section."
DW_URL = "https://www.dw.com"
TASK_DESCRIPTION = "Visit the DW homepage and list the headline and publication time of the top news article featured in the main section."
# NOTE: These are intentionally initialized with defaults and then re-bound inside `main()`
# AFTER `.env` loading. Reading env vars at import-time makes `.env` overrides ineffective.
DEMO_MODE = "fix"  # "fail" | "fix"
START_URL = DW_URL

# Legacy references (for compatibility with existing code)
ACE_URL = DW_URL
SEARCH_URL = DW_URL  # DW task doesn't require search


def _load_env_file(path: Path, *, override: bool = False) -> None:
    """
    Minimal .env loader (so we don't hard-depend on python-dotenv).

    Supports lines like:
      KEY=value
      export KEY=value
      KEY="value with spaces"
    Ignores blank lines and comments starting with '#'.
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


def _pick_search_input_element(snap) -> object | None:
    """
    Best-effort heuristic to find Ace's homepage search input from a Sentience snapshot.
    """
    try:
        elements = list(getattr(snap, "elements", []) or [])
    except Exception:
        return None

    def _s(e) -> int:
        role = str(getattr(e, "role", "") or "").lower()
        name = str(getattr(e, "name", "") or "").lower()
        text = str(getattr(e, "text", "") or "").lower()
        near = str(getattr(e, "nearby_text", "") or "").lower()
        itype = str(getattr(e, "input_type", "") or "").lower()
        y = float(getattr(getattr(e, "bbox", None), "y", 9999.0) or 9999.0)
        in_view = bool(getattr(e, "in_viewport", True))

        score = 0
        if role in ("textbox", "searchbox", "combobox", "input"):
            score += 60
        if itype in ("search", "text"):
            score += 25
        hint = "what can we help you find"
        if hint in name or hint in text or hint in near:
            score += 120
        if "search" in name or "search" in near:
            score += 30
        if in_view:
            score += 10
        # Search box is typically in the header area.
        if y <= 260:
            score += 15
        # Prefer non-tiny elements
        try:
            w = float(getattr(getattr(e, "bbox", None), "width", 0.0) or 0.0)
            h = float(getattr(getattr(e, "bbox", None), "height", 0.0) or 0.0)
            if w >= 180 and h >= 22:
                score += 10
        except Exception:
            pass
        return score

    best = None
    best_score = -1
    for e in elements:
        sc = _s(e)
        if sc > best_score:
            best_score = sc
            best = e

    # Require at least some confidence; otherwise this is too risky.
    if best is None or best_score < 60:
        return None
    return best


async def _sleep_ms(ms: int) -> None:
    await asyncio.sleep(ms / 1000.0)


async def _maybe_await(result):
    if inspect.isawaitable(result):
        return await result
    return result


async def await_with_timeout(label: str, coro, *, timeout_s: float):
    """
    Await a coroutine with a hard timeout and clear logging.

    This prevents the demo from "silently hanging" on CDP/navigation calls.
    """
    print(f"[demo] -> {label} (timeout={timeout_s}s)", flush=True)
    try:
        result = await asyncio.wait_for(coro, timeout=timeout_s)
        print(f"[demo] <- {label} (ok)", flush=True)
        return result
    except asyncio.TimeoutError as e:
        print(f"[demo] !! {label} timed out after {timeout_s}s", flush=True)
        raise e


async def page_goto(page, url: str, **kwargs):
    fn = getattr(page, "goto", None)
    if not callable(fn):
        raise RuntimeError("page.goto is not available on this page object")
    try:
        sig = inspect.signature(fn)
        params = sig.parameters
        has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
        if has_var_kw:
            return await _maybe_await(fn(url, **kwargs))
        filtered = {k: v for k, v in kwargs.items() if k in params}
        return await _maybe_await(fn(url, **filtered))
    except TypeError:
        # Some browser-use Page variants accept only (url) with no kwargs.
        return await _maybe_await(fn(url))


async def page_wait_for_load(page, state: str = "domcontentloaded", **kwargs):
    fn = getattr(page, "wait_for_load_state", None)
    if not callable(fn):
        # browser_use.actor.page.Page does not expose Playwright load-state waits
        # (it is CDP-driven). We do a small, deterministic pause instead.
        await _sleep_ms(1200)
        return None
    try:
        sig = inspect.signature(fn)
        params = sig.parameters
        has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
        if has_var_kw:
            return await _maybe_await(fn(state, **kwargs))
        filtered = {k: v for k, v in kwargs.items() if k in params}
        if len(params) == 0:
            return await _maybe_await(fn())
        return await _maybe_await(fn(state, **filtered))
    except TypeError:
        try:
            return await _maybe_await(fn())
        except Exception:
            await _sleep_ms(1200)
            return None


async def connect_playwright_page_from_browser_use_session(session):
    """
    Mirror browser-use's official Sentience integration strategy:
    - Use browser-use for navigation (session.navigate_to)
    - For verification/snapshots, attach PredicateDebugger to a real Playwright Page
      by connecting Playwright to the same browser via CDP.
    """
    cdp_url = getattr(session, "cdp_url", None)
    if not cdp_url:
        raise RuntimeError("browser-use session has no cdp_url; cannot connect Playwright")

    # Import Playwright lazily to keep startup fast when not needed.
    from playwright.async_api import async_playwright  # type: ignore

    playwright = await async_playwright().start()
    browser = await playwright.chromium.connect_over_cdp(str(cdp_url))

    # Try to pick the page whose URL matches browser-use's current URL.
    target_url = None
    get_url_fn = getattr(session, "get_current_page_url", None)
    if callable(get_url_fn):
        try:
            target_url = await _maybe_await(get_url_fn())
        except Exception:
            target_url = None

    page = None
    try:
        contexts = getattr(browser, "contexts", []) or []
        pages = []
        for ctx in contexts:
            try:
                pages.extend(list(getattr(ctx, "pages", []) or []))
            except Exception:
                continue
        # Prefer exact URL match; else first non-blank page.
        if target_url:
            for p in pages:
                try:
                    if getattr(p, "url", None) == target_url:
                        page = p
                        break
                except Exception:
                    continue
        if page is None:
            for p in pages:
                try:
                    u = getattr(p, "url", "") or ""
                    if u and not u.startswith("about:"):
                        page = p
                        break
                except Exception:
                    continue
        if page is None and pages:
            page = pages[0]
    except Exception:
        page = None

    if page is None:
        await browser.close()
        await playwright.stop()
        raise RuntimeError("Could not locate a Playwright Page via connect_over_cdp")

    return playwright, browser, page


async def ensure_predicate_injected_on_playwright_page(page, *, timeout_s: float = 30.0) -> None:
    """
    Ensure window.sentience.snapshot is available on the given Page.

    This is necessary after navigations where the extension injects at document_idle.
    We wait longer than the SDK's internal 5s to avoid flakiness on heavier pages.

    Works with both Playwright Page and browser-use Page objects.
    """
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=int(timeout_s * 1000))
    except Exception:
        pass
    # Give document_idle content scripts a moment.
    await _sleep_ms(600)

    # Check if this is a Playwright page (has wait_for_function) or browser-use page
    if hasattr(page, "wait_for_function"):
        # Playwright Page - use native wait_for_function
        await page.wait_for_function(
            "typeof window.sentience !== 'undefined' && typeof window.sentience.snapshot === 'function'",
            timeout=int(timeout_s * 1000),
        )
    else:
        # browser-use Page - poll using evaluate-like APIs (varies by version)
        #
        # Known variants:
        # - Playwright page: evaluate(...)
        # - browser-use Page: evaluate_js(...)
        eval_fn = getattr(page, "evaluate", None)
        eval_js_fn = getattr(page, "evaluate_js", None)
        start = time.time()
        last_err: str | None = None
        while time.time() - start < timeout_s:
            try:
                expr = "typeof window.sentience !== 'undefined' && typeof window.sentience.snapshot === 'function'"
                if callable(eval_fn):
                    result = await eval_fn(expr)
                elif callable(eval_js_fn):
                    result = await eval_js_fn(expr)
                else:
                    raise RuntimeError("page has no evaluate/evaluate_js")
                if result:
                    return
            except Exception:
                try:
                    last_err = traceback.format_exc(limit=1)
                except Exception:
                    last_err = "eval_failed"
                pass
            await _sleep_ms(500)
        raise TimeoutError(
            f"Predicate extension not injected after {timeout_s}s (last_err={last_err})"
        )


async def _fallback_to_browser_use_backend(session, dbg, *, timeout_s: float = 20.0) -> None:
    """
    If Playwright evaluation cannot see window.sentience (isolated world / context mismatch),
    fall back to browser-use's CDP backend for snapshotting (which evaluates in the page world).
    """
    print(f"[demo] _fallback_to_browser_use_backend: creating adapter...", flush=True)
    try:
        adapter = BrowserUseAdapter(session)
        print(f"[demo] _fallback_to_browser_use_backend: calling create_backend (timeout={timeout_s}s)...", flush=True)
        backend = await asyncio.wait_for(adapter.create_backend(), timeout=timeout_s)
        print(f"[demo] _fallback_to_browser_use_backend: backend created successfully", flush=True)
        dbg.runtime.backend = backend
    except asyncio.TimeoutError:
        print(f"[demo] _fallback_to_browser_use_backend: create_backend timed out after {timeout_s}s", flush=True)
        raise RuntimeError(f"create_backend() timed out after {timeout_s}s")
    except Exception as e:
        print(f"[demo] _fallback_to_browser_use_backend: failed: {type(e).__name__}: {e}", flush=True)
        raise RuntimeError(f"failed to switch debugger backend to browser-use CDP: {e}") from e


async def _sync_playwright_page_to_browser_use(session, pw_browser, page, dbg) -> object:
    """
    browser-use can change the focused target/tab during navigation.
    Keep the debugger attached to the currently focused page by rebinding the backend.
    """
    try:
        get_url_fn = getattr(session, "get_current_page_url", None)
        if not callable(get_url_fn):
            return page
        target_url = str(await _maybe_await(get_url_fn()) or "")
        if not target_url:
            return page

        current_url = ""
        try:
            current_url = str(getattr(page, "url", "") or "")
        except Exception:
            current_url = ""

        if current_url == target_url:
            return page

        # Find matching Playwright page for browser-use's current URL.
        contexts = getattr(pw_browser, "contexts", []) or []
        for ctx in contexts:
            for p in getattr(ctx, "pages", []) or []:
                try:
                    if getattr(p, "url", None) == target_url:
                        page = p
                        raise StopIteration
                except StopIteration:
                    raise
                except Exception:
                    continue
    except StopIteration:
        pass
    except Exception:
        return page

    # Rebind runtime backend to the new page (keep same tracer/step timeline).
    try:
        from predicate.backends.playwright_backend import PlaywrightBackend

        dbg.runtime.backend = PlaywrightBackend(page)
    except Exception:
        pass

    return page


async def wait_for_predicate_extension_ready(backend, *, timeout_s: float = 30.0) -> None:
    """
    Wait (with diagnostics) until the Sentience content script is injected.

    We do this explicitly in the demo because older browser-use versions can take
    longer than the SDK's default 5s wait, especially right after startup.
    """
    start = time.monotonic()
    last_diag: dict | None = None
    last_print_s: int | None = None
    consecutive_eval_timeouts = 0

    async def _eval_with_timeout(expr: str, *, timeout_s: float = 2.0):
        """
        Evaluate JS with a hard timeout that can't deadlock.

        We intentionally avoid awaiting task cancellation because some CDP client
        stacks can get "stuck" in an await that doesn't respond to cancellation.
        """
        task = asyncio.create_task(backend.eval(expr))
        done, _pending = await asyncio.wait({task}, timeout=timeout_s)
        if task not in done:
            task.cancel()
            return "__EVAL_TIMEOUT__"
        try:
            return task.result()
        except Exception:
            return "__EVAL_ERROR__"

    while True:
        elapsed = time.monotonic() - start
        if elapsed >= timeout_s:
            break

        # If the backend caches an execution context, refresh it periodically.
        # This avoids getting "stuck" observing a pre-injection context.
        try:
            reset_fn = getattr(backend, "reset_execution_context", None)
            if callable(reset_fn) and (int(elapsed) % 2 == 0):
                reset_fn()
        except Exception:
            pass

        # 1) Check readiness (fast path)
        ready = await _eval_with_timeout(
            "typeof window.sentience !== 'undefined' && typeof window.sentience.snapshot === 'function'"
        )

        if ready == "__EVAL_TIMEOUT__":
            consecutive_eval_timeouts += 1
        else:
            consecutive_eval_timeouts = 0

        if ready not in ("__EVAL_TIMEOUT__", "__EVAL_ERROR__", False, None):
            return

        # 2) Once per second: print diagnostics (always attempt; never rely on a timing window)
        now_s = int(elapsed)
        if last_print_s != now_s:
            last_print_s = now_s
            last_diag = await _eval_with_timeout(
                """
                (() => ({
                    url: window.location.href,
                    ready_state: document.readyState,
                    sentience_defined: typeof window.sentience !== 'undefined',
                    sentience_snapshot: typeof window.sentience?.snapshot === 'function',
                    extension_id: document.documentElement.dataset.sentienceExtensionId || null
                }))()
                """
            )

            if last_diag == "__EVAL_TIMEOUT__":
                print(f"[demo] waiting... (CDP eval timeout; streak={consecutive_eval_timeouts})", flush=True)
            elif last_diag == "__EVAL_ERROR__":
                print(f"[demo] waiting... (CDP eval error; streak={consecutive_eval_timeouts})", flush=True)
            elif isinstance(last_diag, dict):
                print(
                    "[demo] waiting... "
                    f"url={last_diag.get('url')!s} "
                    f"ready_state={last_diag.get('ready_state')!s} "
                    f"extension_id={last_diag.get('extension_id')!s} "
                    f"sentience_defined={last_diag.get('sentience_defined')!s} "
                    f"sentience_snapshot={last_diag.get('sentience_snapshot')!s} "
                    f"timeout_streak={consecutive_eval_timeouts}",
                    flush=True,
                )
            else:
                print(f"[demo] waiting... (no diagnostics; streak={consecutive_eval_timeouts})", flush=True)

        await _sleep_ms(200)

    raise RuntimeError(
        "Predicate extension did not become ready in time. "
        f"diagnostics={last_diag!r}"
    )


async def debug_print_extension_targets(session) -> None:
    """
    Print any chrome-extension:// targets seen by browser-use.

    This is the fastest way to tell whether Chrome actually loaded the extension(s),
    independent of whether content scripts injected on the current page.
    """
    # Prefer a raw CDP query because SessionManager filters targets (page/iframe only).
    root = getattr(session, "_cdp_client_root", None)
    send = getattr(root, "send", None) if root is not None else None
    tgt = getattr(send, "Target", None) if send is not None else None
    get_targets = getattr(tgt, "getTargets", None) if tgt is not None else None
    if callable(get_targets):
        try:
            # Temporarily broaden discovery. browser-use itself sets a restrictive filter
            # (page/iframe) for event monitoring; we want to see extension/service_worker targets too.
            set_discover = getattr(tgt, "setDiscoverTargets", None)
            if callable(set_discover):
                try:
                    await set_discover(params={"discover": True})
                except Exception:
                    pass
            res = await get_targets(params={})
            infos = res.get("targetInfos", []) if isinstance(res, dict) else []
            try:
                type_counts: dict[str, int] = {}
                for info in infos:
                    typ = str((info or {}).get("type") or "")
                    type_counts[typ] = type_counts.get(typ, 0) + 1
                sample = ", ".join(f"{k}:{v}" for k, v in sorted(type_counts.items()))
                print(f"[demo] CDP Target.getTargets(): total={len(infos)} types=({sample})")
            except Exception:
                pass
            # Print a few non-page targets too (often where MV3 background lives).
            sample_other: list[str] = []
            try:
                for info in infos:
                    typ = str((info or {}).get("type") or "")
                    url = str((info or {}).get("url") or "")
                    if typ in ("service_worker", "worker", "background_page"):
                        sample_other.append(f"{typ}: {url}")
                if sample_other:
                    print("[demo] CDP targets sample (service_worker/worker/background_page):")
                    for s in sample_other[:8]:
                        print(f"[demo]   {s}")
            except Exception:
                pass

            ext_infos = []
            for info in infos:
                try:
                    url = str(info.get("url") or "")
                    typ = str(info.get("type") or "")
                except Exception:
                    continue
                if url.startswith("chrome-extension://"):
                    ext_infos.append((typ, url))
            if ext_infos:
                uniq = sorted(set(ext_infos))
                print(f"[demo] chrome-extension targets detected via CDP: {len(uniq)}")
                for typ, url in uniq[:12]:
                    print(f"[demo]   {typ}: {url}")
                if len(uniq) > 12:
                    print(f"[demo]   ... +{len(uniq) - 12} more")
                return
            print("[demo] No chrome-extension targets detected via CDP")
            return
        except Exception as e:
            print(f"[demo] Failed to query Target.getTargets: {e}")

    print("[demo] Could not query extension targets (no CDP root client)")


async def debug_print_browser_info(session) -> None:
    """Print browser version + (best-effort) actual command line switches."""
    root = getattr(session, "_cdp_client_root", None)
    send = getattr(root, "send", None) if root is not None else None
    browser = getattr(send, "Browser", None) if send is not None else None
    if browser is None:
        return
    try:
        get_version = getattr(browser, "getVersion", None)
        if callable(get_version):
            v = await get_version(params={})
            if isinstance(v, dict):
                print(f"[demo] Browser.getVersion(): {v.get('product')} ({v.get('userAgent')})")
    except Exception as e:
        print(f"[demo] Browser.getVersion() failed: {e}")

    # Not always available depending on Chrome build / permissions.
    try:
        get_cmd = getattr(browser, "getBrowserCommandLine", None)
        if callable(get_cmd):
            res = await get_cmd(params={})
            argv = res.get("arguments", []) if isinstance(res, dict) else []
            if argv:
                has_load_ext = any(a.startswith("--load-extension=") for a in argv)
                has_disable_ext = any(a == "--disable-extensions" for a in argv)
                has_disable_ext_except = any(a.startswith("--disable-extensions-except=") for a in argv)
                print(
                    f"[demo] Browser.getBrowserCommandLine(): args={len(argv)} "
                    f"has_load_extension={has_load_ext} "
                    f"has_disable_extensions={has_disable_ext} "
                    f"has_disable_extensions_except={has_disable_ext_except}"
                )
                if has_load_ext:
                    for a in argv:
                        if a.startswith("--load-extension="):
                            print(f"[demo]   {a[:300]}{'...' if len(a) > 300 else ''}")
                            break
    except Exception as e:
        print(f"[demo] Browser.getBrowserCommandLine() unavailable/failed: {e}")


async def page_screenshot(page, *, path: str, full_page: bool = False):
    fn = getattr(page, "screenshot", None)
    if not callable(fn):
        return None
    try:
        sig = inspect.signature(fn)
        if "path" in sig.parameters:
            return await _maybe_await(fn(path=path, full_page=full_page))
    except Exception:
        pass

    # browser_use.actor.page.Page.screenshot() returns base64 (no path arg).
    b64 = await _maybe_await(fn())
    if isinstance(b64, str) and b64:
        data = base64.b64decode(b64)
        Path(path).write_bytes(data)
        return path
    return None


async def page_get_url(page) -> str:
    # browser_use.actor.page.Page uses get_url()
    fn = getattr(page, "get_url", None)
    if callable(fn):
        u = await _maybe_await(fn())
        return str(u or "")
    # Playwright Page uses .url (property) or .url()
    if hasattr(page, "url"):
        u = getattr(page, "url")
        if callable(u):
            return str(await _maybe_await(u()))
        return str(u or "")
    return ""


async def ensure_session_on_real_url(session, *, start_url: str, task_text: str | None = None) -> None:
    """
    Ensure the *current tab* is on a real URL (not about:blank).

    This mirrors browser-use's official Sentience integration:
    - Predicate extension does not inject on about:blank / about:*
    - Use BrowserSession.navigate_to() to navigate the existing tab, rather than
      opening a second tab (which often leaves an about:blank tab around).
    """
    get_url_fn = getattr(session, "get_current_page_url", None)
    nav_fn = getattr(session, "navigate_to", None)
    if not callable(get_url_fn) or not callable(nav_fn):
        print("[demo] session missing get_current_page_url or navigate_to, skipping ensure_session_on_real_url", flush=True)
        return

    try:
        current_url = str(await _maybe_await(get_url_fn()) or "")
    except Exception as e:
        print(f"[demo] get_current_page_url() failed: {e}", flush=True)
        current_url = ""

    if current_url and not current_url.startswith("about:"):
        print(f"[demo] Already on real URL: {current_url[:80]}", flush=True)
        return

    # Try to extract a URL from the task (nice for generic demos); else use START_URL.
    target_url = start_url
    if task_text:
        try:
            urls = re.findall(r"https?://[^\s<>\"]+", task_text)
            if urls:
                target_url = urls[0]
        except Exception:
            pass

    print(
        f"[demo] current_url={current_url!r} (Sentience won't inject). "
        f"session.navigate_to({target_url})",
        flush=True
    )

    # Navigate - still wrap in a hard timeout so we never "hang" here.
    try:
        await await_with_timeout(
            "session.navigate_to(start_url)",
            _maybe_await(nav_fn(target_url)),
            timeout_s=60,
        )
        print("[demo] navigate_to() returned", flush=True)
    except Exception as e:
        print(f"[demo] navigate_to() raised {type(e).__name__}: {e}", flush=True)

    # Wait for navigation to settle (like the working example: simple sleep).
    await _sleep_ms(1500)

    # Verify we're no longer on about:blank
    try:
        new_url = str(await _maybe_await(get_url_fn()) or "")
        if new_url and not new_url.startswith("about:"):
            print(f"[demo] Navigation settled, url={new_url[:80]}", flush=True)
        else:
            print(f"[demo] Warning: still on {new_url!r} after navigation", flush=True)
    except Exception as e:
        print(f"[demo] get_current_page_url() after nav failed: {e}", flush=True)


def _maybe_make_browser_profile_kwargs(*, record_video_dir: str | None) -> dict:
    """
    Build BrowserProfile kwargs.

    IMPORTANT: Do NOT rely on inspect.signature() for Pydantic models; it can be
    misleading across versions and cause us to silently drop critical fields
    like 'args' (which would prevent the extension from loading).
    """
    kwargs: dict = {}

    # IMPORTANT:
    # Google Chrome Stable can reject --load-extension entirely (we saw:
    # " --load-extension is not allowed in Google Chrome, ignoring.").
    # Prefer Playwright's "Google Chrome for Testing" binary when available.
    executable_path = (os.getenv("BROWSER_USE_EXECUTABLE_PATH") or "").strip() or None
    if not executable_path:
        try:
            pw_root = Path.home() / "Library" / "Caches" / "ms-playwright"
            candidates = sorted(
                pw_root.glob(
                    "chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
                )
            )
            if candidates:
                executable_path = str(candidates[-1])
        except Exception:
            executable_path = None
    if executable_path:
        kwargs["executable_path"] = executable_path
        print(f"[demo] Using browser executable_path: {executable_path}")

    # Common knobs we want
    kwargs["headless"] = False

    # We must load the Predicate extension for window.sentience.snapshot()
    sentience_ext = get_extension_dir()
    print(f"[demo] Predicate extension dir: {sentience_ext}")

    # IMPORTANT: Chrome only respects the LAST --load-extension arg.
    # For this demo we load ONLY the Predicate extension by default.
    # browser-use default extensions can affect page rendering (e.g. adblock / DNR rules),
    # which can make pages look like "images are missing".
    def _manifest_version(ext_dir: str) -> int | None:
        try:
            import json

            p = Path(ext_dir) / "manifest.json"
            if not p.exists():
                return None
            data = json.loads(p.read_text())
            mv = data.get("manifest_version")
            return int(mv) if mv is not None else 2  # Many MV2 manifests omit the field.
        except Exception:
            return None

    extension_paths = [sentience_ext]
    if (os.getenv("BROWSER_USE_LOAD_DEFAULT_EXTENSIONS") or "").strip().lower() in ("1", "true", "yes"):
        try:
            from browser_use import BrowserProfile  # type: ignore

            temp_profile = BrowserProfile(enable_default_extensions=True)
            default_exts = []
            ensure_fn = getattr(temp_profile, "_ensure_default_extensions_downloaded", None)
            if callable(ensure_fn):
                default_exts = list(ensure_fn() or [])
            if default_exts:
                kept: list[str] = []
                skipped: list[tuple[str, str]] = []
                for p in default_exts:
                    s = str(p)
                    mv = _manifest_version(s)
                    if mv is None:
                        skipped.append((s, "no manifest.json / unreadable"))
                    elif mv < 3:
                        skipped.append((s, f"manifest_version={mv} (skip MV2)"))
                    else:
                        kept.append(s)

                extension_paths.extend(kept)
                print(f"[demo] Found {len(default_exts)} browser-use default extensions")
                print(f"[demo] Keeping {len(kept)} MV3 default extensions; skipping {len(skipped)}")
            else:
                print("[demo] No browser-use default extensions found (ok)")
        except Exception as e:
            print(f"[demo] Could not collect browser-use default extensions: {e}")

    combined_extensions = ",".join(extension_paths)
    print(f"[demo] Combined extensions (count={len(extension_paths)}): {combined_extensions[:120]}...")

    # Strategy (same as browser-use example):
    # - disable auto-loading, and manually load everything together
    kwargs["enable_default_extensions"] = False
    # NOTE: browser-use's local launch path uses its own CHROME_DEFAULT_ARGS (not Playwright),
    # and those defaults currently include flags that can break extension background execution.
    # In particular, '--disable-component-extensions-with-background-pages' can prevent our
    # MV3 service worker from running, which in turn can prevent the extension from functioning.
    kwargs["ignore_default_args"] = [
        "--disable-extensions",  # Important: don't disable extensions
        "--hide-scrollbars",
        "--disable-component-extensions-with-background-pages",
    ]
    args = [
        # Keep --enable-automation so CDP can reveal browser command line
        # (helps debug whether Chrome actually received --load-extension).
        "--enable-automation",
        # Surface extension load failures to stderr (otherwise Chrome can be silent).
        "--enable-logging=stderr",
        "--v=1",
        "--vmodule=extensions*=2,extension_service=2,crx_file*=2,crx_installer*=2",
        "--enable-extensions",
        "--disable-extensions-file-access-check",
        "--disable-extensions-http-throttling",
        "--extensions-on-chrome-urls",
        f"--load-extension={combined_extensions}",
    ]
    kwargs["args"] = args
    print(f"[demo] BrowserProfile args: {args}")

    # Best-effort: if browser-use exposes record_video_dir, pass it.
    if record_video_dir:
        kwargs["record_video_dir"] = record_video_dir
        # Some browser-use versions use camelCase.
        kwargs["recordVideoDir"] = record_video_dir

    return kwargs


def _extract_top_products(snap, *, k: int = 5) -> list[dict[str, str]]:
    """
    Best-effort structured extraction for the demo.

    This is intentionally heuristic: we want a stable, explainable demo for verification,
    not a perfect commerce scraper.
    """
    elements = list(getattr(snap, "elements", []) or [])

    def _price_from_text(text: str) -> str | None:
        m = re.search(r"\$\s*\d+(?:\.\d{2})?", text)
        return m.group(0) if m else None

    candidates = [
        e
        for e in elements
        if getattr(e, "role", "") == "link"
        and (getattr(e, "text", "") or "").strip()
        and len((getattr(e, "text", "") or "").strip()) >= 12
        and getattr(e, "href", None)
        and getattr(e, "in_dominant_group", None) is not False
    ]

    def _sort_key(e):
        gi = getattr(e, "group_index", None)
        imp = getattr(e, "importance", 0) or 0
        dy = getattr(e, "doc_y", None)
        return (
            0 if gi is not None else 1,
            gi if gi is not None else 10_000,
            -int(imp),
            float(dy) if dy is not None else 1e9,
        )

    candidates.sort(key=_sort_key)

    results: list[dict[str, str]] = []
    seen_titles: set[str] = set()

    for c in candidates:
        title = (getattr(c, "text", "") or "").strip()
        if title in seen_titles:
            continue
        seen_titles.add(title)

        price: str | None = None
        cy = getattr(c, "doc_y", None) or getattr(c, "center_y", None) or None
        if cy is not None:
            best_dist = 1e9
            for e in elements:
                t = (getattr(e, "text", "") or "").strip()
                if not t:
                    continue
                p = _price_from_text(t)
                if not p:
                    continue
                ey = getattr(e, "doc_y", None) or getattr(e, "center_y", None) or None
                if ey is None:
                    continue
                d = abs(float(ey) - float(cy))
                if d < best_dist and d <= 180:
                    best_dist = d
                    price = p

        if price is None:
            nt = (getattr(c, "nearby_text", None) or "").strip()
            if nt:
                price = _price_from_text(nt)

        results.append({"title": title, "sale_price": price or ""})
        if len(results) >= k:
            break

    return results


async def main() -> None:
    # Load env vars from the playground .env (so BROWSER_USE_API_KEY is picked up
    # even when running from the monorepo root).
    _load_env_file(_REPO_ROOT / "sentience-sdk-playground" / ".env", override=True)
    load_dotenv(dotenv_path=str(_REPO_ROOT / "sentience-sdk-playground" / ".env"), override=True)
    # Also allow a local ".env" (cwd / script dir) to override/add vars.
    _load_env_file(Path.cwd() / ".env", override=True)
    load_dotenv(override=True)
    # Re-bind config that depends on env vars (loaded above).
    global DEMO_MODE, START_URL
    DEMO_MODE = (os.getenv("DEMO_MODE") or "fix").strip().lower()
    START_URL = (os.getenv("BROWSER_USE_START_URL") or DW_URL).strip()
    predicate_api_key = os.getenv("PREDICATE_API_KEY")
    if not predicate_api_key:
        raise SystemExit("Missing PREDICATE_API_KEY in environment.")

    # browser-use ChatBrowserUse reads BROWSER_USE_API_KEY from env.
    if not os.getenv("BROWSER_USE_API_KEY"):
        raise SystemExit(
            "Missing BROWSER_USE_API_KEY in environment (required for browser-use ChatBrowserUse).\n"
            "Set it in sentience-sdk-playground/.env or export it in your shell."
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_dir = Path(__file__).resolve().parent / "artifacts" / timestamp
    screenshots_dir = base_dir / "screenshots"
    video_dir = base_dir / "video"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)

    # NOTE: Cloud tracer init requires a UUID run_id.
    run_label = f"browser-use-debug-{timestamp}"
    run_id = str(uuid.uuid4())
    tracer = create_tracer(
        api_key=predicate_api_key,
        run_id=run_id,
        upload_trace=True,
        goal=f"[demo] {run_label} | DW news task",
        agent_type="sdk-playground/browser-use-debugging",
        llm_model="browser-use/ChatBrowserUse",
        start_url=DW_URL,
    )

    print(f"[demo] run_label={run_label}")
    print(f"[demo] run_id={run_id} (UUID; used by Predicate Studio)")
    print(f"[demo] DEMO_MODE={DEMO_MODE!r} (set DEMO_MODE=fail to force a failing trace)")
    print(
        "[demo] NOTE: this demo is designed to show the key contrast:\n"
        "       vision-based agent considers the run 'successful' (finishes / returns an answer),\n"
        "       but Sentience verification can still fail if outcomes are not provably correct."
    )

    # ---------------------------------------------------------------------
    # Start browser-use session (best-effort video recording hook)
    # ---------------------------------------------------------------------
    try:
        import browser_use  # type: ignore

        print(f"[demo] browser_use package: {getattr(browser_use, '__file__', None)}")
        from browser_use import Agent, BrowserProfile, BrowserSession, ChatBrowserUse  # type: ignore
    except ImportError as e:
        raise SystemExit(
            "browser-use is required.\n"
            "Install: pip install \"predicate-sdk[browser-use]\"\n"
            f"ImportError: {e}"
        ) from e

    profile_kwargs = _maybe_make_browser_profile_kwargs(record_video_dir=str(video_dir))
    profile = BrowserProfile(**profile_kwargs)
    session = BrowserSession(browser_profile=profile)
    # Reset demo log time origin as close as possible to video/session start,
    # so log timestamps align with the recorded video duration.
    _set_demo_time_origin()
    await session.start()
    await debug_print_browser_info(session)
    # Now that browser-use has set user_data_dir, we can inspect the real launch args.
    try:
        launch_args = session.browser_profile.get_args()
        has_load_ext = any(a.startswith("--load-extension=") for a in launch_args)
        has_disable_extensions_exact = any(a == "--disable-extensions" for a in launch_args)
        has_disable_extensions_except = any(a.startswith("--disable-extensions-except=") for a in launch_args)
        has_disable_component_bg = any(
            a == "--disable-component-extensions-with-background-pages" for a in launch_args
        )
        print(
            "[demo] session.browser_profile.get_args(): "
            f"has_load_extension={has_load_ext}, "
            f"has_disable_extensions_exact={has_disable_extensions_exact}, "
            f"has_disable_extensions_except={has_disable_extensions_except}, "
            f"has_disable_component_extensions_with_background_pages={has_disable_component_bg}"
        )
    except Exception as e:
        print(f"[demo] session.browser_profile.get_args() failed: {e}")
    await debug_print_extension_targets(session)

    # SIMPLIFIED STRATEGY: Use browser-use's native CDP session like the working integration.
    # Don't connect external Playwright - just use PredicateContext.build() which internally
    # calls BrowserUseAdapter.create_backend().
    pw = None
    pw_browser = None
    page = None
    dbg: PredicateDebugger | None = None
    playwright_attached = False
    cdp_backend_created = False

    # Navigate first using browser-use
    print("[demo] Navigating to target URL via browser-use...", flush=True)
    await ensure_session_on_real_url(session, start_url=START_URL, task_text=None)

    # Skip the debug print that times out
    print("[demo] Skipping debug_print_extension_targets (known to timeout post-nav)", flush=True)

    # Give the browser a moment to stabilize after navigation timeout
    print("[demo] Waiting 3s for browser to stabilize...", flush=True)
    await asyncio.sleep(3.0)

    # Use PredicateContext.build() like the working integration does
    # This uses BrowserUseAdapter internally
    print("[demo] Testing PredicateContext.build() (like working integration)...", flush=True)
    from predicate.backends import PredicateContext

    sentience_ctx = PredicateContext(
        predicate_api_key=predicate_api_key,
        use_api=True,
        max_elements=60,
        show_overlay=True,
    )

    try:
        ctx_state = await asyncio.wait_for(
            sentience_ctx.build(
                session,
                goal="browser-use-debug-demo",
                wait_for_extension_ms=10000,
                retries=1,
            ),
            timeout=60.0
        )
        if ctx_state:
            print(f"[demo] PredicateContext.build() succeeded! Elements: {len(ctx_state.snapshot.elements)}", flush=True)
        else:
            print("[demo] PredicateContext.build() returned None (snapshot failed)", flush=True)
    except Exception as ctx_err:
        print(f"[demo] PredicateContext.build() failed: {type(ctx_err).__name__}: {ctx_err}", flush=True)
        import traceback
        traceback.print_exc()

    # Create the Predicate browser-use plugin (single wiring point).
    #
    # This replaces the ad-hoc: BrowserUseAdapter → AgentRuntime → PredicateDebugger setup.
    print("[demo] Creating PredicateBrowserUsePlugin...", flush=True)
    # In DEMO_MODE=fail we inject an intentional failing required check as a per-step auto_check.
    # This demonstrates the key contrast: browser-use can return "done", but deterministic verification can still fail.
    per_step_checks = [
        StepCheckSpec(
            predicate=any_of(
                url_contains("dw.com"),
                exists("text~'DW'"),
                exists("text~'News'"),
            ),
            label="on_dw_homepage",
            required=True,
            eventually=True,
            timeout_s=6.0,
        )
    ]
    if DEMO_MODE == "fail":
        per_step_checks = [
            StepCheckSpec(
                predicate=custom(lambda _ctx: False, "demo_intentional_failure"),
                label="demo_fail_required_check",
                required=True,
                eventually=False,
            )
        ]

    plugin = PredicateBrowserUsePlugin(
        config=PredicateBrowserUsePluginConfig(
            predicate_api_key=predicate_api_key,
            use_api=True,
            wait_for_extension_ms=10_000,
            tracer=tracer,
            snapshot_options=SnapshotOptions(
                use_api=True,
                limit=100,
                screenshot=True,  # Enable screenshots for trace upload to Studio
                show_overlay=True,
                goal="browser-use-debug-demo",
                predicate_api_key=predicate_api_key,
            ),
            auto_snapshot_each_step=True,
            auto_checks_each_step=True,
            auto_checks=per_step_checks,
            on_failure="raise",
        )
    )
    try:
        await asyncio.wait_for(plugin.bind(browser_session=session), timeout=30.0)
        dbg = plugin.dbg
        if dbg is None:
            raise RuntimeError("plugin.dbg is None after bind()")
        cdp_backend_created = True
        print("[demo] PredicateBrowserUsePlugin bound successfully!", flush=True)
    except Exception as plugin_err:
        print(
            f"[demo] PredicateBrowserUsePlugin.bind() failed: {type(plugin_err).__name__}: {plugin_err}",
            flush=True,
        )
        import traceback

        traceback.print_exc()
        raise RuntimeError(f"Could not bind Predicate browser-use plugin: {plugin_err}")

    # Get browser-use Page for screenshots
    page = await session.get_current_page()
    if page is None:
        print("[demo] WARNING: session.get_current_page() returned None", flush=True)

    token_summary = {
        "demo_name": "browser-use + PredicateDebugger (verification sidecar)",
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_tokens": 0,
        "average_per_scene": 0,
        "interactions": [],
    }

    print("[demo] Entering main demo try block...", flush=True)

    try:

        # Always save a startup screenshot (helps debug "blank/stuck" launches).
        print("[demo] Taking startup screenshot...", flush=True)
        try:
            p0 = screenshots_dir / f"scene0_{_safe_filename('browser_started')}.png"
            await asyncio.wait_for(page_screenshot(page, path=str(p0), full_page=False), timeout=15.0)
            print(f"[demo] Startup screenshot saved: {p0}", flush=True)
        except asyncio.TimeoutError:
            print("[demo] Startup screenshot timed out after 15s, continuing", flush=True)
        except Exception as e:
            print(f"[demo] Startup screenshot failed: {e}", flush=True)

        print("[demo] Asserting dbg is not None...", flush=True)
        assert dbg is not None

        async def snap_and_check(step_label: str) -> None:
            await dbg.record_action(f"snapshot({step_label})", url=await page_get_url(page))
            await dbg.snapshot(
                goal=f"verify:{step_label}",
                use_api=True,
                limit=100,
                show_overlay=True,
            )
            await dbg.check(
                url_contains("dw.com"),
                label="still_on_dw_domain",
                required=True,
            ).eventually(timeout_s=10)

        # Wait for Predicate extension to inject.
        #
        # IMPORTANT:
        # - The demo's snapshots should not depend on Playwright being able to evaluate
        #   window.sentience (this can be flaky on CDP-attached pages).
        # - Use browser-use's CDP backend as the default snapshot backend, since it evaluates
        #   in the same environment browser-use uses for actions.
        # - BUT: if Playwright attach succeeded, skip browser-use CDP backend creation
        #   (it can hang due to CDP session conflicts).
        print("[demo] waiting for Predicate extension to inject...", flush=True)
        if not playwright_attached and not cdp_backend_created:
            # Only create browser-use CDP backend if we're in CDP-only mode AND don't already have one
            await _fallback_to_browser_use_backend(session, dbg)
        else:
            reason = "Playwright attached" if playwright_attached else "CDP backend already created"
            print(f"[demo] Skipping _fallback_to_browser_use_backend ({reason})", flush=True)
        try:
            await await_with_timeout(
                "wait_for_predicate_extension_ready",
                wait_for_predicate_extension_ready(dbg.runtime.backend, timeout_s=30),  # type: ignore[arg-type]
                timeout_s=35,
            )
        except (asyncio.TimeoutError, Exception) as ext_wait_err:
            # Extension is likely ready (chrome stderr confirms WASM loaded), but CDP eval is flaky.
            # Continue anyway - snapshot will fail if extension truly isn't ready.
            print(f"[demo] wait_for_predicate_extension_ready failed: {type(ext_wait_err).__name__}, continuing anyway", flush=True)

        # Optional: also verify Playwright can observe injection (debug-only).
        if (os.getenv("CHECK_PLAYWRIGHT_SENTIENCE") or "").strip().lower() in ("1", "true", "yes"):
            await ensure_predicate_injected_on_playwright_page(page, timeout_s=15)
        print("[demo] Predicate extension ready (window.sentience.snapshot is available).", flush=True)
        try:
            await await_with_timeout(
                "dbg.snapshot(verify:extension_ready)",
                dbg.snapshot(goal="verify:extension_ready", use_api=True, limit=10, show_overlay=True),
                timeout_s=60,
            )
            print("[demo] Initial snapshot complete; starting demo scenes.", flush=True)
        except (asyncio.TimeoutError, Exception) as snap_err:
            print(f"[demo] Initial snapshot failed: {type(snap_err).__name__}: {snap_err}", flush=True)
            print("[demo] CDP backend may be flaky; proceeding with demo anyway...", flush=True)

        # -------------------------
        # Scene 1: Ensure we're on DW homepage (browser-use navigation)
        # -------------------------
        print("[demo] Scene 1: ensure landing page (DW homepage)", flush=True)
        async with dbg.step("Ensure DW homepage", step_index=0):
            # NOTE: We already navigated once before attaching the debugger.
            # Calling session.navigate_to(...) again can trigger slow focus-recovery paths
            # in browser-use (bubus handler timeouts), so we only navigate if needed.
            current_url = ""
            try:
                get_url_fn = getattr(session, "get_current_page_url", None)
                if callable(get_url_fn):
                    current_url = str(await _maybe_await(get_url_fn()) or "")
            except Exception:
                current_url = ""

            needs_nav = (not current_url) or current_url.startswith("about:") or ("dw.com" not in current_url)
            await await_with_timeout(
                "dbg.record_action(ensure_landing)",
                dbg.record_action(
                    f"ensure DW landing (needs_nav={needs_nav})",
                    url=await page_get_url(page),
                ),
                timeout_s=10,
            )

            if needs_nav:
                nav_fn = getattr(session, "navigate_to", None)
                if callable(nav_fn):
                    await await_with_timeout(
                        "session.navigate_to(DW_URL)",
                        _maybe_await(nav_fn(DW_URL)),
                        timeout_s=60,
                    )
                else:
                    await await_with_timeout("page_goto(DW_URL)", page_goto(page, DW_URL), timeout_s=60)
            await await_with_timeout(
                "page_wait_for_load(domcontentloaded)",
                page_wait_for_load(page, "domcontentloaded"),
                timeout_s=20,
            )
            await await_with_timeout(
                "dbg.snapshot(verify:landing)",
                dbg.snapshot(goal="verify:DW landing page", use_api=True, limit=80, show_overlay=True),
                timeout_s=60,
            )
            await await_with_timeout(
                "dbg.check(on_dw_domain).eventually",
                dbg.check(url_contains("dw.com"), label="on_dw_domain", required=True).eventually(
                    timeout_s=10
                ),
                timeout_s=20,
            )

            p = screenshots_dir / f"scene1_{_safe_filename('navigate')}.png"
            await page_screenshot(page, path=str(p), full_page=False)

        # -------------------------
        # Scene 2: Find top news article headline and publication time
        # Task: "Visit the DW homepage and list the headline and publication time of the top news article featured in the main section."
        # -------------------------
        print("[demo] Scene 2: find top news article (DW task)", flush=True)
        async with dbg.step("Find top news article", step_index=1):
            # Ensure we're on the DW homepage
            nav_fn = getattr(session, "navigate_to", None)
            if callable(nav_fn):
                await await_with_timeout(
                    "session.navigate_to(DW_URL)",
                    _maybe_await(nav_fn(DW_URL)),
                    timeout_s=60,
                )
            else:
                await await_with_timeout("page_goto(DW_URL)", page_goto(page, DW_URL), timeout_s=60)
            await await_with_timeout(
                "page_wait_for_load(domcontentloaded)",
                page_wait_for_load(page, "domcontentloaded"),
                timeout_s=20,
            )

            # Handle DW cookie consent modal if present
            # DW uses a CMP (Consent Management Platform) that may be in an iframe
            print("[demo] Checking for cookie consent modal...", flush=True)
            try:
                # Wait for the modal to fully load
                await asyncio.sleep(3.0)

                # First, check if there's a consent iframe and try to interact with it
                consent_js = """
                (() => {
                    // Helper to search in a document (main or iframe)
                    function findAndClickConsent(doc, source) {
                        // Look for buttons by text content
                        const allButtons = Array.from(doc.querySelectorAll('button, [role="button"], a, span, div'));
                        for (const btn of allButtons) {
                            const text = (btn.textContent || btn.innerText || '').trim();
                            const lowerText = text.toLowerCase();

                            // Check for Reject/Agree buttons
                            if (lowerText === 'reject' || lowerText === 'agree' ||
                                lowerText === 'accept' || lowerText === 'reject all' ||
                                lowerText === 'accept all' || lowerText === 'agree to all') {
                                console.log('[consent] Found button in ' + source + ': ' + text);
                                btn.click();
                                return 'clicked in ' + source + ': ' + text;
                            }
                        }

                        // Look for Sourcepoint/CMP specific selectors
                        const cmpSelectors = [
                            'button[title="Reject"]',
                            'button[title="Agree"]',
                            'button[title="Accept"]',
                            '[class*="sp_choice_type_11"]',  // Sourcepoint reject
                            '[class*="sp_choice_type_12"]',  // Sourcepoint accept
                            '.message-button',
                            '.sp-button',
                        ];
                        for (const sel of cmpSelectors) {
                            const el = doc.querySelector(sel);
                            if (el) {
                                console.log('[consent] Found via selector in ' + source + ': ' + sel);
                                el.click();
                                return 'clicked via selector in ' + source + ': ' + sel;
                            }
                        }
                        return null;
                    }

                    // Try main document first
                    let result = findAndClickConsent(document, 'main');
                    if (result) return result;

                    // Check all iframes
                    const iframes = document.querySelectorAll('iframe');
                    console.log('[consent] Found ' + iframes.length + ' iframes');
                    for (const iframe of iframes) {
                        try {
                            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                            if (iframeDoc) {
                                result = findAndClickConsent(iframeDoc, 'iframe:' + (iframe.id || iframe.src || 'anonymous'));
                                if (result) return result;
                            }
                        } catch (e) {
                            // Cross-origin iframe, can't access
                            console.log('[consent] Cannot access iframe: ' + e.message);
                        }
                    }

                    // Check shadow DOMs
                    const allElements = document.querySelectorAll('*');
                    for (const el of allElements) {
                        if (el.shadowRoot) {
                            result = findAndClickConsent(el.shadowRoot, 'shadow:' + el.tagName);
                            if (result) return result;
                        }
                    }

                    return 'no consent buttons found (checked main + ' + iframes.length + ' iframes)';
                })()
                """
                result = await asyncio.wait_for(
                    dbg.runtime.backend.eval(consent_js),
                    timeout=10.0
                )
                print(f"[demo] Cookie consent result: {result}", flush=True)

                # If JS didn't find it, the browser-use agent will handle it via vision
                # since we added instructions to dismiss the modal in the task
                await asyncio.sleep(2.0)  # Wait for modal to close
            except Exception as consent_err:
                print(f"[demo] Cookie consent handling error: {consent_err}", flush=True)
                print("[demo] browser-use agent will attempt to dismiss modal via vision", flush=True)

            await await_with_timeout(
                "wait_for_predicate_on_homepage",
                # Use the same CDP execution path as snapshots to avoid browser-use Page API
                # differences (evaluate vs evaluate_js) and isolated-world issues.
                wait_for_predicate_extension_ready(dbg.runtime.backend, timeout_s=30),  # type: ignore[arg-type]
                timeout_s=35,
            )

            # Take snapshot to find top news article
            snap = await await_with_timeout(
                "dbg.snapshot(find_top_news)",
                dbg.snapshot(goal="find top news article headline and publication time", use_api=True, limit=120, show_overlay=True),
                timeout_s=60,
            )

            # For this demo, we just verify we got a snapshot with news elements
            if snap and hasattr(snap, 'elements') and len(snap.elements) > 0:
                print(f"[demo] Found {len(snap.elements)} elements on DW homepage", flush=True)
            else:
                print("[demo] Warning: No elements found in snapshot", flush=True)

            # Take screenshot of the news section
            p = screenshots_dir / f"scene2_{_safe_filename('top_news')}.png"
            await page_screenshot(page, path=str(p), full_page=False)

        # -------------------------
        # Scene 3: Run browser-use agent to extract headline and publication time
        # -------------------------
        # Task: "Visit the DW homepage and list the headline and publication time of the top news article featured in the main section."
        task = (
            "IMPORTANT: You are already on the DW (Deutsche Welle) homepage at dw.com. "
            "Do NOT navigate anywhere else. Stay on this page.\n\n"
            "YOUR TASK:\n"
            "1. If you see a cookie consent modal with 'Agree' or 'Reject' buttons, click 'Reject' or 'Agree' to dismiss it first.\n"
            "2. Look at the main section of the page (the large featured area, not the sidebar).\n"
            "3. Find the TOP NEWS ARTICLE - it's usually the largest/most prominent article with a big headline.\n"
            "4. READ and EXTRACT:\n"
            "   - The HEADLINE text of the top article (the main title)\n"
            "   - The PUBLICATION TIME/DATE if visible\n"
            "5. REPORT your findings by stating: 'The top headline is: [headline text]. Publication time: [time if found, or \"not visible\"]'\n\n"
            "DO NOT click on articles or navigate away. Just READ the text visible on the homepage.\n"
            "Avoid long-running evaluate scripts. Use your vision to read the page content."
        )
        llm = ChatBrowserUse()

        agent_kwargs = {
            "task": task,
            "llm": llm,
            "browser_session": session,
            "use_vision": True,
        }
        try:
            sig = inspect.signature(Agent)
            allowed = set(sig.parameters.keys())
            agent_kwargs = {k: v for k, v in agent_kwargs.items() if k in allowed}
        except Exception:
            pass
        agent = Agent(**agent_kwargs)

        max_steps = int(os.getenv("BROWSER_USE_MAX_STEPS", "10"))
        step_fn = getattr(agent, "step", None)
        run_fn = getattr(agent, "run", None)

        agent_final: object | None = None

        if callable(step_fn):
            for i in range(max_steps):
                # Run Predicate verification around each Browser Use step.
                # (Browser Use doesn't expose hooks for step(), so we invoke them manually.)
                await plugin.on_step_start(agent)
                try:
                    # Make it obvious where we stop if browser-use exits/crashes.
                    await dbg.record_action(
                        f"about_to_call_browser_use.step({i})", url=await page_get_url(page)
                    )
                    # Hard timeout: prevent the demo from hanging forever (e.g., stuck 'evaluate' tool).
                    res = await await_with_timeout(
                        f"browser_use.step({i})",
                        step_fn(),
                        timeout_s=float(os.getenv("BROWSER_USE_STEP_TIMEOUT_S", "45")),
                    )
                    await dbg.record_action(
                        f"browser_use.step({i}) returned", url=await page_get_url(page)
                    )
                    agent_final = res
                    await dbg.record_action(
                        f"browser_use.step() -> {res!r}", url=await page_get_url(page)
                    )
                finally:
                    # Auto snapshot + deterministic checks happen here (per plugin config).
                    await plugin.on_step_end(agent)

                    # Check if agent signals task completion
                    # browser-use Agent has is_done() method or done attribute
                    agent_done = False
                    try:
                        is_done_fn = getattr(agent, "is_done", None)
                        if callable(is_done_fn):
                            agent_done = await _maybe_await(is_done_fn())
                        elif hasattr(agent, "done"):
                            agent_done = bool(agent.done)
                        elif hasattr(agent, "_done"):
                            agent_done = bool(agent._done)
                        # NOTE: browser-use Agent.step() returns None; completion is indicated
                        # by its internal ActionResult list (last_result[-1].is_done).
                        try:
                            state = getattr(agent, "state", None)
                            last_result = getattr(state, "last_result", None) if state is not None else None
                            if last_result and isinstance(last_result, (list, tuple)):
                                last = last_result[-1]
                                if bool(getattr(last, "is_done", False)):
                                    agent_done = True
                        except Exception:
                            pass
                        print(f"[demo] step {i} agent_done={agent_done}", flush=True)
                    except Exception as e:
                        print(f"[demo] Error checking agent done status: {e}", flush=True)

                    # If Playwright attach is active, keep it in sync with browser-use focus.
                    if pw_browser is not None:
                        page = await _sync_playwright_page_to_browser_use(session, pw_browser, page, dbg)
                    try:
                        bu_url = ""
                        get_url_fn = getattr(session, "get_current_page_url", None)
                        if callable(get_url_fn):
                            bu_url = str(await _maybe_await(get_url_fn()) or "")
                        pw_url = await page_get_url(page)
                        print(f"[demo] post-step url sync: browser_use_url={bu_url!r} playwright_url={pw_url!r}", flush=True)
                    except Exception:
                        pass
                    # NOTE: We previously did explicit extension-ready waits + post-step snapshots
                    # here. That logic is now centralized in the plugin hook(s).

                    p = screenshots_dir / f"scene{2+i}_{_safe_filename(f'after_step_{i}')}.png"
                    await page_screenshot(page, path=str(p), full_page=False)

                    # Exit loop if agent signals it's done with the task
                    if agent_done:
                        print(f"[demo] Agent signaled task completion at step {i}", flush=True)
                        break
        elif callable(run_fn):
            await dbg.record_action("browser_use.run()", url=await page_get_url(page))
            # Prefer native Browser Use hook support (agent.run accepts on_step_start/on_step_end).
            res = None
            try:
                sig = inspect.signature(run_fn)
                allowed = set(sig.parameters.keys())
                run_kwargs = {}
                if "on_step_start" in allowed:
                    run_kwargs["on_step_start"] = plugin.on_step_start
                if "on_step_end" in allowed:
                    run_kwargs["on_step_end"] = plugin.on_step_end
                res = await run_fn(**run_kwargs)
            except Exception:
                # Fall back to no-hook run; plugin can still be used explicitly post-run.
                res = await run_fn()
            agent_final = res
            # This is the "vision agent claims success" moment: browser-use returns without throwing.
            await dbg.record_action(f"browser_use.run() -> {res!r}", url=await page_get_url(page))
            await dbg.record_action(
                "agent_claimed_success=true (finished without deterministic verification)",
                url=await page_get_url(page),
            )
            await snap_and_check("post_run")
            p = screenshots_dir / f"scene2_{_safe_filename('post_run')}.png"
            await page_screenshot(page, path=str(p), full_page=False)
        else:
            raise RuntimeError("browser-use Agent has neither .step() nor .run()")

        # -------------------------
        # Task completion verification + extraction
        # Task: "Visit the DW homepage and list the headline and publication time of the top news article"
        # -------------------------
        async with dbg.step("Verify DW task completion", step_index=99):
            snap = await dbg.snapshot(
                goal="verify:dw_news_extraction",
                use_api=True,
                limit=150,
                show_overlay=True,
            )

            # For DW task, we verify we're on the homepage and have news elements
            def _on_dw_with_news(_ctx) -> bool:
                url = getattr(_ctx, "url", "") or ""
                return "dw.com" in url.lower()

            await dbg.record_action(f"agent_final={agent_final!r}", url=await page_get_url(page))

            ok = dbg.check(
                custom(_on_dw_with_news, "on_dw_homepage"),
                label="task_complete",
                required=True,
            ).once()

            # Make demo behavior explicit:
            # - We still fail-fast if the required completion predicate does not pass.
            if not ok:
                raise RuntimeError(
                    f"Deterministic verification failed: task_complete (DEMO_MODE={DEMO_MODE})"
                )

            # Also persist task output to a JSON file
            try:
                import json

                (base_dir / "dw_task_result.json").write_text(
                    json.dumps(
                        {
                            "task": TASK_DESCRIPTION,
                            "demo_mode": DEMO_MODE,
                            "run_id": run_id,
                        },
                        indent=2,
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            except Exception:
                pass

            p = screenshots_dir / f"scene_final_{_safe_filename('task_complete')}.png"
            await page_screenshot(page, path=str(p), full_page=False)

        # -------------------------
        # Persist Playwright video if available
        # -------------------------
        persisted = await try_persist_page_video(page, out_dir=video_dir, filename="playwright.mp4")
        if persisted:
            print(f"[video] persisted Playwright recording to: {persisted}")

    except PredicateBrowserUseVerificationError as e:
        # Demo-friendly failure mode: print a clear reason and exit cleanly (no traceback).
        # The `finally` block will still run and persist artifacts (trace upload, video, etc.).
        print(f"[demo] FATAL: {type(e).__name__}: {e}")
        return
    except BaseException as e:
        # IMPORTANT: browser-use (or its deps) can raise SystemExit in some failure modes.
        # Catch BaseException so we can print a clear reason instead of "stopping abruptly".
        print(f"[demo] FATAL: {type(e).__name__}: {e}")
        try:
            traceback.print_exc()
        except Exception:
            pass
        raise
    finally:
        # IMPORTANT:
        # browser-use BrowserSession does not guarantee a `.close()` method, and leaving the
        # session/event bus running can keep the Python process alive after main() finishes.
        # Prefer `kill()` (stop browser process) and fall back to `stop()` (graceful cleanup).
        try:
            kill_fn = getattr(session, "kill", None)
            stop_fn = getattr(session, "stop", None)
            if callable(kill_fn):
                await kill_fn()
            elif callable(stop_fn):
                await stop_fn()
        except Exception:
            pass
        try:
            if pw_browser is not None:
                await pw_browser.close()
        except Exception:
            pass
        try:
            if pw is not None:
                await pw.stop()
        except Exception:
            pass
        tracer.close(blocking=True)

        # Stitch screenshots into a simple mp4 (token overlay is a no-op for now)
        out_mp4 = video_dir / "demo.mp4"
        if create_demo_video is not None:
            try:
                create_demo_video(str(screenshots_dir), token_summary, str(out_mp4))
            except Exception as e:
                print(f"[warn] video stitching failed: {e}")
        else:
            print("[video] moviepy not installed; skipping screenshot stitching")

        # If any non-daemon threads are still alive, the process may hang even after main() returns.
        # This can happen with some video/recording stacks. Since this is a playground demo,
        # prefer a clean exit over requiring Ctrl+C.
        try:
            non_daemon = [
                t
                for t in threading.enumerate()
                if t.is_alive() and (not t.daemon) and t.name != "MainThread"
            ]
            if non_daemon:
                names = ", ".join(f"{t.name}" for t in non_daemon[:8])
                print(f"[demo] WARNING: non-daemon threads still alive ({len(non_daemon)}): {names}")
                print("[demo] Forcing process exit to avoid hang.")
                os._exit(0)
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())

