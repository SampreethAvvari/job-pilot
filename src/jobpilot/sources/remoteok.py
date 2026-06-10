"""RemoteOK public API — free, keyless, remote jobs only. Requires a UA header."""

from __future__ import annotations

import httpx

from jobpilot.config import Config, SourceCfg
from jobpilot.models import Posting
from jobpilot.sources.common import parse_dt, strip_html, title_matches

URL = "https://remoteok.com/api"


def fetch(sc: SourceCfg, cfg: Config, client: httpx.Client) -> list[Posting]:
    resp = client.get(URL, headers={"User-Agent": "JobPilot/1.0"})
    resp.raise_for_status()
    items = resp.json()
    out: list[Posting] = []
    for item in items[1:]:  # first element is a legal-notice dict, not a job
        title = item.get("position", "")
        if not title_matches(title, cfg.queries):
            continue
        salary = None
        if item.get("salary_min") and item.get("salary_max"):
            salary = f"${item['salary_min']:,}–${item['salary_max']:,}"
        out.append(
            Posting(
                title=title,
                company=item.get("company", ""),
                location=item.get("location") or "Remote",
                remote=True,
                url=item.get("url", ""),
                source="remoteok",
                posted_at=parse_dt(item.get("date")),
                description=strip_html(item.get("description", "")),
                salary=salary,
            )
        )
    cap = min(sc.max_items, cfg.caps.per_source)
    return out[:cap]
