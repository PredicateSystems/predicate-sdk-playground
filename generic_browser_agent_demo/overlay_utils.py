"""
Overlay Dismissal Utilities for Generic Browser Agent Demo.

This module provides proactive overlay/modal dismissal to clear blocking elements
(cookie banners, newsletter popups, promotional overlays) BEFORE the agent starts
executing its plan.

The SDK's built-in ModalDismissalConfig triggers AFTER DOM changes from actions,
but many sites show blocking overlays immediately on page load. This module
handles those initial blocking overlays.

Key features:
- Multiple overlay detection strategies (modal_detected, ARIA roles, z-index, class names)
- ESC key press as first attempt
- Scoring system for close/accept buttons
- Iterative clicking with verification
- Wall-clock timeout to avoid stalling

Usage:
    from overlay_utils import dismiss_overlays_before_agent

    # After page load, before agent run:
    await dismiss_overlays_before_agent(runtime, browser)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Common class name patterns for overlays/modals
_OVERLAY_CLASS_PATTERNS = frozenset({
    "modal",
    "overlay",
    "popup",
    "dialog",
    "lightbox",
    "subscribe",
    "newsletter",
    "paywall",
    "interstitial",
    "splash",
    "promo",
    "announcement",
    "banner",
    "toast",
    "drawer",
    "sheet",
    "cookie",
    "consent",
    "gdpr",
})

# Z-index threshold for overlay detection
_OVERLAY_Z_INDEX_THRESHOLD = 1000


@dataclass(frozen=True)
class OverlayDismissResult:
    """Result of overlay dismissal attempt."""
    actions: tuple[str, ...]
    overlays_before: int
    overlays_after: int
    status: str


def _norm(s: Any) -> str:
    """Normalize string for comparison."""
    return str(s or "").strip().lower()


def _is_overlay_role(role: str) -> bool:
    """Check if role indicates an overlay."""
    r = (role or "").strip().lower()
    return r in {"dialog", "alertdialog"}


def _has_overlay_class(class_name: str | None) -> bool:
    """Check if element has a class name suggesting it's an overlay."""
    if not class_name:
        return False
    cn = class_name.lower()
    return any(p in cn for p in _OVERLAY_CLASS_PATTERNS)


