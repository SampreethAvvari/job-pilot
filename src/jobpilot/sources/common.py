"""Helpers shared by source fetchers."""

from __future__ import annotations

import html as html_lib
import re
from datetime import datetime, timezone

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    return html_lib.unescape(_TAG_RE.sub(" ", text or "")).strip()


def parse_dt(value: str | int | float | None) -> datetime | None:
    """Parse ISO strings or epoch seconds/milliseconds into aware UTC datetimes."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        if value > 1e12:  # epoch milliseconds
            value = value / 1000
        return datetime.fromtimestamp(value, tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def title_matches(title: str, queries: list[str]) -> bool:
    """True when every word of any query appears as a whole word in the title."""
    t = title.lower()
    for q in queries:
        if all(re.search(rf"\b{re.escape(word)}\b", t) for word in q.lower().split()):
            return True
    return False
