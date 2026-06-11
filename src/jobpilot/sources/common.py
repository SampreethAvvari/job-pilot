"""Helpers shared by source fetchers."""

from __future__ import annotations

import html as html_lib
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx

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


# Per-run health sink for per-company board sources: source -> slug -> count|error.
# Cleared by pipeline.fetch_all() at the start of every run; the pipeline writes
# it back to the Companies sheet tab afterwards.
RUN_STATS: dict[str, dict[str, str]] = {}


def fetch_many(source: str, slugs: list[str], fetch_one, per_company: int,
               max_workers: int = 16) -> list:
    """Run fetch_one(slug) -> list[Posting] across a thread pool.

    Caps each company's matches at per_company, records per-slug counts or
    error strings in RUN_STATS, and never lets one bad board kill the source.
    """
    def run(slug: str) -> tuple[str, list, str]:
        try:
            return slug, fetch_one(slug), ""
        except httpx.HTTPStatusError as exc:
            return slug, [], str(exc.response.status_code)
        except httpx.HTTPError as exc:
            return slug, [], type(exc).__name__

    postings: list = []
    stats = RUN_STATS.setdefault(source, {})
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for slug, got, err in pool.map(run, slugs):
            if err:
                stats[slug] = err
                continue
            got = got[:per_company]
            stats[slug] = str(len(got))
            postings.extend(got)
    return postings