def _count_overlays(snapshot: Any) -> int:
    """
    Count overlays using multiple detection strategies.

    Detection methods:
    1. Gateway-provided modal_detected/modal_grids (z-index based)
    2. ARIA role-based detection (dialog, alertdialog)
    3. Class name-based detection (modal, overlay, popup, etc.)
    4. Z-index based detection (elements with z_index >= 1000)
    5. Dismiss button heuristic (presence of common dismiss buttons)
    """
    try:
        # Prefer gateway-provided modal detection if available
        modal_detected = getattr(snapshot, "modal_detected", None)
        modal_grids = getattr(snapshot, "modal_grids", None)
        if modal_detected is True:
            return max(1, len(modal_grids or []))
        if modal_detected is None and modal_grids is not None and len(modal_grids) > 0:
            return len(modal_grids)

        # Heuristic: check for dismiss button patterns that indicate overlays
        # Common overlay dismiss buttons
        dismiss_indicators = (
            "close dialog", "close modal", "close popup",
            "accept", "decline", "preferences", "cookie",
            "no thanks", "not now", "maybe later", "dismiss",
        )
        els = getattr(snapshot, "elements", None) or []
        dismiss_button_count = 0
        for el in els:
            role = _norm(getattr(el, "role", ""))
            if role != "button":
                continue
            text = _norm(getattr(el, "text", "") or "")
            if any(p in text for p in dismiss_indicators):
                dismiss_button_count += 1

        # If we see 2+ dismiss-style buttons, there's likely an overlay
        if dismiss_button_count >= 2:
            return 1

        # Fallback: scan elements for overlay patterns
        els = getattr(snapshot, "elements", None) or []
        n = 0
        seen_high_z = False

        # Get viewport for size heuristics
        vp_w = None
        vp_h = None
        try:
            vp = getattr(snapshot, "viewport", None)
            if vp is not None:
                vp_w = getattr(vp, "width", None)
                vp_h = getattr(vp, "height", None)
        except Exception:
            pass

        def _is_large_overlay(el: Any) -> bool:
            """Check if element is large enough to be a blocking overlay."""
            try:
                bbox = getattr(el, "bbox", None)
                if bbox is None:
                    return False
                w = float(getattr(bbox, "width", 0.0) or 0.0)
                h = float(getattr(bbox, "height", 0.0) or 0.0)
                if w <= 0.0 or h <= 0.0:
                    return False
                area = w * h
                # Minimum area threshold (~400x300)
                if area < 120_000.0:
                    return False
                # Check viewport coverage if available
                if vp_w and vp_h:
                    try:
                        area_ratio = area / (float(vp_w) * float(vp_h))
                        if area_ratio < 0.10:
                            return False
                    except Exception:
                        pass
                return True
            except Exception:
                return False

        for el in els:
            # Check ARIA role
            if _is_overlay_role(getattr(el, "role", "")):
                n += 1
                continue
            # Check class name for overlay patterns
            class_name = getattr(el, "class_name", None) or getattr(el, "className", None)
            if _has_overlay_class(class_name):
                n += 1
                continue
            # Check z-index for high-z elements
            z_index = getattr(el, "z_index", None)
            if (
                z_index is not None
                and z_index >= _OVERLAY_Z_INDEX_THRESHOLD
                and not seen_high_z
                and _is_large_overlay(el)
            ):
                role_l = _norm(getattr(el, "role", ""))
                if role_l in {"button", "link"}:
                    # Only count if class strongly suggests overlay
                    if not _has_overlay_class(str(class_name or "")):
                        continue
                seen_high_z = True
                n += 1
        return n
    except Exception:
        return 0


def _word_match(pattern: str, text: str) -> bool:
    """Match pattern as word boundary (not substring of longer word)."""
    import re
    if len(pattern) <= 2:
        # For short patterns (icons), require exact match
        return text == pattern or text.strip() == pattern
    # For longer patterns, use word boundary
    try:
        return bool(re.search(r'\b' + re.escape(pattern) + r'\b', text))
    except Exception:
        return pattern in text


# Button text patterns for scoring
_ACCEPT_PHRASES = (
    "accept all", "accept", "agree", "i agree", "allow all", "allow",
    "okay", "got it", "continue", "i understand",
)
_ACCEPT_EXACT = ("ok", "yes")

_CLOSE_PHRASES = (
    "close", "dismiss", "cancel", "skip", "no thanks", "no, thanks",
    "reject", "decline", "deny", "not now", "maybe later", "not interested",
    "no thank you", "close dialog", "close modal", "close popup",
    "close overlay", "close banner", "dismiss banner", "dismiss dialog",
)
_CLOSE_ICONS = ("x", "×", "✕", "✖", "✗", "╳", "ⓧ")
_CLOSE_EXACT = ("later",)

_AVOID_WORDS = (
    "learn more", "more info", "manage preferences", "preferences",
    "settings", "customize", "options", "details", "policy",
    "sign up", "sign in", "login", "log in", "register",
    "create account", "subscribe", "submit", "join", "get started",
)


def _is_clickable_control(el: Any) -> bool:
    """Check if element is a clickable control."""
    try:
        role = _norm(getattr(el, "role", ""))
        if role in {"button", "link"}:
            return True
        vc = getattr(el, "visual_cues", None)
        if vc is not None and bool(getattr(vc, "is_clickable", False)):
            return True
    except Exception:
        pass
    return False


