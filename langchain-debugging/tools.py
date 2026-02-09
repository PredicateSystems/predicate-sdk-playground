from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ClickTarget:
    label: str
    x: float
    y: float
    meta: dict[str, Any]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def pick_click_target_from_snapshot(
    snap: Any,
    query: str,
    *,
    max_candidates: int = 120,
) -> ClickTarget | None:
    """
    Best-effort, deterministic selection of an element from a Sentience snapshot.

    We intentionally keep this simple: prefer elements whose (name/text/nearby_text)
    contains the query string, then break ties by fused_rank_index / y position.
    """
    q = _norm(query)
    if not q:
        return None

    try:
        elements: Iterable[Any] = list(getattr(snap, "elements", []) or [])[:max_candidates]
    except Exception:
        return None

    best: tuple[int, float, float, Any] | None = None
    for e in elements:
        try:
            name = _norm(str(getattr(e, "name", "") or ""))
            text = _norm(str(getattr(e, "text", "") or ""))
            near = _norm(str(getattr(e, "nearby_text", "") or ""))
            role = _norm(str(getattr(e, "role", "") or ""))
            fused = int(getattr(e, "fused_rank_index", 10_000) or 10_000)
            bbox = getattr(e, "bbox", None)
            x = float(getattr(bbox, "x", 0.0) or 0.0)
            y = float(getattr(bbox, "y", 9_999.0) or 9_999.0)
            w = float(getattr(bbox, "width", 0.0) or 0.0)
            h = float(getattr(bbox, "height", 0.0) or 0.0)
            if w <= 2 or h <= 2:
                continue

            hay = " ".join([name, text, near])
            if q not in hay:
                continue

            # Prefer clickable-ish roles lightly; but don't hardcode too much.
            role_bonus = 0
            if role in {"button", "link"}:
                role_bonus = -50

            score = role_bonus + fused
            key = (score, y, x, e)
            if best is None or key < best:
                best = key
        except Exception:
            continue

    if best is None:
        return None

    _score, _y, _x, e = best
    bbox = getattr(e, "bbox", None)
    x0 = float(getattr(bbox, "x", 0.0) or 0.0)
    y0 = float(getattr(bbox, "y", 0.0) or 0.0)
    w0 = float(getattr(bbox, "width", 0.0) or 0.0)
    h0 = float(getattr(bbox, "height", 0.0) or 0.0)
    cx = x0 + max(1.0, w0) / 2.0
    cy = y0 + max(1.0, h0) / 2.0

    label = (getattr(e, "name", None) or getattr(e, "text", None) or query) or query
    meta = {
        "query": query,
        "role": getattr(e, "role", None),
        "name": getattr(e, "name", None),
        "text": getattr(e, "text", None),
        "nearby_text": getattr(e, "nearby_text", None),
        "fused_rank_index": getattr(e, "fused_rank_index", None),
        "bbox": {
            "x": x0,
            "y": y0,
            "width": w0,
            "height": h0,
        },
    }
    return ClickTarget(label=str(label), x=cx, y=cy, meta=meta)


async def tool_goto(page: Any, url: str) -> str:
    await page.goto(url, wait_until="domcontentloaded")
    return f"goto({url})"


async def tool_click_at(page: Any, x: float, y: float) -> str:
    await page.mouse.click(x, y)
    return f"click_at({x:.0f},{y:.0f})"


async def tool_type_text(page: Any, text: str) -> str:
    """
    Type into the currently focused element.
    Keep it simple + deterministic: no selectors, just keyboard events.
    """
    t = text or ""
    if not t:
        return "type_text(empty)"
    await page.keyboard.type(t)
    return f"type_text({t!r})"


async def tool_press(page: Any, key: str) -> str:
    k = (key or "").strip() or "Enter"
    await page.keyboard.press(k)
    return f"press({k})"


async def tool_scroll_by(page: Any, dy: int) -> str:
    """
    Scroll the primary scrolling element. Some sites use nested scrollers / overflow rules,
    so we verify scrollY before/after and fall back to wheel/keyboard if needed.
    """
    before = 0
    after = 0
    try:
        before = int(
            await page.evaluate(
                "() => Math.round((document.scrollingElement || document.documentElement || document.body).scrollTop || window.scrollY || 0)"
            )
        )
    except Exception:
        before = 0

    try:
        after = int(
            await page.evaluate(
                """(dy) => {
  const el = document.scrollingElement || document.documentElement || document.body;
  const b = Math.round(el.scrollTop || window.scrollY || 0);
  el.scrollBy(0, dy);
  const a = Math.round(el.scrollTop || window.scrollY || 0);
  return a;
}""",
                dy,
            )
        )
    except Exception:
        after = before

    # Fallbacks if nothing moved.
    if abs(after - before) < max(5, abs(dy) // 20):
        try:
            await page.mouse.wheel(0, dy)
        except Exception:
            pass
        try:
            await page.keyboard.press("PageDown" if dy >= 0 else "PageUp")
        except Exception:
            pass
        try:
            after = int(
                await page.evaluate(
                    "() => Math.round((document.scrollingElement || document.documentElement || document.body).scrollTop || window.scrollY || 0)"
                )
            )
        except Exception:
            after = before

    return f"scroll_by(dy={dy}) scrollY:{before}->{after}"

