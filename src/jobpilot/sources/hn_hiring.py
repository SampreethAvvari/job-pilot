"""Hacker News monthly 'Ask HN: Who is hiring?' thread via the free Algolia API.

Comment first lines conventionally read 'Company | Role | Location | ...'. We parse
coarsely here; the scorer reads the full text for the fine-grained judgment.
"""

from __future__ import annotations

import httpx

from jobpilot.config import Config, SourceCfg
from jobpilot.models import Posting
from jobpilot.sources import SourceError
from jobpilot.sources.common import parse_dt, strip_html, title_matches

SEARCH = "https://hn.algolia.com/api/v1/search_by_date"


def _latest_story_id(client: httpx.Client) -> str:
    resp = client.get(
        SEARCH,
        params={"query": "Ask HN: Who is hiring?", "tags": "story,author_whoishiring"},
    )
    resp.raise_for_status()
    hits = [h for h in resp.json().get("hits", []) if "who is hiring" in h.get("title", "").lower()]
    if not hits:
        raise SourceError("hn_hiring: no 'Who is hiring' story found")
    return hits[0]["objectID"]


def fetch(sc: SourceCfg, cfg: Config, client: httpx.Client) -> list[Posting]:
    story_id = _latest_story_id(client)
    resp = client.get(
        SEARCH,
        params={"tags": f"comment,story_{story_id}", "hitsPerPage": sc.max_items},
    )
    resp.raise_for_status()
    out: list[Posting] = []
    for hit in resp.json().get("hits", []):
        if str(hit.get("parent_id")) != str(story_id):
            continue  # top-level job comments only
        text = strip_html(hit.get("comment_text", ""))
        if not text:
            continue
        first_line = text.split("\n")[0][:300]
        parts = [p.strip() for p in first_line.split("|") if p.strip()]
        if not parts:
            continue
        company = parts[0][:80]
        title = parts[1][:120] if len(parts) > 1 else first_line[:120]
        location = parts[2][:80] if len(parts) > 2 else ""
        if not title_matches(f"{title} {first_line}", cfg.queries):
            continue
        out.append(
            Posting(
                title=title,
                company=company,
                location=location,
                remote="remote" in first_line.lower() or None,
                url=f"https://news.ycombinator.com/item?id={hit['objectID']}",
                source="hn_hiring",
                posted_at=parse_dt(hit.get("created_at")),
                description=text,
            )
        )
    return out[: cfg.caps.per_source]