def _label_variants(el: Any) -> list[str]:
    """Get multiple label sources for an element."""
    out: list[str] = []
    try:
        out.append(_norm(getattr(el, "text", None) or ""))
        out.append(_norm(getattr(el, "name", None) or ""))
        out.append(_norm(getattr(el, "aria_label", None) or getattr(el, "ariaLabel", None) or ""))
        out.append(_norm(getattr(el, "title", None) or ""))
    except Exception:
        pass
    return [s for s in out if s]


def _collect_candidates(
    elements: list[Any],
    page_host: str,
    overlay_bbox: tuple[float, float, float, float] | None,
) -> list[tuple[int, Any, str]]:
    """Collect and score candidate dismiss buttons."""
    candidates: list[tuple[int, Any, str]] = []

    for el in elements:
        # Skip occluded elements
        if bool(getattr(el, "is_occluded", False)):
            continue
        if not _is_clickable_control(el):
            continue

        # If we have overlay bbox, filter to controls within it
        if overlay_bbox is not None:
            try:
                bbox = getattr(el, "bbox", None)
                if bbox is not None:
                    bx, by, bw, bh = overlay_bbox
                    ex = float(getattr(bbox, "x", 0.0) or 0.0)
                    ey = float(getattr(bbox, "y", 0.0) or 0.0)
                    ew = float(getattr(bbox, "width", 0.0) or 0.0)
                    eh = float(getattr(bbox, "height", 0.0) or 0.0)
                    cx, cy = ex + ew/2, ey + eh/2
                    pad = 24.0
                    if not ((bx - pad) <= cx <= (bx + bw + pad) and (by - pad) <= cy <= (by + bh + pad)):
                        continue
            except Exception:
                pass

        labels = _label_variants(el)
        if not labels:
            continue
        label = labels[0]
        score = 0

        # Penalize external links
        try:
            role = _norm(getattr(el, "role", ""))
            href = str(getattr(el, "href", None) or "").strip()
            if role == "link" and href:
                href_host = ""
                try:
                    href_host = (urlparse(href).hostname or "").lower()
                except Exception:
                    pass
                if href_host and page_host and href_host != page_host:
                    score -= 200
        except Exception:
            pass

        # Score based on button text
        for lbl in labels:
            # Accept patterns
            if any(_word_match(k, lbl) for k in _ACCEPT_PHRASES):
                score += 100
            if lbl in _ACCEPT_EXACT:
                score += 100
            # Close patterns
            if lbl in _CLOSE_EXACT:
                score += 80
            if any(_word_match(k, lbl) for k in _CLOSE_PHRASES):
                score += 80
            if lbl in _CLOSE_ICONS:
                score += 80
            # Cookie/consent bonus
            if "cookie" in lbl or "consent" in lbl:
                score += 20
            # Avoid patterns
            if any(k in lbl for k in _AVOID_WORDS):
                score -= 50
            # Newsletter penalty for accept
            if "newsletter" in lbl or "subscribe" in lbl:
                if any(_word_match(k, lbl) for k in _ACCEPT_PHRASES):
                    score -= 10

        if score > 0:
            candidates.append((score, el, label))

    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates


def _best_overlay_bbox(snap: Any) -> tuple[float, float, float, float] | None:
    """Find the best overlay container bounding box."""
    try:
        els = getattr(snap, "elements", None) or []
    except Exception:
        return None

    best = None
    best_area = 0.0
    for el in els:
        try:
            z = getattr(el, "z_index", None)
            if z is None or float(z) < float(_OVERLAY_Z_INDEX_THRESHOLD):
                continue
            role = _norm(getattr(el, "role", ""))
            if role in {"button", "link"}:
                continue
            bbox = getattr(el, "bbox", None)
            if bbox is None:
                continue
            w = float(getattr(bbox, "width", 0.0) or 0.0)
            h = float(getattr(bbox, "height", 0.0) or 0.0)
            if w <= 0.0 or h <= 0.0:
                continue
            area = w * h
            if area > best_area:
                best_area = area
                best = (
                    float(getattr(bbox, "x", 0.0) or 0.0),
                    float(getattr(bbox, "y", 0.0) or 0.0),
                    w, h
                )
        except Exception:
            continue
    return best


