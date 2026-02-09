from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sentience.verification import custom, exists, url_contains


@dataclass
class CheckOutcome:
    label: str
    required: bool
    ok: bool | None  # None if not executed
    detail: str | None = None


def year_in_1990s(year: int | None) -> bool:
    return year is not None and 1990 <= year <= 1999


def extract_year_from_text(text: str) -> int | None:
    # Match 1990..1999 explicitly.
    m = re.search(r"\b(199[0-9])\b", text or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def make_verify_predicates(*, decade_required: str = "1990s"):
    """
    Create common predicates used by the LangGraph demo.
    """
    decade = (decade_required or "1990s").strip()
    return {
        "on_esquire_domain": url_contains("esquire.com"),
        # Loose signal that we are on the archive view for the required decade.
        "archive_decade_visible": exists(f"text~'{decade}'"),
        # Loose signal that we opened an article view.
        "opened_article_signal": exists("role=heading"),
        # The strict year check is done from extracted year; this is the fallback UI signal.
        "published_year_signal": exists("text~'199'"),
        # Intentional custom hook template.
        "custom": custom,
    }

