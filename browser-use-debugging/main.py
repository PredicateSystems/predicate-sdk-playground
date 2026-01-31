#!/usr/bin/env python3
"""
browser-use + SentienceDebugger demo (sidecar verification + trace).

This is intentionally a "minimal adapter" demo:
- browser-use owns the browser session
- SentienceDebugger attaches to the Playwright Page and verifies outcomes
- We emit per-step screenshots and stitch them into a simple mp4 with token overlays
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import os
import re
import sys
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

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

from sentience import SentienceDebugger, get_extension_dir
from sentience.agent_runtime import AgentRuntime
from sentience.backends import ExtensionNotLoadedError
from sentience.backends import BrowserUseAdapter
from sentience.models import SnapshotOptions
from sentience.tracer_factory import create_tracer
from sentience.verification import any_of, custom, exists, url_contains

from shared.playwright_video import try_persist_page_video
from shared.video_generator_simple import create_demo_video


ACE_URL = "https://www.acehardware.com"
QUERY = os.getenv("ACE_QUERY", "LED light bulbs")
DEMO_MODE = (os.getenv("DEMO_MODE") or "fix").strip().lower()  # "fail" | "fix"
START_URL = (os.getenv("BROWSER_USE_START_URL") or ACE_URL).strip()


def _safe_filename(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", s.strip())
    return s[:80].strip("_") or "step"


async def _sleep_ms(ms: int) -> None:
    await asyncio.sleep(ms / 1000.0)


async def _maybe_await(result):
    if inspect.isawaitable(result):
        return await result
    return result


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


async def wait_for_sentience_extension_ready(backend, *, timeout_s: float = 30.0) -> None:
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
        try:
            return await asyncio.wait_for(backend.eval(expr), timeout=timeout_s)
        except asyncio.TimeoutError:
            return "__EVAL_TIMEOUT__"

    while True:
        elapsed = time.monotonic() - start
        if elapsed >= timeout_s:
            break
        # 1) Check readiness (fast path)
        ready = "__EVAL_TIMEOUT__"
        try:
            ready = await _eval_with_timeout(
                "typeof window.sentience !== 'undefined' && typeof window.sentience.snapshot === 'function'"
            )
        except Exception:
            ready = "__EVAL_TIMEOUT__"

        if ready == "__EVAL_TIMEOUT__":
            consecutive_eval_timeouts += 1
        else:
            consecutive_eval_timeouts = 0

        if ready not in ("__EVAL_TIMEOUT__", False, None):
            return

        # 2) Once per second: print diagnostics (always attempt; never rely on a timing window)
        now_s = int(elapsed)
        if last_print_s != now_s:
            last_print_s = now_s
            try:
                last_diag = await _eval_with_timeout(
                    """
                    (() => ({
                        url: window.location.href,
                        sentience_defined: typeof window.sentience !== 'undefined',
                        sentience_snapshot: typeof window.sentience?.snapshot === 'function',
                        extension_id: document.documentElement.dataset.sentienceExtensionId || null
                    }))()
                    """
                )
            except Exception:
                last_diag = None

            if last_diag == "__EVAL_TIMEOUT__":
                print(f"[demo] waiting... (CDP eval timeout; streak={consecutive_eval_timeouts})")
            elif isinstance(last_diag, dict):
                print(
                    "[demo] waiting... "
                    f"url={last_diag.get('url')!s} "
                    f"extension_id={last_diag.get('extension_id')!s} "
                    f"sentience_defined={last_diag.get('sentience_defined')!s} "
                    f"sentience_snapshot={last_diag.get('sentience_snapshot')!s} "
                    f"timeout_streak={consecutive_eval_timeouts}"
                )
            else:
                print(f"[demo] waiting... (no diagnostics; streak={consecutive_eval_timeouts})")

        await _sleep_ms(200)

    raise RuntimeError(
        "Sentience extension did not become ready in time. "
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
    - Sentience extension does not inject on about:blank / about:*
    - Use BrowserSession.navigate_to() to navigate the existing tab, rather than
      opening a second tab (which often leaves an about:blank tab around).
    """
    get_url_fn = getattr(session, "get_current_page_url", None)
    nav_fn = getattr(session, "navigate_to", None)
    if not callable(get_url_fn) or not callable(nav_fn):
        return

    try:
        current_url = str(await _maybe_await(get_url_fn()) or "")
    except Exception:
        current_url = ""

    if current_url and not current_url.startswith("about:"):
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
        f"session.navigate_to({target_url})"
    )
    await _maybe_await(nav_fn(target_url))

    # Wait for the navigation to settle and for content scripts to inject.
    for _ in range(10):
        await _sleep_ms(300)
        try:
            u = str(await _maybe_await(get_url_fn()) or "")
        except Exception:
            u = ""
        if u and not u.startswith("about:"):
            return


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

    # We must load the Sentience extension for window.sentience.snapshot()
    sentience_ext = get_extension_dir()
    print(f"[demo] Sentience extension dir: {sentience_ext}")

    # IMPORTANT: Chrome only respects the LAST --load-extension arg.
    # browser-use ships with helpful default extensions; to combine them with Sentience,
    # we must load ALL extensions in a single --load-extension=path1,path2,... arg.
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
    try:
        from browser_use import BrowserProfile  # type: ignore

        temp_profile = BrowserProfile(enable_default_extensions=True)
        default_exts = []
        # Private method, but this is the official pattern used by browser-use's example.
        ensure_fn = getattr(temp_profile, "_ensure_default_extensions_downloaded", None)
        if callable(ensure_fn):
            default_exts = list(ensure_fn() or [])
        if default_exts:
            kept: list[str] = []
            skipped: list[tuple[str, str]] = []
            for p in default_exts:
                s = str(p)
                mv = _manifest_version(s)
                # Chrome 144 tends to reject MV2 extensions; if any fail, it can
                # effectively break extension loading. Keep only MV3.
                if mv is None:
                    skipped.append((s, "no manifest.json / unreadable"))
                elif mv < 3:
                    skipped.append((s, f"manifest_version={mv} (skip MV2)"))
                else:
                    kept.append(s)

            extension_paths.extend(kept)
            print(f"[demo] Found {len(default_exts)} browser-use default extensions")
            print(f"[demo] Keeping {len(kept)} MV3 default extensions; skipping {len(skipped)}")
            for s, why in skipped[:6]:
                print(f"[demo]   skip: {s} ({why})")
            if len(skipped) > 6:
                print(f"[demo]   ... +{len(skipped) - 6} more skipped")
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
    load_dotenv(dotenv_path=str(_REPO_ROOT / "sentience-sdk-playground" / ".env"), override=False)
    # Also allow a local ".env" (cwd / script dir) to override/add vars.
    load_dotenv(override=False)
    sentience_api_key = os.getenv("SENTIENCE_API_KEY")
    if not sentience_api_key:
        raise SystemExit("Missing SENTIENCE_API_KEY in environment.")

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
        api_key=sentience_api_key,
        run_id=run_id,
        upload_trace=True,
        goal=f"[demo] {run_label} | AceHardware search: {QUERY}",
        agent_type="sdk-playground/browser-use-debugging",
        llm_model="browser-use/ChatBrowserUse",
        start_url=ACE_URL,
    )

    print(f"[demo] run_label={run_label}")
    print(f"[demo] run_id={run_id} (UUID; used by Sentience Studio)")
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
            "Install: pip install \"sentienceapi[browser-use]\"\n"
            f"ImportError: {e}"
        ) from e

    profile_kwargs = _maybe_make_browser_profile_kwargs(record_video_dir=str(video_dir))
    profile = BrowserProfile(**profile_kwargs)
    session = BrowserSession(browser_profile=profile)
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

    # CRITICAL: avoid starting on about:blank.
    # Gateway snapshots still require the Sentience extension to collect raw elements, so we
    # must get onto a real URL before attempting any snapshots.
    page = None
    await ensure_session_on_real_url(session, start_url=START_URL, task_text=None)
    await debug_print_extension_targets(session)

    # Prefer using the existing page/tab (avoid leaving an about:blank tab around).
    page = await session.get_current_page()
    if page is not None:
        # In case the session API isn't available (older browser-use), do a best-effort
        # page-level navigation.
        current_url = await page_get_url(page)
        if not current_url or current_url.startswith("about:"):
            print(f"[demo] page_goto({START_URL}) (fallback; avoid about:blank)")
            await page_goto(page, START_URL, timeout=60_000)
            await page_wait_for_load(page, "domcontentloaded")
    else:
        # Last resort: create a page at the target URL.
        new_page_fn = getattr(session, "new_page", None)
        if callable(new_page_fn):
            print(f"[demo] session.new_page({START_URL}) (last-resort)")
            page = await _maybe_await(new_page_fn(START_URL))

    if page is None:
        raise RuntimeError("browser-use session did not provide a page")

    token_summary = {
        "demo_name": "browser-use + SentienceDebugger (verification sidecar)",
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_tokens": 0,
        "average_per_scene": 0,
        "interactions": [],
    }

    try:

        # Always save a startup screenshot (helps debug "blank/stuck" launches).
        try:
            p0 = screenshots_dir / f"scene0_{_safe_filename('browser_started')}.png"
            await page_screenshot(page, path=str(p0), full_page=False)
        except Exception:
            pass

        # IMPORTANT: browser-use's Page is CDP-driven and not a Playwright Page.
        # SentienceDebugger.attach(page, ...) is for Playwright Page only.
        # For browser-use we build a proper BrowserBackend via BrowserUseAdapter.
        #
        # CRITICAL FIX: Create the backend AFTER navigation to a real URL completes.
        # The Sentience extension's content script (injected_api.js) runs at document_idle
        # in the MAIN world. If we create the backend and cache the execution context
        # before the extension injects, window.sentience won't be visible.
        #
        # Give the page time to reach document_idle where the extension injects.
        print("[demo] waiting for page to reach document_idle (extension injects here)...")
        await _sleep_ms(2000)

        adapter = BrowserUseAdapter(session)
        backend = await adapter.create_backend()

        # Reset execution context to ensure we get a fresh context that can see
        # the extension's injected window.sentience API.
        backend.reset_execution_context()

        runtime = AgentRuntime(
            backend=backend,
            tracer=tracer,
            sentience_api_key=sentience_api_key,
            snapshot_options=SnapshotOptions(
                use_api=True,
                limit=100,
                screenshot=False,
                show_overlay=True,
                goal="browser-use-debug-demo",
                sentience_api_key=sentience_api_key,
            ),
        )
        dbg = SentienceDebugger(runtime=runtime)

        async def snap_and_check(step_label: str) -> None:
            await dbg.record_action(f"snapshot({step_label})", url=await page_get_url(page))
            await dbg.snapshot(
                goal=f"verify:{step_label}",
                use_api=True,
                limit=100,
                show_overlay=True,
            )
            await dbg.check(
                url_contains("acehardware.com"),
                label="still_on_ace_domain",
                required=True,
            ).eventually(timeout_s=10)

        # Wait for Sentience extension to be ready (otherwise snapshots will fail).
        # We do a longer explicit wait than the SDK default to reduce flakiness.
        print("[demo] waiting for Sentience extension to inject...")
        await wait_for_sentience_extension_ready(backend, timeout_s=30)
        await dbg.snapshot(goal="verify:extension_ready", use_api=True, limit=10, show_overlay=True)

        # -------------------------
        # Scene 1: Navigate
        # -------------------------
        async with dbg.step("Navigate to AceHardware", step_index=0):
            await dbg.record_action(f"page.goto({ACE_URL})", url=await page_get_url(page))
            await page_goto(page, ACE_URL)
            await page_wait_for_load(page, "domcontentloaded")
            # Reset execution context after navigation - extension re-injects on new page
            backend.reset_execution_context()
            await _sleep_ms(500)  # Brief delay for extension to inject
            await dbg.snapshot(goal="verify:landing", use_api=True, limit=80, show_overlay=True)
            await dbg.check(url_contains("acehardware.com"), label="on_ace_domain", required=True).eventually(
                timeout_s=10
            )

            p = screenshots_dir / f"scene1_{_safe_filename('navigate')}.png"
            await page_screenshot(page, path=str(p), full_page=False)

        # -------------------------
        # Scene 2..N: Run a real browser-use agent (with verification after each step)
        # -------------------------
        task = (
            f"Go to {ACE_URL} and search for {QUERY!r}. "
            "Make sure the search results page is loaded."
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
                async with dbg.step(f"browser-use step {i}", step_index=1 + i):
                    res = await step_fn()
                    agent_final = res
                    await dbg.record_action(f"browser_use.step() -> {res!r}", url=await page_get_url(page))
                    await dbg.snapshot(
                        goal=f"verify:after_step_{i}",
                        use_api=True,
                        limit=100,
                        show_overlay=True,
                    )

                    on_results = any_of(
                        url_contains("search"),
                        exists("text~'Results'"),
                        exists("text~'Search'"),
                    )
                    ok = await dbg.check(on_results, label="maybe_on_results").eventually(timeout_s=6)

                    p = screenshots_dir / f"scene{2+i}_{_safe_filename(f'after_step_{i}')}.png"
                    await page_screenshot(page, path=str(p), full_page=False)
                    if ok:
                        break
        elif callable(run_fn):
            async with dbg.step("browser-use run()", step_index=1):
                await dbg.record_action("browser_use.run()", url=await page_get_url(page))
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
        # -------------------------
        async with dbg.step("Extract first 5 products (verify task completion)", step_index=99):
            snap = await dbg.snapshot(
                goal="verify:extract",
                use_api=True,
                limit=150,
                show_overlay=True,
            )
            products = _extract_top_products(snap, k=5)

            def _has_5_with_prices(_ctx) -> bool:
                if len(products) != 5:
                    return False
                titles_ok = all(bool(p.get("title")) for p in products)
                price_count = sum(1 for p in products if (p.get("sale_price") or "").strip())
                return titles_ok and price_count >= 3

            def _strict_has_5_prices_and_search_state(_ctx) -> bool:
                # A stricter version that often catches vision drift / hallucinated extraction.
                if len(products) != 5:
                    return False
                titles_ok = all(bool(p.get("title")) for p in products)
                price_count = sum(1 for p in products if (p.get("sale_price") or "").strip())
                on_search_like_url = "search" in (getattr(_ctx, "url", "") or "").lower()
                return titles_ok and price_count == 5 and on_search_like_url

            await dbg.record_action(f"extracted_products={products!r}", url=await page_get_url(page))
            await dbg.record_action(f"agent_final={agent_final!r}", url=await page_get_url(page))

            # In DEMO_MODE=fail we intentionally inject a failing *required* check so you can
            # record a clean Studio walkthrough: failure → evidence → fix → rerun pass.
            if DEMO_MODE == "fail":
                # Prefer a "real" failure mode first: assert a strict, provable success condition.
                # If it unexpectedly passes (site stable, extraction good), fall back to a forced failure
                # so the demo remains recordable.
                strict_ok = dbg.check(
                    custom(_strict_has_5_prices_and_search_state, "strict_task_complete"),
                    label="task_complete_strict",
                    required=True,
                ).once()
                if strict_ok:
                    await dbg.record_action(
                        "strict_task_complete unexpectedly passed; forcing demo failure fallback",
                        url=await page_get_url(page),
                    )
                    dbg.check(
                        custom(lambda _ctx: False, "demo_intentional_failure_fallback"),
                        label="task_complete",
                        required=True,
                    ).once()
            else:
                dbg.check(
                    custom(_has_5_with_prices, "extracted_5_products"),
                    label="task_complete",
                    required=True,
                ).once()

            # Also persist extracted output to a JSON file for easy copy/paste in the video.
            try:
                import json

                (base_dir / "extracted_products.json").write_text(
                    json.dumps(
                        {
                            "query": QUERY,
                            "products": products,
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

    except Exception as e:
        print(f"[demo] ERROR: {e}")
        traceback.print_exc()
        raise
    finally:
        try:
            await session.close()
        except Exception:
            pass
        tracer.close(blocking=True)

        # Stitch screenshots into a simple mp4 (token overlay is a no-op for now)
        out_mp4 = video_dir / "demo.mp4"
        try:
            create_demo_video(str(screenshots_dir), token_summary, str(out_mp4))
        except Exception as e:
            print(f"[warn] video stitching failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())

