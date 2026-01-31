"""
Best-effort helpers for Playwright video artifacts.

browser-use controls the Playwright context; video recording may or may not be enabled.
These helpers safely detect and persist the video path when available.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


async def try_persist_page_video(page: Any, *, out_dir: Path, filename: str) -> Path | None:
    """
    If Playwright video recording is enabled for the page context, persist the video to out_dir.

    Returns:
        Path to the persisted video, or None if no video is available.
    """
    try:
        video = getattr(page, "video", None)
        if video is None:
            return None
        path_coro = getattr(video, "path", None)
        if not callable(path_coro):
            return None
        src = await path_coro()
        if not src:
            return None
        src_path = Path(src)
        if not src_path.exists():
            return None
        out_dir.mkdir(parents=True, exist_ok=True)
        dst = out_dir / filename
        shutil.copyfile(src_path, dst)
        return dst
    except Exception:
        return None