async def dismiss_overlays(
    runtime,
    browser,
    *,
    max_rounds: int = 2,
    snapshot_limit: int = 100,
    max_clicks_per_round: int = 3,
    use_api: bool | None = None,
    max_seconds: float = 8.0,
    verbose: bool = False,
) -> OverlayDismissResult:
    """
    Best-effort cross-site overlay dismissal (cookie banners, modals, popups).

    This function attempts to dismiss blocking overlays before the agent runs.
    It uses multiple detection strategies and clicks dismiss/accept buttons.

    Args:
        runtime: AgentRuntime instance
        browser: AsyncPredicateBrowser instance
        max_rounds: Maximum dismissal rounds
        snapshot_limit: Element limit for snapshots
        max_clicks_per_round: Maximum clicks per round
        use_api: Force API-based snapshots (None = auto)
        max_seconds: Wall-clock timeout
        verbose: Print debug info

    Returns:
        OverlayDismissResult with actions taken and overlay counts
    """
    actions: list[str] = []
    status = "unknown"

    # Snapshot options
    snap_kwargs = {"limit": snapshot_limit}
    if use_api is not None:
        snap_kwargs["use_api"] = use_api

    # Initial scan
    snap0 = await runtime.snapshot(goal="overlay_scan", **snap_kwargs)
    overlays_before = _count_overlays(snap0)

    if verbose:
        modal_detected = getattr(snap0, "modal_detected", None)
        modal_grids = getattr(snap0, "modal_grids", None)
        logger.info(
            f"[OVERLAY] Initial scan: overlays={overlays_before}, "
            f"modal_detected={modal_detected}, modal_grids={len(modal_grids or [])}"
        )

    # If no overlays, return immediately
    if overlays_before <= 0:
        return OverlayDismissResult(
            actions=tuple(actions),
            overlays_before=0,
            overlays_after=0,
            status="none",
        )

    start_t = time.monotonic()
    overlay_bbox = _best_overlay_bbox(snap0)

    # Get page host for external link detection
    page_host = ""
    try:
        page_url = str(browser.page.url or "")
        page_host = (urlparse(page_url).hostname or "").lower()
    except Exception:
        pass

    attempted_click_any = False

    for _round in range(max_rounds):
        # Timeout check
        if (time.monotonic() - start_t) > max_seconds and attempted_click_any:
            status = "timeout"
            if verbose:
                logger.info("[OVERLAY] Timeout reached")
            break

        if verbose:
            logger.info(f"[OVERLAY] Round {_round + 1}/{max_rounds}")

        # Try ESC first
        try:
            await browser.page.keyboard.press("Escape")
            actions.append('PRESS("Escape")')
            if verbose:
                logger.info("[OVERLAY] Pressed Escape")
        except Exception:
            pass

        # Re-scan
        snap = await runtime.snapshot(goal="overlay_scan", **snap_kwargs)

        # Check if overlays are gone
        if _count_overlays(snap) == 0:
            status = "gone"
            if verbose:
                logger.info("[OVERLAY] Overlays dismissed by Escape")
            break

        # Collect candidates
        elements = getattr(snap, "elements", None) or []
        candidates = _collect_candidates(elements, page_host, overlay_bbox)

        if verbose:
            logger.info(f"[OVERLAY] Found {len(candidates)} candidates")
            for i, (sc, _el, lbl) in enumerate(candidates[:5]):
                logger.info(f"  [{i}] score={sc} label={lbl[:40]!r}")

        if not candidates:
            status = "no_candidates"
            if verbose:
                logger.info("[OVERLAY] No dismiss candidates found")
            break

        # Click candidates
        clicks = 0
        clicked_labels: set[str] = set()

        while clicks < max_clicks_per_round:
            if (time.monotonic() - start_t) > max_seconds and attempted_click_any:
                status = "timeout"
                break

            # Filter already-clicked
            candidates = [c for c in candidates if c[2] not in clicked_labels]
            if not candidates:
                break

            _score, el, label = candidates[0]
            bbox = getattr(el, "bbox", None)
            if bbox is None:
                clicked_labels.add(label)
                candidates = candidates[1:]
                continue

            try:
                bbox_x = float(getattr(bbox, "x", 0.0))
                bbox_y = float(getattr(bbox, "y", 0.0))
                bbox_w = float(getattr(bbox, "width", 0.0))
                bbox_h = float(getattr(bbox, "height", 0.0))
                x = bbox_x + bbox_w / 2.0
                y = bbox_y + bbox_h / 2.0

                if verbose:
                    logger.info(f"[OVERLAY] Clicking '{label[:30]}' at ({x:.0f}, {y:.0f})")

                # Click using backend
                await runtime.backend.mouse_click(x, y)
                actions.append(f'OVERLAY_CLICK("{label[:40]}")')
                clicked_labels.add(label)
                clicks += 1
                attempted_click_any = True
            except Exception as e:
                if verbose:
                    logger.warning(f"[OVERLAY] Click failed: {e}")
                clicked_labels.add(label)
                continue

            # Wait for UI to settle
            try:
                await browser.page.wait_for_timeout(350)
            except Exception:
                pass

            # Check if overlay is gone
            snap_after = await runtime.snapshot(goal="overlay_verify", **snap_kwargs)
            if _count_overlays(snap_after) == 0:
                status = "gone"
                if verbose:
                    logger.info("[OVERLAY] Overlay dismissed after click")
                break

            # Update candidates from new snapshot
            try:
                overlay_bbox = _best_overlay_bbox(snap_after)
                candidates = _collect_candidates(
                    getattr(snap_after, "elements", None) or [],
                    page_host,
                    overlay_bbox,
                )
            except Exception:
                pass

        if status == "gone":
            break

    # Final count
    final_snap = await runtime.snapshot(goal="overlay_final", **snap_kwargs)
    overlays_after = _count_overlays(final_snap)

    if overlays_after == 0 and status not in ("gone", "none"):
        status = "gone"
    elif overlays_after > 0 and status not in ("timeout", "no_candidates"):
        status = "partial"

    if verbose:
        logger.info(f"[OVERLAY] Done: status={status}, before={overlays_before}, after={overlays_after}")

    return OverlayDismissResult(
        actions=tuple(actions),
        overlays_before=overlays_before,
        overlays_after=overlays_after,
        status=status,
    )


async def dismiss_overlays_before_agent(
    runtime,
    browser,
    *,
    verbose: bool = False,
) -> OverlayDismissResult:
    """
    Convenience wrapper to dismiss overlays before agent execution.

    This should be called after page load and before the agent's run() method.
    It handles the common case of initial page overlays (cookie banners, popups).

    Args:
        runtime: AgentRuntime instance
        browser: AsyncPredicateBrowser instance
        verbose: Print debug info

    Returns:
        OverlayDismissResult

    Example:
        async with AsyncPredicateBrowser() as browser:
            await browser.page.goto(url)

            runtime = AgentRuntime(backend=backend, tracer=tracer)

            # Dismiss initial overlays
            result = await dismiss_overlays_before_agent(runtime, browser, verbose=True)

            # Now run the agent
            await agent.run(runtime, task)
    """
    return await dismiss_overlays(
        runtime,
        browser,
        max_rounds=3,  # More rounds to handle multiple overlays
        snapshot_limit=100,
        max_clicks_per_round=4,  # More clicks per round
        use_api=True,  # Prefer gateway API for accurate modal detection
        max_seconds=12.0,  # More time for complex sites
        verbose=verbose,
    )
