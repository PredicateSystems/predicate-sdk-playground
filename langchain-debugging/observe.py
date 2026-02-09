from __future__ import annotations

from typing import Any


def make_compact_observation(snap: Any, *, max_elements: int = 40) -> dict[str, Any]:
    """
    Convert a snapshot into a compact, prompt-friendly observation.

    We avoid raw DOM. We provide only the highest-signal ranked candidates.
    """
    obs: dict[str, Any] = {}

    try:
        obs["url"] = getattr(snap, "url", None)
        obs["dominant_group_key"] = getattr(snap, "dominant_group_key", None)
        obs["modal_detected"] = getattr(snap, "modal_detected", None)
        diag = getattr(snap, "diagnostics", None)
        if diag is not None:
            obs["diagnostics"] = {
                "confidence": getattr(diag, "confidence", None),
                "reasons": getattr(diag, "reasons", None),
                "requires_vision": getattr(diag, "requires_vision", None),
                "requires_vision_reason": getattr(diag, "requires_vision_reason", None),
            }
    except Exception:
        pass

    out_elems: list[dict[str, Any]] = []
    try:
        elems = list(getattr(snap, "elements", []) or [])[:max_elements]
        for e in elems:
            bbox = getattr(e, "bbox", None)
            out_elems.append(
                {
                    "rank": getattr(e, "fused_rank_index", None),
                    "role": getattr(e, "role", None),
                    "name": getattr(e, "name", None),
                    "text": getattr(e, "text", None),
                    "nearby_text": getattr(e, "nearby_text", None),
                    "bbox": {
                        "x": getattr(bbox, "x", None),
                        "y": getattr(bbox, "y", None),
                        "width": getattr(bbox, "width", None),
                        "height": getattr(bbox, "height", None),
                    }
                    if bbox is not None
                    else None,
                }
            )
    except Exception:
        pass

    obs["top_elements"] = out_elems
    return obs

