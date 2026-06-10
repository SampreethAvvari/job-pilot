"""Ashby public job-board API — free, keyless, per-company."""

from __future__ import annotations

import httpx

from jobpilot.config import Config, SourceCfg
from jobpilot.models import Posting
from jobpilot.sources.common import parse_dt, strip_html, title_matches

BASE = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def fetch(sc: SourceCfg, cfg: Config, client: httpx.Client) -> list[Posting]:
    out: list[Posting] = []
    for slug in sc.companies:
        resp = client.get(BASE.format(slug=slug))
        if resp.status_code == 404:
            continue
        resp.raise_for_status()
        for job in resp.json().get("jobs", []):
            title = job.get("title", "")
            if not title_matches(title, cfg.queries):
                continue
            out.append(
                Posting(
                    title=title,
                    company=slug,
                    location=job.get("location", ""),
                    remote=job.get("isRemote"),
                    url=job.get("jobUrl") or job.get("applyUrl", ""),
                    source="ashby",
                    posted_at=parse_dt(job.get("publishedAt")),
                    description=strip_html(job.get("descriptionHtml", "")),
                )
            )
    return out[: cfg.caps.per_source]
